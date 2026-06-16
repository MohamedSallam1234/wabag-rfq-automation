"""Shared GitHub-flavored Markdown rendering for the office-document parsers.

Both the Word (:mod:`app.services.ingestion.word_parser`) and Excel
(:mod:`app.services.ingestion.excel_parser`) converters render tabular data as
GitHub-flavored Markdown (GFM) tables, so the cell-escaping and table-assembly
logic lives here once.
"""

from collections.abc import Sequence
from datetime import date, datetime


def escape_cell(value: object) -> str:
    r"""Render a single value as inline text safe to drop into a GFM table cell.

    ``None`` becomes an empty string, ``date``/``datetime`` use ISO 8601, and any
    other value is stringified. Pipes are escaped (``|`` → ``\\|``) and newlines
    collapsed to spaces so a value can never break the one-row-per-line structure.
    """
    if value is None:
        text = ""
    elif isinstance(value, datetime | date):
        text = value.isoformat()
    else:
        text = str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return " ".join(text.split("\n")).replace("|", "\\|")


def gfm_table(rows: Sequence[Sequence[object]]) -> str:
    """Render ``rows`` as a GFM table; the first row is the header.

    The caller must pass at least one row, all rows the same width (the header
    sets the column count; shorter rows are padded and longer rows truncated).
    """
    header = [escape_cell(cell) for cell in rows[0]]
    width = len(header)
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    for row in rows[1:]:
        cells = [escape_cell(cell) for cell in row][:width]
        cells.extend([""] * (width - len(cells)))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)
