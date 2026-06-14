"""Tests for rendering an RFQGeneration into a fresh .xlsx datasheet."""

import io

from openpyxl import load_workbook

from app.schemas.rfq import RFQField, RFQGeneration, RFQSection
from app.services.rfq.renderer import render_xlsx


def _generation() -> RFQGeneration:
    return RFQGeneration(
        equipment_tag="B-100",
        equipment_category="Blower",
        header={"Project": "Kohafa WWTP", "Client": "WABAG"},
        sections=[
            RFQSection(
                title="Process Data",
                fields=[
                    RFQField(
                        field="Capacity",
                        value=860,
                        unit="m3/hr",
                        confidence=0.9,
                        source_ref="04_Hydraulic",
                        status="extracted",
                    ),
                    RFQField(field="Material", value=None, status="tbd"),
                ],
            )
        ],
    )


def test_render_xlsx_contains_header_section_and_fields() -> None:
    data = render_xlsx(_generation())

    workbook = load_workbook(io.BytesIO(data))
    sheet = workbook.active
    flat = [str(cell.value) for row in sheet.iter_rows() for cell in row if cell.value is not None]

    assert "Kohafa WWTP" in flat  # header value
    assert "Process Data" in flat  # section title
    assert {"Field", "Value", "Unit", "Confidence", "Source", "Status"} <= set(flat)
    assert "Capacity" in flat  # field label
    assert "860" in flat  # field value
    assert "extracted" in flat  # status of a filled field
    assert "tbd" in flat  # status of an empty field


def test_render_xlsx_is_a_valid_xlsx_container() -> None:
    data = render_xlsx(_generation())
    assert data.startswith(b"PK\x03\x04")  # OOXML/ZIP magic
