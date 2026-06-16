"""Prompt assembly for map-reduce RFQ generation.

The operating rules live in the system prompt (``system_prompt.md``); these helpers build only the
per-stage *task*. The **map** stage extracts the fields one document supports — with the verbatim
evidence and the document's precedence tier — so the **reduce** stage can merge the per-document
partials and apply the precedence/conflict rules over that compact evidence. Neither restates the
universal rules; the reduce task spells out the precedence *algorithm* because reduce is the only
stage that sees all sources.
"""

from collections.abc import Sequence

from app.services.rfq.precedence import tier_label

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
          "source_document": string | null,
          "source_location": string | null,
          "evidence": string | null,
          "status": "extracted" | "conflict" | "tbd" | "vtf",
          "conflicts": [
            {
              "value": string | number | null,
              "source_document": string | null,
              "source_location": string | null,
              "evidence": string | null
            }
          ] | null
        }
      ]
    }
  ]
}"""


def _tier_tag(tier: int) -> str:
    """Render a document's precedence tier as an explicit, model-readable annotation."""
    return f"PRECEDENCE TIER {tier} — {tier_label(tier)}"


def _document_block(label: str, tier: int, markdown: str) -> str:
    return f"# === DOCUMENT: {label} ===\n# {_tier_tag(tier)}\n{markdown}"


def _template_block(label: str, markdown: str) -> str:
    return f"# === RFQ TEMPLATE: {label} ===\n{markdown}"


def extraction_instructions(equipment: str) -> str:
    """Map-stage task: extract the fields one document supports for ``equipment``, with evidence."""
    return (
        f'You are extracting data for the "{equipment}" RFQ datasheet from ONE source document.\n'
        f"Walk through EVERY field in the RFQ template; for each field, check whether THIS "
        f"document provides any evidence (a stated value, an explicit formula + its inputs, or a "
        f"vendor-scope indication). Emit a PARTIAL JSON object containing only the fields this "
        f"document supports -- omit fields for which it has no evidence at all (do not emit "
        f"tbd/null placeholders). Do not drop a field merely because the evidence is weak or "
        f"indirect; emit it with a lower confidence instead.\n\n"
        f"For each emitted field, record its provenance in THREE fields:\n"
        f"- source_document: this document's label (exactly as given in its block header).\n"
        f"- source_location: the most specific locator available IN THIS DOCUMENT (section/clause "
        f"heading, table or sheet name, row/column label, or nearest heading).\n"
        f'- evidence: a SHORT verbatim quote of the supporting text, e.g. "design flow 860".\n'
        f"- Set confidence by the evidence strength (0.85-1.0 explicit & unambiguous; 0.4-0.84 "
        f"weak or indirect).\n"
        f"Vendor scope / scope of supply: if the field/row reads like vendor scope -- wording such "
        f'as "scope of supply", "by vendor", "vendor to furnish/provide/supply", "by others", '
        f'"by purchaser/client", "supplied by", "included", "furnished with", "shall include" -- '
        f'set status "vtf" and FILL value with the scope token: "VTF" for a general '
        f'vendor-furnished technical field, or the document\'s own wording ("Included" / "By '
        f'Vendor" / "By Others") for a scope-of-supply row. Do NOT leave such a value null.\n'
        f"- Scope quantity/duration beats the token: if a scope item states a figure (e.g. "
        f'"spare parts for 3 years", "2 spare sets", "24 months"), extract that figure (status '
        f'"extracted"), NOT "Yes"/"Included".\n'
        f"- Materials of construction: materials may appear as names, grades, or standard codes "
        f"(GG/EN-GJL, EN 1.4xxx, AISI 3xx, SS, bronze, carbon steel, duplex, ASTM...). Apply a "
        f'blanket statement ("all wetted parts SS316") to EVERY relevant component row. Extract a '
        f"component's material when stated; otherwise the vendor furnishes it -> emit it for the "
        f"merge to mark vtf. Never invent a grade the document does not state.\n"
        f'- Use status "extracted" for an ordinary engineer-scope field with a real value.\n'
        f'- If THIS document gives a concrete value, ALWAYS emit it (status "extracted") even '
        f"when the field may be vendor scope in another document; never suppress a real value. "
        f"The merge stage makes the final vendor-scope decision.\n"
        f"- Do NOT resolve cross-document conflicts here (you only see one document); that is the "
        f'merge stage\'s job. Never emit status "conflict" at this stage.\n'
        f"- Leave equipment_tag/header null unless THIS document establishes them.\n\n"
        f"{_SCHEMA}\n\nReturn JSON only: no prose, no code fences."
    )


