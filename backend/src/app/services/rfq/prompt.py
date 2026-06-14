"""Prompt assembly for map-reduce RFQ generation.

The operating rules live in the system prompt (``system_prompt.md``); these helpers build only the
per-stage *task*. The **map** stage extracts the fields one document supports; the **reduce** stage
merges the per-document partials and fills the complete datasheet. Neither restates the rules.
"""

from collections.abc import Sequence

_SCHEMA = """\
The JSON object shape is:

{
  "equipment_tag": string | null,
  "equipment_category": string | null,
  "header": { string: string },
  "sections": [
    {
      "title": string,
      "fields": [
        {
          "field": string,
          "value": string | number | null,
          "unit": string | null,
          "confidence": number,
          "source_ref": string | null,
          "status": "extracted" | "conflict" | "tbd",
          "conflicts": [ { "value": string | number | null, "source_ref": string | null } ] | null
        }
      ]
    }
  ]
}"""


def _document_block(label: str, markdown: str) -> str:
    return f"# === DOCUMENT: {label} ===\n{markdown}"


def _template_block(label: str, markdown: str) -> str:
    return f"# === RFQ TEMPLATE: {label} ===\n{markdown}"


def extraction_instructions(equipment: str) -> str:
    """Map-stage task: extract the fields one document supports for ``equipment``."""
    return (
        f'You are extracting data for the "{equipment}" RFQ datasheet from ONE source document.\n'
        f"Using only the single document in the user message, extract the template fields you find "
        f"evidence for. Return a PARTIAL JSON object containing ONLY the fields actually supported "
        f"by this document (omit fields not present); set each field's source_ref to its location "
        f"in this document. Do not emit tbd/null placeholder fields.\n\n"
        f"{_SCHEMA}\n\nReturn JSON only: no prose, no code fences."
    )


def extraction_message(
    equipment: str, template_label: str, template_md: str, doc_label: str, doc_md: str
) -> str:
    """Map-stage user message: one source document + the template for field names/structure."""
    return "\n\n".join(
        [
            f'Extract data for the "{equipment}" RFQ datasheet from the single document below. '
            f"The RFQ template (for field names and structure) follows it.",
            _document_block(doc_label, doc_md),
            _template_block(template_label, template_md),
        ]
    )


def merge_instructions(equipment: str) -> str:
    """Reduce-stage task: merge per-document partials and fill the complete datasheet."""
    return (
        f'You are assembling the final "{equipment}" RFQ datasheet from per-document extractions.\n'
        f"Merge the partial extractions in the user message, applying the source-precedence and "
        f"conflict rules. Emit EVERY field of the template — fill the supported ones and mark the "
        f'rest with value null, status "tbd", confidence 0.0. Return ONE complete JSON object.\n\n'
        f"{_SCHEMA}\n\nReturn JSON only: no prose, no code fences."
    )


def merge_message(
    equipment: str,
    template_label: str,
    template_md: str,
    partials: Sequence[tuple[str, str]],
) -> str:
    """Reduce-stage user message: per-document partial JSONs + the template to fill.

    ``partials`` is a sequence of ``(document_label, partial_json)`` pairs from the map stage.
    """
    parts = [
        f'Assemble the complete "{equipment}" RFQ datasheet. Below are per-document extractions, '
        f"followed by the RFQ template whose every field must appear in your output.",
    ]
    for label, partial_json in partials:
        parts.append(f"# === EXTRACTION FROM: {label} ===\n{partial_json}")
    parts.append(_template_block(template_label, template_md))
    return "\n\n".join(parts)
