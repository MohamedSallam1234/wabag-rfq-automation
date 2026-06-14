"""Pydantic schemas for RFQ generation: the LLM's JSON output and the API response.

``RFQGeneration`` (and its nested models) is the structured datasheet the LLM must return — one
section per template section, one field per template field, each carrying the F-04 traceability
metadata (``confidence``/``source_ref``/``status``/``conflicts``). ``RFQGenerationResponse`` is what
the endpoint returns: the persisted document plus a status summary.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.document import DocumentRead

FieldStatus = Literal["extracted", "conflict", "tbd"]


class RFQFieldConflict(BaseModel):
    """A single conflicting candidate value preserved when sources disagree."""

    value: str | float | None = None
    source_ref: str | None = None


class RFQField(BaseModel):
    """One datasheet field with its value and F-04 traceability metadata."""

    model_config = ConfigDict(extra="ignore")

    field: str
    value: str | float | None = None
    unit: str | None = None
    confidence: float = 0.0
    source_ref: str | None = None
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


class RFQGenerationResponse(BaseModel):
    """API response for a generation request: the persisted document + a status summary."""

    document: DocumentRead
    summary: RFQSummary
