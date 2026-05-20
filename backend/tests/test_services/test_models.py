"""Tests for ORM model column definitions."""

import pytest

from app.models.document import Document


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        ("status", {"pending", "processing", "ready", "failed"}),
        ("doc_type_source", {"auto", "manual"}),
        ("retention", {"persistent", "transient"}),
    ],
)
def test_document_enum_columns_persist_lowercase_values(column: str, expected: set[str]) -> None:
    """Enum columns must bind lowercase values, matching the Postgres enum labels.

    Without ``values_callable`` SQLAlchemy would bind member names (e.g. ``FAILED``),
    which the DB enum (``failed``) rejects.
    """
    enum_type = Document.__table__.c[column].type
    assert set(enum_type.enums) == expected
