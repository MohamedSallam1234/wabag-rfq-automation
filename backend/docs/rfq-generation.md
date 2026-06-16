# RFQ Generation (v1 — map-reduce)

> Feature spec: see **F-03 / F-06** in the top-level `README.md`. This doc describes the v1
> implementation.

## What it does

Generates a populated RFQ datasheet (Excel) for **one named equipment** from a project's uploaded
documents. Extraction and generation are fused — there is no separate equipment table — but the
work is **map-reduce** across LLM calls so a whole project's documents never have to fit in one
call: each source document is extracted in parallel, then a single merge+fill call assembles the
datasheet.

Engineer workflow:

1. Create a project and upload the source documents (`01_*` employer specs, `02_*` process,
   `04_*` hydraulic, `03_*` equipment list) via `POST /api/v1/projects/{id}/documents` — each is
   converted to Markdown and stored (F-01).
2. At generation time, call the endpoint below with the **RFQ template file** and the **equipment
   name**.

## Endpoint

```
POST /api/v1/projects/{project_id}/rfqs
Content-Type: multipart/form-data
  file:      the RFQ template (.pdf/.docx/.xlsx/.xls)   ← converted to Markdown in-memory, NOT stored
  equipment: the equipment name, e.g. "aeration blower"  (form field)
```

Flow:

1. Validate + convert the uploaded template to Markdown in-memory (reuses the F-01 intake pipeline);
   the template is **transient** — never persisted.
2. Resolve the source set: every project source document (excludes previously-generated
   `RFQ Package` outputs), each downloaded from storage and decoded to Markdown. Each source carries
   a **precedence tier** (see `services/rfq/precedence.py`). A project with no source documents is a
   `422`.
3. **Map (parallel):** one LLM call per source document extracts only the template fields that
   document supports → a *partial* `RFQGeneration`. Each emitted field carries structured provenance
   (`source_document` / `source_location` / `evidence` quote); the document's **precedence tier** is
   stamped on the prompt block. These run concurrently via `asyncio.gather` (pure async — no threads),
   bounded
   by `RFQ_MAX_CONCURRENT_EXTRACTIONS`.
4. **Reduce (one call):** merges the per-document partials — each tagged with its precedence tier —
   against the template, applying the **precedence / Employer's-Golden-Rule / conflict** algorithm
   over the partials' compact evidence, and fills the complete datasheet (every template field,
   `tbd` where nothing was found, `vtf` for vendor-scope fields). The universal operating rules come
   from the system prompt (`agents/llm/system_prompt.md` → `SYSTEM_RULES`); the per-stage task
   instructions frame the task, the JSON contract, and (for reduce) the precedence algorithm.
5. Parse the model's JSON into `RFQGeneration`, render a **fresh `.xlsx`** (openpyxl), upload it, and
   persist a `documents` row (`doc_type="RFQ Package"`, `content_type` = the xlsx OOXML type,
   `retention=persistent`).

Response (`201`): the created document + a status summary.

```jsonc
{
  "document": { /* DocumentRead — id, original_filename "RFQ_aeration_blower.xlsx", content_type, … */ },
  "summary":  { "fields_total": 42, "extracted": 30, "conflict": 2, "tbd": 8, "vtf": 2 }
}
```

Fetch the file via the existing `GET /api/v1/documents/{id}` (returns a short-lived signed URL).

Status codes: `201` ok; `404` project missing; `415` unsupported template type; `422` unparseable
template or project has no source documents (or missing `equipment`); `502` the model returned
invalid JSON or a storage op failed; `503` the LLM is unavailable.

## The `RFQGeneration` JSON contract

The model must return a single JSON object (no prose, no code fences):

