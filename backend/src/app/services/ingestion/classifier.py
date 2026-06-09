"""Deterministic document classification from filename patterns (no I/O, no LLM).

Classification follows the filename-prefix rules in the SRS (README ``F-02``). The
function is pure so it is cheap to unit-test and has no external dependencies.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from app.models.document import RetentionPolicy


class DocType(StrEnum):
    """The set of document types recognised by the classifier."""

    EMPLOYER_TECHNICAL_SPECIFICATIONS = "Employer Technical Specifications"
    PROCESS_ENGINEERING_PROFILE = "Process Engineering Profile"
    RFQ_TEMPLATE = "RFQ Template"
    HYDRAULIC_CALCULATION_PROFILE = "Hydraulic Calculation Profile"
    EQUIPMENT_LIST = "Equipment List"
    GENERAL_MOTOR_SPECIFICATIONS = "General Motor Specifications"
    GENERAL_MECHANICAL_WORKS_SPECS = "General Mechanical Works Specs"
    LOCAL_CONTROL_PANEL_DATASHEET = "Local Control Panel DataSheet"
    RFQ_AUTHORIZATION_LETTER = "RFQ Authorization Letter"
    EQUIPMENT_DATASHEET = "Equipment DataSheet"
    EQUIPMENT_SPECIFICATION_DOCUMENT = "Equipment Specification Document"


# Ordered rules; the first matching pattern wins. Tender-section patterns
# (SectionII through SectionVII) are intentionally excluded - out of scope.
_RULES: list[tuple[re.Pattern[str], DocType]] = [
    (re.compile(r"^01_", re.IGNORECASE), DocType.EMPLOYER_TECHNICAL_SPECIFICATIONS),
    (re.compile(r"^02_", re.IGNORECASE), DocType.PROCESS_ENGINEERING_PROFILE),
    (re.compile(r"^03_RFQ", re.IGNORECASE), DocType.RFQ_TEMPLATE),
    (re.compile(r"^04_", re.IGNORECASE), DocType.HYDRAULIC_CALCULATION_PROFILE),
    (re.compile(r"^05_", re.IGNORECASE), DocType.EQUIPMENT_LIST),
    (re.compile(r"^General Motors Specs", re.IGNORECASE), DocType.GENERAL_MOTOR_SPECIFICATIONS),
    (
        re.compile(r"^GENERAL MECHANICAL WORKS", re.IGNORECASE),
        DocType.GENERAL_MECHANICAL_WORKS_SPECS,
    ),
    (
        re.compile(r"^Local control panels DataSheet", re.IGNORECASE),
        DocType.LOCAL_CONTROL_PANEL_DATASHEET,
    ),
    (re.compile(r"^Authorization letter", re.IGNORECASE), DocType.RFQ_AUTHORIZATION_LETTER),
]

# Generic equipment documents: a keyword appearing anywhere in a PDF filename, applied
# only after the specific prefix rules above fail. Plain substring checks (not
# ``.*keyword.*\.pdf$`` regexes) avoid polynomial regex backtracking on adversarial names.
_PDF_KEYWORD_RULES: list[tuple[str, DocType]] = [
    ("datasheet", DocType.EQUIPMENT_DATASHEET),
    ("specs", DocType.EQUIPMENT_SPECIFICATION_DOCUMENT),
]

# Matches Rev00, Rev01, rev.01, Rev 01, Rev000, Rev00a, etc.
_REVISION_RE = re.compile(r"rev\.?\s?(\d{1,3})([a-z])?", re.IGNORECASE)


@dataclass(frozen=True)
class Classification:
    """The result of classifying a filename."""

    doc_type: str | None
    revision_label: str | None
    revision_number: int | None


def _basename(filename: str) -> str:
    """Return the final path component, tolerating forward and back slashes."""
    return filename.replace("\\", "/").rsplit("/", 1)[-1]


def _classify_doc_type(name: str) -> str | None:
    """Return the document type for a basename, or ``None`` if nothing matches.

    Specific prefix/keyword regex rules win first; otherwise a PDF whose name contains a
    known equipment keyword is classified generically.
    """
    for pattern, label in _RULES:
        if pattern.search(name):
            return label.value
    lowered = name.lower()
    if lowered.endswith(".pdf"):
        for keyword, label in _PDF_KEYWORD_RULES:
            if keyword in lowered:
                return label.value
    return None


def classify_filename(filename: str) -> Classification:
    """Classify a filename into a document type and parse its revision.

    Args:
        filename: The original upload filename (path components are ignored).

    Returns:
        A :class:`Classification`; ``doc_type`` is ``None`` when no rule matches
        (the engineer can override it later).
    """
    name = _basename(filename)
    doc_type = _classify_doc_type(name)

    revision_label: str | None = None
    revision_number: int | None = None
    revision_match = _REVISION_RE.search(name)
    if revision_match:
        revision_label = revision_match.group(0)
        revision_number = int(revision_match.group(1))

    return Classification(
        doc_type=doc_type,
        revision_label=revision_label,
        revision_number=revision_number,
    )


def revision_sort_key(revision_number: int | None, revision_label: str | None) -> tuple[int, str]:
    """Build a sort key so the latest revision of a document is the maximum.

    Documents with no detected revision sort first (lowest). A sub-revision
    suffix (e.g. ``Rev00a``) sorts after the same plain number.

    Args:
        revision_number: Parsed revision number, or ``None``.
        revision_label: The raw revision label (may carry a trailing letter).

    Returns:
        A ``(number, suffix)`` tuple suitable for ``max``/``sorted``.
    """
    number = revision_number if revision_number is not None else -1
    suffix = ""
    if revision_label:
        match = _REVISION_RE.search(revision_label)
        if match and match.group(2):
            suffix = match.group(2).lower()
    return (number, suffix)


# Project-common inputs that are shared across all of a project's RFQs and kept for the
# life of the project. Everything else (RFQ template, datasheets, specs, unmatched) is
# RFQ-specific and only needed during generation.
_PERSISTENT_DOC_TYPES: frozenset[str] = frozenset(
    {
        DocType.EMPLOYER_TECHNICAL_SPECIFICATIONS.value,
        DocType.PROCESS_ENGINEERING_PROFILE.value,
        DocType.HYDRAULIC_CALCULATION_PROFILE.value,
        DocType.EQUIPMENT_LIST.value,
    }
)


def retention_for(doc_type: str | None) -> RetentionPolicy:
    """Return the storage retention policy for a classified document type.

    Project-common inputs are persistent; RFQ-specific inputs and unmatched files are
    transient (deleted from storage once their RFQ has been generated).
    """
    if doc_type in _PERSISTENT_DOC_TYPES:
        return RetentionPolicy.PERSISTENT
    return RetentionPolicy.TRANSIENT
