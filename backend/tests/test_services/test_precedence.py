"""Tests for the RFQ source-precedence ladder."""

from app.services.ingestion.classifier import DocType
from app.services.rfq.precedence import (
    STANDARDS_TIER,
    precedence_tier,
    tier_label,
)


def test_employer_specs_are_the_golden_tier() -> None:
    assert precedence_tier(DocType.EMPLOYER_TECHNICAL_SPECIFICATIONS.value) == 1


def test_core_inputs_are_strictly_ordered() -> None:
    tiers = [
        precedence_tier(DocType.EMPLOYER_TECHNICAL_SPECIFICATIONS.value),
        precedence_tier(DocType.PROCESS_ENGINEERING_PROFILE.value),
        precedence_tier(DocType.HYDRAULIC_CALCULATION_PROFILE.value),
        precedence_tier(DocType.EQUIPMENT_LIST.value),
    ]
    assert tiers == [1, 2, 3, 4]
    assert tiers == sorted(tiers)


def test_datasheets_and_general_specs_fall_to_default_tier() -> None:
    # Datasheets/general specs no longer have a dedicated tier (their content lives in the
    # Employer's Technical Specifications); they resolve to the default "other" tier.
    for doc_type in (
        DocType.EQUIPMENT_DATASHEET,
        DocType.EQUIPMENT_SPECIFICATION_DOCUMENT,
        DocType.GENERAL_MOTOR_SPECIFICATIONS,
        DocType.GENERAL_MECHANICAL_WORKS_SPECS,
        DocType.LOCAL_CONTROL_PANEL_DATASHEET,
    ):
        assert precedence_tier(doc_type.value) == 5
        # Below the core engineering inputs, but still above raw industry standards.
        assert precedence_tier(DocType.EQUIPMENT_LIST.value) < precedence_tier(doc_type.value)
        assert precedence_tier(doc_type.value) < STANDARDS_TIER


def test_unknown_and_none_fall_to_default_tier() -> None:
    assert precedence_tier(None) == 5
    assert precedence_tier("Something Unrecognized") == 5
    assert precedence_tier(None) < STANDARDS_TIER


def test_tier_label_is_human_readable() -> None:
    assert "Employer" in tier_label(1)
    assert "Standards" in tier_label(STANDARDS_TIER)
    assert tier_label(99) == "Unclassified"