```jsonc
{
  "equipment_tag": "B-100" | null,
  "equipment_category": "Blower" | null,
  "header": { "Project": "Kohafa WWTP", "Client": "WABAG" },
  "sections": [
    {
      "title": "Process Data",
      "fields": [
        {
          "field": "Capacity",
          "value": 860,                       // string | number | null
          "unit": "m3/hr",
          "confidence": 0.9,                  // 0.0–1.0
          "source_document": "04_Hydraulic",  // which document
          "source_location": "Sheet Design, row Flow", // where in it (section/sheet/row/heading)
          "evidence": "design flow 860 m3/hr",// short verbatim quote
          "status": "extracted",              // "extracted" | "conflict" | "tbd" | "vtf"
          "conflicts": null                   // [{value, source_document, source_location, evidence}, …] when "conflict"
        }
      ]
    }
  ]
}
```

The operating rules (source-of-truth / no invention, source precedence + Employer's Golden Rule,
evidence & traceability via structured `source_document` / `source_location` / `evidence`, unit
validation, VTF/scope → `status:"vtf"` with a filled token, calculations, conflict handling with
≥2 candidates, confidence bands, status semantics) live in `system_prompt.md` and
are prepended to every call. The **precedence ladder** is the single source of truth in
`services/rfq/precedence.py` (Employer's Requirements → Process → Hydraulic → Equipment List →
other/unclassified → Industry Standards) and is stamped onto every source/partial as an
explicit tier so the reduce stage applies precedence deterministically rather than guessing from
filenames.

**VTF / scope of supply.** VTF is a property of the *template field*, so the **reduce** stage decides
it for every template field — including fields no source mentions (it would otherwise default them to
`tbd`). A field is marked `vtf` when the template signals vendor scope (a Scope/Supply column,
"(by vendor)", "supplied by", "scope of supply") **or** it is a conventionally vendor-furnished item
(accessories, painting, testing, spares, internal motor build, **materials of construction** whose
grade the documents don't state); the cell shows the token (`VTF` / `By Vendor` / `Included`).
**Scope quantities:** when a scope item states a figure (e.g. "spare parts for 3 years", "24 months
warranty"), that figure is captured as the value (`extracted`) rather than a generic token.
**Safety net:** when a vendor-scope field also has a value in a lower-precedence document, the value
is carried in `conflicts[]` and the cell renders `VTF / <value>` with that value's provenance in the
source columns — so a real value is never silently dropped.

## Limitations (v1) / follow-ups

- **No template fidelity.** The output is a freshly-built `.xlsx`; the engineer's original styling,
  formulas, and merged cells are not preserved. (Follow-up: load + fill the uploaded `.xlsx` in
  place.)
- **A single document larger than the context window.** Map-reduce bounds the *cross-document* sum,
  but one document (e.g. a 1000-page spec) must still fit in its own extraction call. If it doesn't,
  that call fails. (Follow-up: intra-document chunking.) Also note the Excel empty-cell-trim fix only
  applies to *new* uploads — **re-upload** older spreadsheets so a single sheet isn't bloated.
- **Synchronous + slow.** The run makes N+1 large calls; wall-clock ≈ the slowest extraction + the
  merge (`LLM_TIMEOUT_S` defaults to 1800s). The worker is held for the duration and any reverse
  proxy must allow long requests. (Follow-up: background-job generation.)
- **Cost.** N+1 calls and the (small) template is repeated per call.
- **One equipment per call.** (Follow-up: batch multiple templates.)

## Operational notes

- **Extended thinking is on by default** (`LLM_REASONING_EFFORT=high`) for every LLM call — it
  improves extraction/merge reasoning at the cost of more tokens and latency. Set
  `LLM_REASONING_EFFORT=none` to disable, or `low`/`medium` to dial it down. Note: thinking does
  **not** change the input context limit — it doesn't help with "prompt too long" errors.
- The storage bucket's `allowed_mime_types` must include the spreadsheet OOXML type
  (`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`) in addition to
  `text/markdown` — generated RFQ outputs are stored as `.xlsx` (see `document-intake.md` §7.1).
