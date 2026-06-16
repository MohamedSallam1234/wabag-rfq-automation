"""Pydantic schemas for RFQ generation: the LLM's JSON output and the API response.

``RFQGeneration`` (and its nested models) is the structured datasheet the LLM must return — one
section per template section, one field per template field, each carrying the F-04 traceability
metadata (``confidence``/``status``/``conflicts`` plus structured provenance:
``source_document``/``source_location``/``evidence``). ``RFQGenerationResponse`` is what the
endpoint returns: the persisted document plus a status summary.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.document import DocumentRead

FieldStatus = Literal["extracted", "conflict", "tbd", "vtf"]


class RFQFieldConflict(BaseModel):
    """A single conflicting candidate value preserved when sources disagree, with its provenance."""

    value: str | float | None = None
    source_document: str | None = None
    source_location: str | None = None
    evidence: str | None = None


class RFQField(BaseModel):
    """One datasheet field with its value and F-04 traceability metadata.

    ``status`` semantics: ``extracted`` (a document-backed value), ``conflict`` (sources disagree —
    ``value`` is null and ``conflicts`` lists the candidates), ``tbd`` (no evidence — ``value``
    null), ``vtf`` (vendor-scope field, "Vendor to Furnish" — value carries the scope token).

    Provenance is structured: ``source_document`` (which document), ``source_location`` (where in it
    — section/sheet/row/heading), and ``evidence`` (a short verbatim quote of the supporting text).
    """

    model_config = ConfigDict(extra="ignore")

    field: str
    value: str | float | None = None
    unit: str | None = None
    confidence: float = 0.0
    source_document: str | None = None
    source_location: str | None = None
    evidence: str | None = None
    status: FieldStatus = "tbd"
    conflicts: list[RFQFieldConflict] | None = None


class RFQSection(BaseModel):
    """A named group of fields, mirroring a section of the RFQ template."""

    model_config = ConfigDict(extra="ignore")

    title: str
    fields: list[RFQField] = Field(default_factory=list)


class RFQGeneration(BaseModel):
    """The full structured datasheet the LLM returns for one equipment template."""

    model_config = ConfigDict(extra="ignore")

    equipment_tag: str | None = None
    equipment_category: str | None = None
    header: dict[str, str] = Field(default_factory=dict)
    sections: list[RFQSection] = Field(default_factory=list)


class RFQSummary(BaseModel):
    """Counts of field statuses across the generated datasheet."""

    fields_total: int
    extracted: int
    conflict: int
    tbd: int
    vtf: int


class RFQGenerationResponse(BaseModel):
    """API response for a generation request: the persisted document + a status summary."""

    document: DocumentRead
    summary: RFQSummary