def extraction_message(
    equipment: str, template_label: str, template_md: str, doc_label: str, tier: int, doc_md: str
) -> str:
    """Map-stage user message: one source document (with its tier) + the template for structure."""
    return "\n\n".join(
        [
            f'Extract data for the "{equipment}" RFQ datasheet from the single document below. '
            f"The RFQ template (for field names and structure) follows it.",
            _document_block(doc_label, tier, doc_md),
            _template_block(template_label, template_md),
        ]
    )


def merge_instructions(equipment: str) -> str:
    """Reduce-stage task: merge per-document partials applying the precedence/conflict algorithm."""
    return (
        f'You are assembling the final "{equipment}" RFQ datasheet from per-document extractions.\n'
        f"Each extraction is tagged with its source document's PRECEDENCE TIER (lower number = "
        f"higher precedence). Output the COMPLETE datasheet, preserving the template's EXACT field "
        f"names, units, and section order verbatim, with EVERY template field present.\n\n"
        f"Carry each value's provenance through unchanged: source_document, source_location, and "
        f"evidence (the verbatim quote).\n"
        f"For each template field, gather the candidate values across all extractions and decide:\n"
        f"1. No candidate value from ANY source -> classify by the TEMPLATE field itself. Mark "
        f'status "vtf" (FILL value with a scope token: "VTF", or "By Vendor"/"Included" if the '
        f"template wording implies it) when EITHER the template row signals vendor scope (a "
        f'Scope/Supply column, "(by vendor)", "supplied by", a "scope of supply" heading) OR the '
        f"field is a conventionally vendor-furnished item (accessories, painting/coating, "
        f"testing & inspection, spare parts, internal motor construction, special tools, and "
        f"materials of construction whose grade the documents do not state). Otherwise status "
        f'"tbd", value null, confidence 0.0.\n'
        f'2. One candidate, or several that AGREE -> status "extracted"; keep the strongest '
        f"provenance (source_document/source_location/evidence) and the highest confidence.\n"
        f"3. Candidates DISAGREE but one is from a strictly higher precedence tier -> take the "
        f'higher-tier value (status "extracted"); the Employer\'s Requirements (tier 1) always '
        f"prevail (Golden Rule). Do not average or invent.\n"
        f"4. Candidates DISAGREE at the SAME tier (or precedence cannot resolve it) -> status "
        f'"conflict", value null, and list AT LEAST the two most-probable candidates in '
        f"conflicts[], each with its value, source_document, source_location and evidence.\n"
        f"5. Vendor scope WITH a value (safety net): if the field is vendor scope -- a "
        f"higher-precedence document marks it vendor-furnished, or it is absent from the "
        f"higher-precedence documents -- but a LOWER-precedence document supplies an actual "
        f'value, set status "vtf" with value = the scope token, AND record that lower-precedence '
        f"value in conflicts[] (with its source_document/source_location/evidence) so BOTH the "
        f"token and the value are shown. Never drop the value.\n"
        f"Scope quantity/duration beats the token: when a scope item states a figure (e.g. "
        f'"spare parts for 3 years", "24 months warranty"), use that figure as the value (status '
        f'"extracted"), not "Yes"/"Included". Materials of construction: keep a stated material '
        f'(apply a blanket "all wetted parts ..." statement to every relevant row); mark the rest '
        f'"vtf". Never invent a grade.\n\n'
        f"{_SCHEMA}\n\nReturn JSON only: no prose, no code fences."
    )


def merge_message(
    equipment: str,
    template_label: str,
    template_md: str,
    partials: Sequence[tuple[str, int, str]],
) -> str:
    """Reduce-stage user message: per-document partial JSONs (with tiers) + the template to fill.

    ``partials`` is a sequence of ``(document_label, precedence_tier, partial_json)`` triples from
    the map stage.
    """
    parts = [
        f'Assemble the complete "{equipment}" RFQ datasheet. Below are per-document extractions '
        f"(each tagged with its precedence tier), followed by the RFQ template whose every field "
        f"must appear in your output.",
    ]
    for label, tier, partial_json in partials:
        parts.append(f"# === EXTRACTION FROM: {label} ===\n# {_tier_tag(tier)}\n{partial_json}")
    parts.append(_template_block(template_label, template_md))
    return "\n\n".join(parts)
