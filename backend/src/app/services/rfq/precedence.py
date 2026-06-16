"""Source-precedence ladder for RFQ extraction (the SRS ``F-04`` precedence hierarchy).

When the same field appears in several documents, the higher-precedence source wins (Rule 2 /
Employer's Golden Rule). This module is the single source of truth for that ordering: it maps a
document's :class:`~app.services.ingestion.classifier.DocType` to an integer **tier** (lower number
= higher precedence) so the precedence becomes explicit metadata stamped on every document block,
rather than something the model must guess from a filename.

The ladder mirrors the SRS Rule 2:

============  ===============================================================
Tier          Document type
============  ===============================================================
1 (golden)    Employer Technical Specifications
2             Process Engineering Profile
3             Hydraulic Calculation Profile
4             Equipment List
5             Other / unclassified documents (datasheets, general specs, and
              anything the classifier could not map all fall here)
6 (lowest)    Industry engineering standards (IEC / ISO / DIN / …)
============  ===============================================================

Datasheets and general specifications do not have a dedicated tier: their content lives in the
Employer's Technical Specifications, so any uploaded separately resolve to the default ("other")
tier.

Industry standards are not a ``DocType`` (they are *cited inside* documents, not uploaded as files);
tier 6 exists so the prompt can tell the model that a value justified only by a standard is the
lowest-precedence tier and loses to anything stated in an uploaded document.
"""

from app.services.ingestion.classifier import DocType

#: Tier assigned to a value justified only by an industry standard (IEC/ISO/DIN/…) — the lowest.
STANDARDS_TIER = 6
#: Tier for documents whose type we could not map (datasheets/specs and unclassified files) — below
#: the core engineering inputs but above raw industry standards.
_DEFAULT_TIER = 5

_TIER_BY_DOC_TYPE: dict[str, int] = {
    DocType.EMPLOYER_TECHNICAL_SPECIFICATIONS.value: 1,
    DocType.PROCESS_ENGINEERING_PROFILE.value: 2,
    DocType.HYDRAULIC_CALCULATION_PROFILE.value: 3,
    DocType.EQUIPMENT_LIST.value: 4,
}

_TIER_LABELS: dict[int, str] = {
    1: "Employer's Requirements / Project Specifications (highest — Golden Rule)",
    2: "Process Engineering",
    3: "Hydraulic Profile",
    4: "Equipment List",
    5: "Other / Unclassified",
    STANDARDS_TIER: "Industry Engineering Standards (lowest)",
}


def precedence_tier(doc_type: str | None) -> int:
    """Return the precedence tier for a document type (lower = higher precedence).

    Unknown/unclassified types — and datasheet/general-spec doc types, which no longer have a
    dedicated tier — fall to :data:`_DEFAULT_TIER`. Industry standards (:data:`STANDARDS_TIER`) are
    never a ``doc_type`` — they are handled by the prompt, not by this lookup.
    """
    if doc_type is None:
        return _DEFAULT_TIER
    return _TIER_BY_DOC_TYPE.get(doc_type, _DEFAULT_TIER)


def tier_label(tier: int) -> str:
    """Return a short human label for a precedence tier (for stamping document blocks)."""
    return _TIER_LABELS.get(tier, "Unclassified")
