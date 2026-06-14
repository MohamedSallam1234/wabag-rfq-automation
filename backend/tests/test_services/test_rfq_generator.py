"""Tests for RFQ generation orchestration: JSON parsing, status summary, end-to-end assembly."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.rfq.generator import (
    RFQGenerationError,
    generate_rfq,
    parse_generation,
    summarize,
)

_VALID = {
    "equipment_tag": "B-100",
    "equipment_category": "Blower",
    "header": {"Project": "Kohafa"},
    "sections": [
        {
            "title": "Process",
            "fields": [
                {
                    "field": "Capacity",
                    "value": 860,
                    "unit": "m3/hr",
                    "confidence": 0.9,
                    "source_ref": "04",
                    "status": "extracted",
                },
                {"field": "Head", "value": None, "status": "tbd", "confidence": 0.0},
                {
                    "field": "Material",
                    "status": "conflict",
                    "confidence": 0.0,
                    "conflicts": [
                        {"value": "SS304", "source_ref": "01"},
                        {"value": "SS316", "source_ref": "02"},
                    ],
                },
            ],
        }
    ],
}


def test_parse_generation_plain_json() -> None:
    gen = parse_generation(json.dumps(_VALID))
    assert gen.equipment_tag == "B-100"
    assert gen.sections[0].fields[0].value == 860


def test_parse_generation_strips_code_fence() -> None:
    text = "```json\n" + json.dumps(_VALID) + "\n```"
    assert parse_generation(text).sections[0].title == "Process"


def test_parse_generation_ignores_surrounding_prose() -> None:
    text = "Here is the RFQ you asked for:\n" + json.dumps(_VALID) + "\nLet me know!"
    assert parse_generation(text).equipment_tag == "B-100"


def test_parse_generation_no_json_raises() -> None:
    with pytest.raises(RFQGenerationError):
        parse_generation("there is no json here")


def test_parse_generation_malformed_json_raises() -> None:
    with pytest.raises(RFQGenerationError):
        parse_generation("{ not: valid json }")


def test_summarize_counts_statuses() -> None:
    summary = summarize(parse_generation(json.dumps(_VALID)))
    assert summary.fields_total == 3
    assert summary.extracted == 1
    assert summary.tbd == 1
    assert summary.conflict == 1


class _FakeLLM:
    """Records every call and returns a fixed valid JSON response (valid for both stages)."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.calls: list[tuple[str, str | None]] = []

    async def ask(self, user_message: str, task_instructions: str | None = None) -> str:
        self.calls.append((user_message, task_instructions))
        return self._response


async def test_generate_rfq_fans_out_per_document_then_merges() -> None:
    proxy = MagicMock()
    proxy.download = AsyncMock(side_effect=lambda path: f"## md for {path}".encode())
    storage = MagicMock()
    storage.from_ = MagicMock(return_value=proxy)
    llm = _FakeLLM(json.dumps(_VALID))

    sources = [
        SimpleNamespace(
            storage_path="p/01.md",
            original_filename="01_Spec.pdf",
            doc_type="Employer Technical Specifications",
        ),
        SimpleNamespace(
            storage_path="p/06.md",
            original_filename="06_List.xlsx",
            doc_type="Equipment List",
        ),
    ]

    generation, xlsx_bytes = await generate_rfq(
        equipment="aeration blower",
        template_label="03_RFQ_Blower.xlsx (RFQ Template)",
        template_md="# Blower Template",
        sources=sources,
        storage=storage,
        bucket="rfq-documents",
        llm=llm,
        max_concurrency=8,
    )

    assert generation.equipment_tag == "B-100"
    assert xlsx_bytes.startswith(b"PK\x03\x04")

    # N extraction calls + 1 merge call; every source was downloaded.
    assert len(llm.calls) == len(sources) + 1
    assert proxy.download.await_count == len(sources)

    extraction_msgs = [msg for msg, _ in llm.calls if "EXTRACTION FROM:" not in msg]
    merge_msgs = [msg for msg, _ in llm.calls if "EXTRACTION FROM:" in msg]
    assert len(extraction_msgs) == 2
    assert len(merge_msgs) == 1
    # Each extraction carries exactly one document.
    for msg in extraction_msgs:
        assert msg.count("# === DOCUMENT:") == 1
    # The merge carries both partials + the template.
    assert merge_msgs[0].count("# === EXTRACTION FROM:") == 2
    assert "Blower Template" in merge_msgs[0]
    assert "aeration blower" in merge_msgs[0]
