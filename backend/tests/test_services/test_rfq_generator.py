"""Tests for RFQ generation orchestration: JSON parsing, status summary, end-to-end assembly."""

import json

import pytest

from app.services.rfq.generator import (
    RFQGenerationError,
    SourceDoc,
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
                    "source_document": "04_Hydraulic",
                    "source_location": "Sheet Design",
                    "evidence": "design flow 860 m3/hr",
                    "status": "extracted",
                },
                {"field": "Head", "value": None, "status": "tbd", "confidence": 0.0},
                {
                    "field": "Material",
                    "status": "conflict",
                    "confidence": 0.0,
                    "conflicts": [
                        {"value": "SS304", "source_document": "01", "source_location": "Sec 3.2"},
                        {"value": "SS316", "source_document": "02", "source_location": "Table 4"},
                    ],
                },
                {"field": "Coupling", "value": None, "status": "vtf", "confidence": 0.0},
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
    assert summary.fields_total == 4
    assert summary.extracted == 1
    assert summary.tbd == 1
    assert summary.conflict == 1
    assert summary.vtf == 1


class _FakeLLM:
    """Records every call and returns a fixed valid JSON response (valid for both stages)."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.calls: list[tuple[str, str | None]] = []

    async def ask(self, user_message: str, task_instructions: str | None = None) -> str:
        self.calls.append((user_message, task_instructions))
        return self._response


async def test_generate_rfq_fans_out_per_document_then_merges() -> None:
    llm = _FakeLLM(json.dumps(_VALID))
    sources = [
        SourceDoc(
            label="01_Spec.pdf (Employer Technical Specifications)", tier=1, markdown="## spec md"
        ),
        SourceDoc(label="06_List.xlsx (Equipment List)", tier=5, markdown="## list md"),
    ]

    generation, xlsx_bytes = await generate_rfq(
        equipment="aeration blower",
        template_label="05_RFQ_Blower.xlsx (RFQ Template)",
        template_md="# Blower Template",
        sources=sources,
        llm=llm,
        max_concurrency=8,
    )

    assert generation.equipment_tag == "B-100"
    assert xlsx_bytes.startswith(b"PK\x03\x04")

    # N extraction calls + 1 merge call.
    assert len(llm.calls) == len(sources) + 1

    extraction_msgs = [msg for msg, _ in llm.calls if "EXTRACTION FROM:" not in msg]
    merge_msgs = [msg for msg, _ in llm.calls if "EXTRACTION FROM:" in msg]
    assert len(extraction_msgs) == 2
    assert len(merge_msgs) == 1
    # Each extraction carries exactly one document, stamped with its precedence tier.
    for msg in extraction_msgs:
        assert msg.count("# === DOCUMENT:") == 1
        assert "PRECEDENCE TIER" in msg
    # The merge carries both partials (with tiers) + the template.
    assert merge_msgs[0].count("# === EXTRACTION FROM:") == 2
    assert "PRECEDENCE TIER 1" in merge_msgs[0]
    assert "Blower Template" in merge_msgs[0]
    assert "aeration blower" in merge_msgs[0]


async def test_generate_rfq_rejects_bad_concurrency() -> None:
    with pytest.raises(RFQGenerationError):
        await generate_rfq(
            equipment="x",
            template_label="t",
            template_md="t",
            sources=[],
            llm=_FakeLLM(json.dumps(_VALID)),
            max_concurrency=0,
        )
