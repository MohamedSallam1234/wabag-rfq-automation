"""Orchestrate map-reduce RFQ generation: parallel per-document extraction → merge + fill.

Each source document is extracted in its own LLM call (fanned out concurrently with
``asyncio.gather`` — pure async I/O, no threads), producing a partial datasheet. A single reduce
call then merges those partials against the template and fills the complete datasheet, which we
render to ``.xlsx``. This keeps every individual call within the model's context window even when
the whole project would not fit in one call.
"""

import asyncio
import json
import logging
from collections.abc import Sequence

import anyio
from pydantic import ValidationError
from storage3 import AsyncStorageClient

from app.agents.llm.router import LLMRouter
from app.models.document import Document
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


def parse_generation(text: str) -> RFQGeneration:
    """Parse an LLM text response into an :class:`RFQGeneration`.

    Tolerant of surrounding prose or ```json code fences: the first ``{`` … last ``}`` slice is
    taken as the JSON object.

    Raises:
        RFQGenerationError: If no JSON object is found, or it is invalid / does not validate.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise RFQGenerationError("no JSON object found in the LLM response")
    try:
        data = json.loads(text[start : end + 1])
        return RFQGeneration.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise RFQGenerationError("the LLM response was not valid RFQ JSON") from exc


def summarize(generation: RFQGeneration) -> RFQSummary:
    """Count field statuses across the generated datasheet."""
    counts = {"extracted": 0, "conflict": 0, "tbd": 0}
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
    )


def _doc_label(doc: Document) -> str:
    """Human label for a source document (filename + classification)."""
    return f"{doc.original_filename} ({doc.doc_type or 'unclassified'})"


async def _extract_one(
    doc: Document,
    *,
    equipment: str,
    template_label: str,
    template_md: str,
    storage: AsyncStorageClient,
    bucket: str,
    llm: LLMRouter,
    sem: asyncio.Semaphore,
) -> tuple[str, RFQGeneration]:
    """Map step: download one document's Markdown and extract its supported fields.

    Returns ``(document_label, partial_generation)``. Failures are logged with the document label
    and re-raised so the caller can fail the whole request (a dropped source is not acceptable).
    """
    label = _doc_label(doc)
    try:
        raw = await storage.from_(bucket).download(doc.storage_path)
        markdown = raw.decode("utf-8")
        async with sem:
            text = await llm.ask(
                user_message=extraction_message(
                    equipment, template_label, template_md, label, markdown
                ),
                task_instructions=extraction_instructions(equipment),
            )
        return label, parse_generation(text)
    except Exception:
        logger.warning("RFQ extraction failed for document %s", label)
        raise


async def generate_rfq(
    *,
    equipment: str,
    template_label: str,
    template_md: str,
    sources: Sequence[Document],
    storage: AsyncStorageClient,
    bucket: str,
    llm: LLMRouter,
    max_concurrency: int,
) -> tuple[RFQGeneration, bytes]:
    """Generate one equipment's RFQ datasheet via map-reduce; return it and the rendered ``.xlsx``.

    Map: extract each source document concurrently (bounded by ``max_concurrency``). Reduce: one
    call merges the partials against the template and fills the complete datasheet. Render off the
    event loop.

    Raises:
        RFQGenerationError: If any LLM response cannot be parsed into an :class:`RFQGeneration`.
        storage3.utils.StorageException: If a source document's bytes cannot be downloaded.
        app.agents.llm.router.LLMTransientError / LLMFatalError: On LLM failures.
    """
    sem = asyncio.Semaphore(max_concurrency)
    tasks = [
        _extract_one(
            doc,
            equipment=equipment,
            template_label=template_label,
            template_md=template_md,
            storage=storage,
            bucket=bucket,
            llm=llm,
            sem=sem,
        )
        for doc in sources
    ]
    extractions: list[tuple[str, RFQGeneration]] = await asyncio.gather(*tasks)

    partials = [(label, partial.model_dump_json()) for label, partial in extractions]
    merge_text = await llm.ask(
        user_message=merge_message(equipment, template_label, template_md, partials),
        task_instructions=merge_instructions(equipment),
    )
    final = parse_generation(merge_text)
    xlsx_bytes: bytes = await anyio.to_thread.run_sync(render_xlsx, final)
    return final, xlsx_bytes
