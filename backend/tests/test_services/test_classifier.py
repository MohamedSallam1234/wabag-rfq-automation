"""Tests for filename-based document classification."""

import pytest

from app.models.document import RetentionPolicy
from app.services.ingestion.classifier import classify_filename, retention_for, revision_sort_key

DOC_TYPE_CASES = [
    ("01_Employer_Specs.pdf", "Employer Technical Specifications"),
    ("02_Process_Engineering.docx", "Process Engineering Profile"),
    ("03_RFQ_Blower_Template.xlsx", "RFQ Template"),
    ("04_Hydraulic_Profile.pdf", "Hydraulic Calculation Profile"),
    ("05_Equipment List.xlsx", "Equipment List"),
    ("General Motors Specs.pdf", "General Motor Specifications"),
    ("GENERAL MECHANICAL WORKS spec.pdf", "General Mechanical Works Specs"),
    ("Local control panels DataSheet.pdf", "Local Control Panel DataSheet"),
    ("Authorization letter signed.pdf", "RFQ Authorization Letter"),
    ("Pump DataSheet.pdf", "Equipment DataSheet"),
    ("Blower Specs.pdf", "Equipment Specification Document"),
    ("summary.pdf", None),
    ("random_notes.docx", None),
]


@pytest.mark.parametrize(("filename", "expected"), DOC_TYPE_CASES)
def test_classify_doc_type(filename: str, expected: str | None) -> None:
    assert classify_filename(filename).doc_type == expected


def test_classify_is_case_insensitive() -> None:
    assert classify_filename("01_employer.PDF").doc_type == "Employer Technical Specifications"


def test_classify_ignores_directory_components() -> None:
    result = classify_filename("uploads\\sub/01_Employer.pdf")
    assert result.doc_type == "Employer Technical Specifications"


REVISION_CASES = [
    ("01_x_Rev00.pdf", 0, "Rev00"),
    ("01_x_Rev01.pdf", 1, "Rev01"),
    ("a rev.01.pdf", 1, "rev.01"),
    ("a Rev 02.pdf", 2, "Rev 02"),
    ("x_Rev000.pdf", 0, "Rev000"),
    ("x_Rev00a.pdf", 0, "Rev00a"),
]


@pytest.mark.parametrize(("filename", "number", "label"), REVISION_CASES)
def test_classify_revision(filename: str, number: int, label: str) -> None:
    result = classify_filename(filename)
    assert result.revision_number == number
    assert result.revision_label == label


def test_classify_no_revision() -> None:
    result = classify_filename("summary.pdf")
    assert result.revision_number is None
    assert result.revision_label is None


def test_revision_sort_key_orders_numbers() -> None:
    assert revision_sort_key(1, "Rev01") > revision_sort_key(0, "Rev00")


def test_revision_sort_key_suffix_is_newer() -> None:
    assert revision_sort_key(0, "Rev00a") > revision_sort_key(0, "Rev00")


def test_revision_sort_key_missing_sorts_first() -> None:
    assert revision_sort_key(None, None) < revision_sort_key(0, "Rev00")


PERSISTENT_TYPES = [
    "Employer Technical Specifications",
    "Process Engineering Profile",
    "Hydraulic Calculation Profile",
    "Equipment List",
]
TRANSIENT_TYPES = [
    "RFQ Template",
    "Equipment DataSheet",
    "Equipment Specification Document",
    "General Motor Specifications",
    None,  # unmatched files default to transient
]


@pytest.mark.parametrize("doc_type", PERSISTENT_TYPES)
def test_retention_for_persistent(doc_type: str) -> None:
    assert retention_for(doc_type) is RetentionPolicy.PERSISTENT


@pytest.mark.parametrize("doc_type", TRANSIENT_TYPES)
def test_retention_for_transient(doc_type: str | None) -> None:
    assert retention_for(doc_type) is RetentionPolicy.TRANSIENT
