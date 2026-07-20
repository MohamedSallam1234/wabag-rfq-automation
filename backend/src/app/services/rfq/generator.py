"""Orchestrate map-reduce RFQ generation: parallel per-document extraction → merge + fill.

Each source document is extracted in its own LLM call (fanned out concurrently with
``asyncio.gather`` — pure async I/O, no threads), producing a *partial* datasheet that carries the
evidence (verbatim quote + ``source_ref``) and the document's precedence tier. A single reduce call
then merges those partials against the template — applying the precedence/conflict rules over the
compact evidence — and fills the complete datasheet, which we render to ``.xlsx``. This keeps every
individual call within the model's context window even when the whole project would not fit in one
call, while still giving the reduce stage enough evidence to reason across documents.

The orchestrator is **storage-agnostic**: it operates on :class:`SourceDoc` values whose Markdown is
already resolved by the caller (downloaded from storage for project documents, or converted
in-memory for files supplied directly in the request).
"""

import asyncio
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass

import anyio
from pydantic import ValidationError

from app.agents.llm.router import LLMRouter
from app.schemas.rfq import RFQGeneration, RFQSummary
from app.services.rfq.prompt import (
    extraction_instructions,
    extraction_message,
    merge_instructions,
    merge_message,
)
from app.services.rfq.renderer import render_xlsx

logger = logging.getLogger(__name__)


class RFQGenerationError(Exception):
    """An LLM response could not be parsed/validated into an :class:`RFQGeneration`."""


@dataclass(frozen=True)
class SourceDoc:
    """A resolved source document for extraction.

    ``label`` is a human reference (filename + classification) used in prompts and ``source_ref``;
    ``tier`` is the precedence tier (see :mod:`app.services.rfq.precedence`); ``markdown`` is the
    document's already-resolved Markdown content.
    """

    label: str
    tier: int
    markdown: str


def parse_generation(text: str) -> RFQGeneration:
    """Parse an LLM text response into an :class:`RFQGeneration`.

    Tolerant of surrounding prose or ```json code fences: scans for the first ``{`` that begins a
    decodable JSON object (via :meth:`json.JSONDecoder.raw_decode`) which also validates as an
    :class:`RFQGeneration`. Decodable objects that don't validate are skipped rather than fatal —
    this matters when the text is a reasoning/thinking stream that contains intermediate JSON
    fragments before the final datasheet (see :mod:`app.agents.llm.router`).

    Raises:
        RFQGenerationError: If no decodable JSON object is found, or none of the decoded objects
            validate as an :class:`RFQGeneration`.
    """
    decoder = json.JSONDecoder()
    last_error: ValidationError | None = None
    for idx, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            data, _ = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            continue
        try:
            return RFQGeneration.model_validate(data)
        except ValidationError as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise RFQGenerationError("the LLM response was not valid RFQ JSON") from last_error
    raise RFQGenerationError("no JSON object found in the LLM response")


def summarize(generation: RFQGeneration) -> RFQSummary:
    """Count field statuses across the generated datasheet."""
    counts = {"extracted": 0, "conflict": 0, "tbd": 0, "vtf": 0}
    total = 0
    for section in generation.sections:
        for field in section.fields:
            total += 1
            counts[field.status] += 1
    return RFQSummary(
        fields_total=total,
        extracted=counts["extracted"],
        conflict=counts["conflict"],
        tbd=counts["tbd"],
        vtf=counts["vtf"],
    )


async def _extract_one(
    doc: SourceDoc,
    *,
    equipment: str,
    template_label: str,
    template_md: str,
    llm: LLMRouter,
    sem: asyncio.Semaphore,
) -> tuple[SourceDoc, RFQGeneration]:
    """Map step: extract one document's supported fields (with evidence + its precedence tier).

    Returns ``(source_doc, partial_generation)``. Failures are logged with the document label and
    re-raised so the caller can fail the whole request (a dropped source is not acceptable).
    """
    try:
        async with sem:
            text = await llm.ask(
                user_message=extraction_message(
                    equipment, template_label, template_md, doc.label, doc.tier, doc.markdown
                ),
                task_instructions=extraction_instructions(equipment),
            )
        return doc, parse_generation(text)
    except Exception:
        logger.warning("RFQ extraction failed for document %s", doc.label)
        raise


async def generate_rfq(
    *,
    equipment: str,
    template_label: str,
    template_md: str,
    sources: Sequence[SourceDoc],
    llm: LLMRouter,
    max_concurrency: int,
) -> tuple[RFQGeneration, bytes]:
    """Generate one equipment's RFQ datasheet via map-reduce; return it and the rendered ``.xlsx``.

    Map: extract each source document concurrently (bounded by ``max_concurrency``). Reduce: one
    call merges the partials against the template — applying precedence/conflict rules over each
    partial's evidence and tier — and fills the complete datasheet. Render off the event loop.

    Raises:
        RFQGenerationError: If ``max_concurrency`` < 1 or any LLM response cannot be parsed into an
            :class:`RFQGeneration`.
        app.agents.llm.router.LLMTransientError / LLMFatalError: On LLM failures.
    """
    if max_concurrency < 1:
        raise RFQGenerationError("max_concurrency must be >= 1")
    sem = asyncio.Semaphore(max_concurrency)
    tasks = [
        asyncio.create_task(
            _extract_one(
                doc,
                equipment=equipment,
                template_label=template_label,
                template_md=template_md,
                llm=llm,
                sem=sem,
            )
        )
        for doc in sources
    ]
    try:
        extractions: list[tuple[SourceDoc, RFQGeneration]] = await asyncio.gather(*tasks)
    except BaseException:
        # One extraction failed (or the request was cancelled): cancel the still-pending LLM
        # calls so we don't burn tokens/capacity on results we're about to discard, then let the
        # original exception propagate unchanged (gather re-raises the first one).
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise

    partials = [(doc.label, doc.tier, partial.model_dump_json()) for doc, partial in extractions]
    merge_text = await llm.ask(
        user_message=merge_message(equipment, template_label, template_md, partials),
        task_instructions=merge_instructions(equipment),
    )
    final = parse_generation(merge_text)
    xlsx_bytes: bytes = await anyio.to_thread.run_sync(render_xlsx, final)
    return final, xlsx_bytes
