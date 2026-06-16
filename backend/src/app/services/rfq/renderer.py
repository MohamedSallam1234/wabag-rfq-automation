"""Render an :class:`RFQGeneration` into a fresh ``.xlsx`` datasheet via openpyxl.

This builds a brand-new workbook (the original template's formatting/formulas are not preserved —
see the RFQ-generation docs). Each section becomes a titled block of rows under a fixed column
header so the audit metadata (confidence/source/status) travels with every value.
"""

import io

from openpyxl import Workbook

from app.schemas.rfq import RFQGeneration

_COLUMNS = ["Field", "Value", "Unit", "Confidence", "Source", "Status"]


def _cell(value: str | float | None) -> str | float:
    """Render a field value for a worksheet cell (``None`` → empty string)."""
    return "" if value is None else value


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
            sheet.append(
                [
                    field.field,
                    _cell(field.value),
                    _cell(field.unit),
                    field.confidence,
                    _cell(field.source_ref),
                    field.status,
                ]
            )
        sheet.append([])

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
