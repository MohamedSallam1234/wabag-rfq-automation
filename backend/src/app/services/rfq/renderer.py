"""Render an :class:`RFQGeneration` into a fresh ``.xlsx`` datasheet via openpyxl.

This builds a brand-new workbook (the original template's formatting/formulas are not preserved —
see the RFQ-generation docs). Each section becomes a titled block of rows under a fixed column
header so the audit metadata (confidence, structured provenance, status) travels with every value.

Cell-fill rules so no decision is silently dropped:
- ``conflict`` → the candidate values are joined in the Value column, with each candidate's
  provenance lined up positionally across the Source Document / Location / Evidence columns.
- ``vtf`` → the Value column shows the scope token (``field.value``, e.g. "VTF" / "By Vendor" /
  "Included"), defaulting to ``"VTF"`` when the model left it blank. If a vtf field also carries
  ``conflicts`` (a value found in a lower-precedence document), the token and that value are shown
  together as ``"VTF / <value>"`` with the value's provenance in the source columns — a safety net.
- otherwise → the field's own value and provenance.
"""

import io

from openpyxl import Workbook

from app.schemas.rfq import RFQField, RFQFieldConflict, RFQGeneration

_COLUMNS = [
    "Field",
    "Value",
    "Unit",
    "Confidence",
    "Source Document",
    "Location",
    "Evidence",
    "Status",
]
_VTF_DEFAULT = "VTF"
_CANDIDATE_SEP = " / "


def _cell(value: str | float | None) -> str | float:
    """Render a field value for a worksheet cell (``None`` → empty string)."""
    return "" if value is None else value


def _str(value: str | float | None) -> str:
    """Render a value as a string for joining (``None`` → empty string)."""
    return "" if value is None else str(value)


def _conflict_cells(conflicts: list[RFQFieldConflict]) -> tuple[str, str, str, str]:
    """Join the candidates positionally → ``(values, documents, locations, evidence)``.

    Each column joins the candidates in the same order, so the k-th piece of every column belongs to
    candidate k.
    """
    values = _CANDIDATE_SEP.join(_str(c.value) for c in conflicts)
    documents = _CANDIDATE_SEP.join(_str(c.source_document) for c in conflicts)
    locations = _CANDIDATE_SEP.join(_str(c.source_location) for c in conflicts)
    evidence = _CANDIDATE_SEP.join(_str(c.evidence) for c in conflicts)
    return values, documents, locations, evidence


def _field_row(field: RFQField) -> list[str | float]:
    """Build one worksheet row for a field, applying the conflict/vtf fill rules."""
    value: str | float
    document: str | float
    location: str | float
    evidence: str | float
    if field.status == "conflict" and field.conflicts:
        value, document, location, evidence = _conflict_cells(field.conflicts)
    elif field.status == "vtf":
        token = _cell(field.value) if field.value not in (None, "") else _VTF_DEFAULT
        if field.conflicts:
            # Safety net: show the VTF token alongside the value found in a lower-precedence
            # document, with that value's provenance in the source columns.
            candidate_values, document, location, evidence = _conflict_cells(field.conflicts)
            value = f"{token}{_CANDIDATE_SEP}{candidate_values}"
        else:
            value = token
            document = _cell(field.source_document)
            location = _cell(field.source_location)
            evidence = _cell(field.evidence)
    else:
        value = _cell(field.value)
        document = _cell(field.source_document)
        location = _cell(field.source_location)
        evidence = _cell(field.evidence)
    return [
        field.field,
        value,
        _cell(field.unit),
        field.confidence,
        document,
        location,
        evidence,
        field.status,
    ]


def render_xlsx(generation: RFQGeneration) -> bytes:
    """Render the generated datasheet to ``.xlsx`` bytes."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "RFQ"

    if generation.equipment_tag:
        sheet.append(["Equipment Tag", generation.equipment_tag])
    if generation.equipment_category:
        sheet.append(["Equipment Category", generation.equipment_category])
    for key, value in generation.header.items():
        sheet.append([key, value])
    if sheet.max_row >= 1 and (
        generation.header or generation.equipment_tag or generation.equipment_category
    ):
        sheet.append([])

    for section in generation.sections:
        sheet.append([section.title])
        sheet.append(list(_COLUMNS))
        for field in section.fields:
            sheet.append(_field_row(field))
        sheet.append([])

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
