"""Offline accuracy eval for RFQ generation — run the real map-reduce against a known-good RFQ.

This is a **developer tool**, not part of the test suite (it makes real LLM calls and needs sample
data). It is deliberately kept outside ``src/`` so the pre-commit gates (pytest/ruff/mypy/coverage,
which target ``src/`` and ``tests/``) do not run against it.

Usage
-----
    cd backend
    uv run python scripts/eval_rfq.py <sample_dir> --equipment "aeration blower"

Expected ``<sample_dir>`` layout::

    <sample_dir>/
      sources/            # the project's source documents (.pdf/.docx/.xlsx/.xls or pre-made .md)
      template.<ext>      # the RFQ template (.pdf/.docx/.xlsx/.xls or .md)
      ground_truth.json   # the known-good answer (see below)

``ground_truth.json`` may be either:
  * a flat ``{"Field name": "expected value", ...}`` map, or
  * a full ``RFQGeneration`` JSON object (the eval flattens its ``sections[].fields[]``).

The script prints an overall field-level accuracy %, the produced status distribution, and a
per-field diff (OK = match / X = mismatch). Capture the number before and after a change to confirm
the accuracy is recovering.
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

from openrouter import OpenRouter

from app.agents.llm.router import build_router
from app.core.config import get_settings
from app.schemas.rfq import RFQGeneration
from app.services.ingestion.classifier import classify_filename
from app.services.ingestion.excel_parser import extract_xls_markdown, extract_xlsx_markdown
from app.services.ingestion.pdf_text import extract_pdf_markdown
from app.services.ingestion.word_parser import extract_docx_markdown
from app.services.rfq.generator import SourceDoc, generate_rfq, summarize
from app.services.rfq.precedence import precedence_tier

_SUPPORTED = {".pdf", ".docx", ".xlsx", ".xls", ".md"}


def _to_markdown(path: Path) -> str:
    """Convert a sample file to Markdown using the same parsers as the intake pipeline."""
    ext = path.suffix.lower()
    if ext == ".md":
        return path.read_text(encoding="utf-8")
    if ext == ".pdf":
        return extract_pdf_markdown(str(path))[0]
    if ext == ".docx":
        return extract_docx_markdown(str(path))
    if ext == ".xlsx":
        return extract_xlsx_markdown(str(path))[0]
    if ext == ".xls":
        return extract_xls_markdown(str(path))[0]
    raise ValueError(f"unsupported sample file type: {path.name}")


def _load_sources(sources_dir: Path) -> list[SourceDoc]:
    """Build a SourceDoc for every supported file in ``sources_dir`` (tier from its filename)."""
    docs: list[SourceDoc] = []
    for path in sorted(sources_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in _SUPPORTED:
            continue
        doc_type = classify_filename(path.name).doc_type
        docs.append(
            SourceDoc(
                label=f"{path.name} ({doc_type or 'unclassified'})",
                tier=precedence_tier(doc_type),
                markdown=_to_markdown(path),
            )
        )
    return docs


def _flatten_truth(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize ground truth into a ``{field_name: expected_value}`` map."""
    if "sections" in raw:  # a full RFQGeneration object
        flat: dict[str, Any] = {}
        for section in raw.get("sections", []):
            for field in section.get("fields", []):
                flat[field["field"]] = field.get("value")
        return flat
    return raw


def _norm(value: Any) -> str:
    """Normalize a value for tolerant comparison (case, whitespace, trailing-zero numbers)."""
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"\s+", " ", text)
    try:  # compare numbers by magnitude so "860" == "860.0"
        return str(float(text))
    except ValueError:
        return text


def _produced_values(generation: RFQGeneration) -> dict[str, Any]:
    """Flatten a produced generation into ``{normalized_field_name: value}``."""
    return {
        field.field.strip().lower(): field.value
        for section in generation.sections
        for field in section.fields
    }


def _score(generation: RFQGeneration, truth: dict[str, Any]) -> None:
    """Print the per-field diff and the overall accuracy."""
    produced = _produced_values(generation)
    matches = 0
    print("\nPer-field diff (OK = match / X = mismatch):")
    for name, expected in truth.items():
        got = produced.get(name.strip().lower())
        ok = _norm(got) == _norm(expected) and _norm(expected) != ""
        matches += ok
        mark = "OK" if ok else "X "
        print(f"  {mark} {name!r}: expected {expected!r} | got {got!r}")
    total = len(truth) or 1
    print(f"\nAccuracy: {matches}/{len(truth)} = {matches / total:.1%}")
    summary = summarize(generation)
    print(
        f"Status distribution: extracted={summary.extracted} conflict={summary.conflict} "
        f"tbd={summary.tbd} vtf={summary.vtf} (total={summary.fields_total})"
    )


async def _run(sample_dir: Path, equipment: str) -> None:
    settings = get_settings()
    sources = _load_sources(sample_dir / "sources")
    if not sources:
        raise SystemExit(f"no source documents found in {sample_dir / 'sources'}")
    template_path = next(
        (p for p in sample_dir.glob("template.*") if p.suffix.lower() in _SUPPORTED), None
    )
    if template_path is None:
        raise SystemExit(f"no template.<ext> found in {sample_dir}")
    template_md = _to_markdown(template_path)
    truth = _flatten_truth(json.loads((sample_dir / "ground_truth.json").read_text("utf-8")))

    print(f"Sources: {len(sources)} | template: {template_path.name} | truth fields: {len(truth)}")
    async with OpenRouter(api_key=settings.OPENROUTER_API_KEY.get_secret_value()) as open_router:
        llm = build_router(settings, open_router)
        generation, _ = await generate_rfq(
            equipment=equipment,
            template_label=f"{template_path.name} (RFQ Template)",
            template_md=template_md,
            sources=sources,
            llm=llm,
            max_concurrency=settings.RFQ_MAX_CONCURRENT_EXTRACTIONS,
        )
    _score(generation, truth)


def main() -> None:
    """Parse args and run one evaluation."""
    parser = argparse.ArgumentParser(description="Evaluate RFQ generation accuracy on a sample.")
    parser.add_argument("sample_dir", type=Path, help="Directory holding sources/, template.*, …")
    parser.add_argument("--equipment", required=True, help='Equipment name, e.g. "aeration blower"')
    args = parser.parse_args()
    if not args.sample_dir.is_dir():
        sys.exit(f"not a directory: {args.sample_dir}")
    asyncio.run(_run(args.sample_dir, args.equipment))


if __name__ == "__main__":
    main()
