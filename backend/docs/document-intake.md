# Document Intake — Upload & Classification (PD-32)

The first stage of the RFQ pipeline (`Upload → Classify → Extract → Generate`).
Engineers upload a project's source documents (employer requirements, process
engineering, equipment lists, hydraulic profiles, RFQ templates, datasheets); the
backend validates the bytes, stores them in Supabase Storage, and auto-classifies
them by filename — all in a single synchronous request.

---

## TL;DR

- **Scope:** Upload + Classify only. Extraction/generation are out of scope.
- **Hierarchy:** `Project 1:M Document` (per the SRS). No `RFQ` table in this feature.
- **One synchronous endpoint.** The client `POST`s the file (multipart) to the backend;
  the backend validates the content, uploads the validated bytes to Supabase Storage,
  classifies the filename, and returns the created document — in one round trip. There is
  **no** `init`/`finalize` handshake, no signed-upload URL, no background task, and no polling.
- **Validate-before-store.** Validation is `extension allow-list` → `magic bytes` →
  `deep parse` (`PyMuPDF`/`openpyxl`/`python-docx`), with a request-body size cap. An invalid
  file is rejected synchronously (`415`/`422`/`413`) and **nothing is ever stored** — so
  every persisted document is valid and has bytes (no `status` lifecycle to track).
- **PDFs are slimmed to Markdown at upload.** Employer specs can be 500–1000+ pages and bloated
  by images/figures/embedded fonts. Born-digital PDFs are converted to a compact Markdown
  artifact (text **and tables** preserved) via `pymupdf4llm`; only that `.md` is stored
  (`content_type=text/markdown`) and the heavy original is discarded — cutting both storage and
  LLM tokens. A scanned / image-only PDF (no extractable text) is rejected `422` (no OCR).
  `.docx/.xlsx/.xls` are unchanged (stored as-is) for now.
- **Classification** is deterministic filename-prefix matching (no LLM), e.g. `01_*` →
  *Employer Technical Specifications*, `03_RFQ*` → *RFQ Template*. Engineers can override.
- **Retention:** project-common docs (`01`/`02`/`04`/`05`) are `persistent`; RFQ-specific
  docs (RFQ template, datasheets, specs) and unmatched files are `transient` (to be deleted
  after the RFQ is generated). Derived from classification; recomputed on override.
- **No authentication.** Every `/api/v1/**` endpoint is **open** — anyone who can reach the
  server can list, upload, download, and delete any document. (Suitable for a prototype/demo,
  or with auth enforced at a gateway/proxy in front of the service.)
- **Endpoints:** projects CRUD-lite + `upload`/list/detail/`PATCH`(override)/`DELETE` for
  documents, all under `/api/v1`.
- **Frontend devs:** see [§3 Frontend integration guide](#3-frontend-integration-guide) for
  the browser flow, TypeScript types, and error handling.
- **Before it runs anywhere:** create the private Supabase bucket (with size/MIME limits) and
  run `uv run alembic upgrade head`. See [§7 Setup](#7-setup).

---

## 1. What was built

| File | Purpose |
|---|---|
| `src/app/models/project.py` | `Project` ORM model (name, location, client, consultant, project_number, capacity). |
| `src/app/models/document.py` | `Document` ORM model + `DocTypeSource` / `RetentionPolicy` enums (enum columns persist lowercase values via `values_callable`). |
| `src/app/models/__init__.py` | Registers `Project` and `Document` so Alembic autogenerate sees them. |
| `src/app/services/ingestion/classifier.py` | Pure filename → `(doc_type, revision_label, revision_number)`; `DocType` enum of known labels; `retention_for(doc_type)` policy. |
| `src/app/services/ingestion/filetype.py` | Magic-byte sniffing + extension/MIME helpers (no native `libmagic`). |
| `src/app/services/ingestion/excel_parser.py` / `word_parser.py` | Deep-parse helpers for office files; opening the file is the integrity check. |
| `src/app/services/ingestion/pdf_text.py` | `extract_pdf_markdown()` — born-digital PDF → Markdown (text + tables) via `pymupdf4llm` (also the PDF integrity check); raises `NoExtractableTextError` for scanned/image-only PDFs. |
| `src/app/services/ingestion/validation.py` | `validate_upload_bytes()` — streams the upload to a temp file (incoming-size guard), checks magic bytes, deep-parses, slims PDFs to Markdown, enforces the stored-artifact cap; `plan_storage_path()`; `UploadValidationError`. |
| `src/app/core/supabase.py` | `create_supabase_client()` — secret-key async client built once in the lifespan. |
| `src/app/api/deps.py` | `get_db` / `get_storage` / `get_router` dependencies + `load_project_or_404` / `load_document_or_404`. |
| `src/app/api/v1/projects.py` | Project create / list / get. |
| `src/app/api/v1/documents.py` | `upload` (validate → store → classify → persist) / list / detail / `PATCH` (override) / `DELETE`. |
| `src/app/api/v1/router.py` | Aggregates the v1 routers; included by `main.py`. |
| `src/app/schemas/project.py` / `document.py` | Pydantic response models (`storage_bucket`/`storage_path` are never exposed). |
| `src/app/core/config.py` | Storage/upload settings (bucket, body-size cap, download-URL TTL, client timeout, allowed extensions). |
| `src/app/main.py` | Lifespan creates/closes the Supabase client and includes the v1 router. |
| `alembic/versions/0001_initial_schema.py` | Single migration: `app_user` role, enum types, `projects` + `documents`, indexes, FK, and explicit `app_user` GRANTs. |
| `tests/test_services/*`, `tests/test_api/*`, `tests/test_core/*` | 138 tests, ~97% coverage, no live Postgres/Supabase. |
| `.env.example`, `pyproject.toml` | Storage/LLM/CORS env keys; `openpyxl` + `pymupdf` mypy overrides; `pymupdf4llm` dep. |

### Architecture in one picture

```text
  ┌──────────┐  POST .../documents  (multipart: file)   ┌──────────────┐
  │  Client  │ ───────────────────────────────────────► │   Backend    │
  │ (web/UI) │                                           │  (FastAPI)   │
  └──────────┘                                           └──────┬───────┘
       ▲                                                        │ 1. ext allow-list  → 415
       │                                                        │ 2. load project    → 404
       │                                                        │ 3. stream to temp file,
       │                                                        │    incoming size   → 413
       │                                                        │ 4. magic bytes     → 422
       │                                                        │ 5. deep parse      → 422
       │                                                        │ 6. PDF → Markdown   → 422 (no text)
       │                                                        │    + stored-size    → 413
       │                                                        │ 7. classify filename
       │                                                        ▼
       │                                                 ┌─────────────────┐
       │                                                 │ Supabase Storage│  8. upload the artifact
       │                                                 │ (private bucket)│   (.md for PDFs) → 502
       │                                                 └────────┬────────┘
       │     201 Created (the persisted Document)                │ 9. insert row, commit
       └─────────────────────────────────────────────────────────
```

Invalid files never reach storage (steps 1–6 reject first); the row is inserted only after
the bytes are safely stored (step 8), so there is no "pending" or "failed" state to reconcile.

---

## 2. API reference

**No authentication.** Every endpoint below is open — no `Authorization` header, no
owner-scoping. A missing project/document returns **404**.

### Projects

| Method & path | Purpose |
|---|---|
| `POST /api/v1/projects` | Create a project. |
| `GET /api/v1/projects` | List all projects (newest first). |
| `GET /api/v1/projects/{project_id}` | Fetch one (404 if missing). |

### Documents

| Method & path | Purpose | Notable responses |
|---|---|---|
| `POST /api/v1/projects/{project_id}/documents` | **Upload** (multipart, field `file`): validate → (PDF→Markdown) → store → classify → persist. | `201` (the document); `415` bad extension; `422` content/extension mismatch, unparseable, or a PDF with no extractable text; `413` body over the incoming cap or artifact over the stored cap; `404` project missing; `502` storage upload failed. |
| `GET /api/v1/projects/{project_id}/documents` | List a project's documents (classification), newest first. | `200`; `404` project missing. |
| `GET /api/v1/documents/{document_id}` | Document metadata + a short-lived signed **download** URL. | `200`; `404`; `502` if a download URL can't be minted. |
| `PATCH /api/v1/documents/{document_id}` | Override classification (`doc_type`); sets `doc_type_source=manual`, recomputes `retention`. | `200`; `422` unknown `doc_type`. |
| `DELETE /api/v1/documents/{document_id}` | Delete the row + best-effort remove the storage object (orphans on storage failure are logged). | `204`. |

### Upload request / response

```jsonc
// POST /api/v1/projects/{project_id}/documents
//   Content-Type: multipart/form-data; the file is field "file"
//   curl -F "file=@01_Employer_Technical_Specifications_Rev02.pdf"

// 201 Created  (DocumentRead)
{
  "id": "…",
  "project_id": "…",
  "original_filename": "01_Employer_Technical_Specifications_Rev02.pdf",
  "content_type": "text/markdown",  // PDFs are slimmed to a .md artifact; office files keep their MIME
  "size_bytes": 48000,              // the .md size (far smaller than the original PDF)
  "doc_type": "Employer Technical Specifications",
  "doc_type_source": "auto",
  "revision_label": "Rev02",
  "revision_number": 2,
  "page_count": 12,          // the original PDF's page count
  "sheet_names": null,       // .xlsx returns its sheet names here instead
  "retention": "persistent",
  "created_at": "…",
  "updated_at": "…"
}
```

> The stored object for a PDF is `{project_id}/{document_id}.md` (`text/markdown`); the
> `download_url` therefore serves Markdown, not the original PDF. `original_filename` keeps the
> `.pdf` name (and drives classification).

The document detail endpoint adds a `download_url` (signed, short-lived). Since every stored
document has bytes, the URL is always populated; if signing fails the endpoint returns `502`.

---

## 3. Frontend integration guide

Intake is now a single multipart `POST` — plain HTTP, no token, no direct-to-Supabase step.

### 3.1 TypeScript types

```ts
type DocTypeSource   = "auto" | "manual";
type RetentionPolicy = "persistent" | "transient";

interface DocumentRead {
  id: string;
  project_id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number | null;
  doc_type: string | null;           // null until classified/overridden
  doc_type_source: DocTypeSource;
  revision_label: string | null;
  revision_number: number | null;
  page_count: number | null;         // PDFs
  sheet_names: string[] | null;      // .xlsx
  retention: RetentionPolicy;
  created_at: string;                // ISO-8601
  updated_at: string;
}

interface DocumentDetail extends DocumentRead {
  download_url: string;              // signed, short-lived
}
```

### 3.2 Upload a document

```ts
const API_BASE = "/api/v1";

/** Upload one file; resolves with the created (already-validated) document. */
async function uploadDocument(projectId: string, file: File): Promise<DocumentRead> {
  const form = new FormData();
  form.append("file", file);                       // field name MUST be "file"

  const res = await fetch(`${API_BASE}/projects/${projectId}/documents`, {
    method: "POST",
    body: form,                                     // do NOT set Content-Type; the browser
  });                                               // sets the multipart boundary itself
  if (!res.ok) throw await apiError(res);           // 415 / 422 / 413 / 404 / 502
  return res.json();                                // 201 — fully classified, bytes stored
}

async function apiError(res: Response): Promise<Error> {
  const detail = await res.json().then((b) => b?.detail).catch(() => res.statusText);
  return Object.assign(new Error(detail), { status: res.status });
}
```

### 3.3 Other operations

```ts
// List a project's documents (newest first)
const docs: DocumentRead[] = await fetch(
  `${API_BASE}/projects/${projectId}/documents`,
).then((r) => r.json());

// Override a misclassified document (doc_type must be one of the known labels — see §5)
await fetch(`${API_BASE}/documents/${documentId}`, {
  method: "PATCH",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ doc_type: "Equipment List" }), // 422 if not a valid label
});

// Download: fetch detail → use the short-lived signed download_url
const detail: DocumentDetail = await fetch(
  `${API_BASE}/documents/${documentId}`,
).then((r) => r.json());
window.open(detail.download_url, "_blank"); // re-fetch detail if it expires

// Delete
await fetch(`${API_BASE}/documents/${documentId}`, { method: "DELETE" });
```

### 3.4 Error handling

| Code | Meaning | What the UI should do |
|---|---|---|
| `404` | Project/document not found | Treat as "doesn't exist". |
| `415` | Extension not allowed | Tell the user the allowed types (`.pdf/.docx/.xlsx/.xls`). |
| `422` | Content doesn't match the extension, the file is unparseable, or a PDF has no extractable **text layer** (image-only: scanned, "Print to PDF", or text-as-outlines) | Ask for a valid file of the stated type; for PDFs, a **text-based** PDF (or the original Word/Excel source). The message names the likely cause. |
| `413` | Body over the incoming cap (`MAX_UPLOAD_SIZE_MB`) or the stored artifact over `MAX_STORED_ARTIFACT_MB` | Show the relevant limit. |
| `502` | Storage upload/sign failed (transient) | Retry shortly. |

### 3.5 Gotchas

- **Field name is `file`.** The multipart part must be named `file`.
- **Don't set `Content-Type` manually** on the upload — let the browser set the multipart
  boundary (only relevant if you hand-build the request instead of using `FormData`).
- **Upload is synchronous and authoritative.** A `201` means the file is validated *and*
  stored; there is no follow-up poll. A `4xx` means nothing was stored — just re-try with a
  corrected file.

---

## 4. Data model

`Project 1:M Document` (CASCADE delete). UUID primary keys, timezone-aware timestamps.

**`projects`** — `id`, `name`, `location?`, `client?`, `consultant?`, `project_number?`,
`capacity_m3d?`, `created_at`, `updated_at`.

**`documents`** — `id` (also the storage object name), `project_id → projects.id
(CASCADE, indexed)`, `original_filename`, `storage_bucket`, `storage_path`,
`content_type`, `size_bytes?`, `doc_type?` (indexed, **plain string** so the taxonomy can
evolve without migrations), `doc_type_source` (`auto`/`manual` enum), `revision_label?`,
`revision_number?`, `page_count?`, `sheet_names?` (JSONB), `retention`
(`persistent`/`transient` enum), `created_at`, `updated_at`.

> **Enum storage:** the `doc_type_source` / `retention` columns use real Postgres enum types
> whose labels are the **lowercase values** (`auto`, not `AUTO`); the ORM binds values via
> `values_callable` so they match. There is **no** `document_status` enum — a stored document
> is always valid.
>
> **No `owner_id` / `uploaded_by`.** Ownership was removed with authentication; documents
> belong only to their project.

### Retention policy

`retention` is derived from the classification (`retention_for(doc_type)`) at upload and
**recomputed when the classification is overridden** via `PATCH`:

| Retention | Documents | Lifecycle |
|---|---|---|
| `persistent` | Project-common inputs: `01_*` Employer, `02_*` Process, `04_*` Hydraulic, `05_*` Equipment List (and, later, the generated RFQ output) | Kept for the life of the project. |
| `transient` | RFQ-specific inputs: RFQ template (`03_RFQ*`), datasheets, specs, and any **unmatched** file | Needed only during generation; **deleted from storage once the RFQ has been generated**. |

The deletion of `transient` objects happens in the **Generate** feature (the `retention` tag
is the hook); intake only records the policy.

---

## 5. Classification rules

Deterministic, ordered, first-match-wins (`src/app/services/ingestion/classifier.py`).
**Tender-section patterns (SectionII–SectionVII) are intentionally excluded** (out of scope).
These labels are also the valid values for the `PATCH` override (`DocType` enum).

| Pattern (case-insensitive) | `doc_type` |
|---|---|
| `01_*` | Employer Technical Specifications |
| `02_*` | Process Engineering Profile |
| `03_RFQ*` | RFQ Template |
| `04_*` | Hydraulic Calculation Profile |
| `05_*` | Equipment List |
| `General Motors Specs*` | General Motor Specifications |
| `GENERAL MECHANICAL WORKS*` | General Mechanical Works Specs |
| `Local control panels DataSheet*` | Local Control Panel DataSheet |
| `Authorization letter*` | RFQ Authorization Letter |
| `*DataSheet*.pdf` | Equipment DataSheet |
| `*Specs*.pdf` | Equipment Specification Document |
| *(no match)* | `null` (engineer sets it via `PATCH`) |

**Revision detection** parses `Rev00`, `Rev01`, `rev.01`, `Rev 02`, `Rev000`, `Rev00a`,
etc. → `revision_number` (int) + `revision_label` (raw text). `revision_sort_key()` gives
a "latest = active" ordering helper (a sub-revision letter like `a` sorts after the plain
number).

---

## 6. Design decisions you should know about

1. **Single synchronous upload, validate-before-store.** The client POSTs the file; the
   backend validates the received bytes *first* and only uploads to Supabase if they pass.
   An invalid file is a synchronous `415`/`422`/`413` and nothing is stored. This removes an
   entire class of machinery the earlier design needed (signed-upload handshake, a `status`
   lifecycle, background validation, a stuck-`processing` recovery loop, FAILED-state cleanup).
2. **Memory is bounded.** The upload is streamed to a temp file in 1 MB chunks while the
   incoming-size cap is enforced on the running total (`413` aborts early). Two caps apply:
   the **incoming** body cap (`MAX_UPLOAD_SIZE_MB`, generous because the original PDF is
   discarded) and the **stored-artifact** cap (`MAX_STORED_ARTIFACT_MB`, matching the bucket
   `file_size_limit`) checked against the final bytes to store.
3. **The deep parse is the authoritative type gate.** `.docx` and `.xlsx` are both ZIP
   (OOXML) containers and share magic bytes, so the magic check is only a coarse first
   filter. A disguised/renamed file is rejected by failing to parse with `openpyxl`
   (`.xlsx`) / `python-docx` (`.docx`) / `PyMuPDF` (`.pdf`). `.xls` (OLE2) is accepted as a
   stored blob — no `xlrd`, so no sheet parsing.
4. **PDFs are slimmed to Markdown at upload (`pymupdf4llm`).** Born-digital PDFs are converted
   to a compact Markdown artifact (text + tables) and only that `.md` is stored; the original
   is discarded. This cuts storage and, downstream, LLM tokens. Extraction runs via
   `anyio.to_thread.run_sync` so the event loop stays free; only the one request waits.
   `pymupdf4llm` is **pinned to the lightweight `0.0.x` line** (`>=0.0.17,<0.1`): table-aware
   extraction costs ~tens of ms/page (text-heavy pages much less; dense-table pages more), so a
   typical spec is a few seconds and the largest (500–1000 pp) take tens of seconds. **Do not
   upgrade to the `1.27.x` line** — it bundles an ONNX layout model (`pymupdf-layout`) that runs
   at ~300 ms/page and makes large specs effectively hang. **Image-only PDFs are rejected fast:**
   a cheap `get_text()` text-layer pre-check runs *before* the table detector, so a scanned /
   "Microsoft Print to PDF" / text-as-outlines PDF (which has no extractable text and over which
   table detection would grind for many minutes) is rejected `422` in seconds — there is **no
   OCR**. PyMuPDF/`pymupdf4llm` are **AGPL-3.0**, accepted for this internal-only tool (revisit
   on external distribution / SaaS).
   > **Caveat:** the pre-check only short-circuits *zero-text* PDFs. A born-digital PDF that has
   > a real (but sparse) text layer *and* heavy vector graphics still passes the pre-check and can
   > be slow in the table-detection step. OCR for image-only PDFs is an explicit non-goal (see §10).
5. **`doc_type` is a string column, not a DB enum.** The taxonomy will churn (new
   equipment types / sections); a DB enum would need an `ALTER TYPE` per label. Allowed
   labels are a Python `StrEnum` validated in the pydantic layer instead.
6. **Single-instance storage client.** The Supabase client is created once in `lifespan`
   (secret key, raised timeout) and shared via `get_storage` — a lifecycle-scoped singleton,
   like the OpenRouter client. Not a module-level global, because the httpx client must bind
   to the running loop and be closed on shutdown.
7. **No authentication (accepted trade-off).** All endpoints are open. The `app_user`
   database role is **kept** — it is database least-privilege (the app's DSN connects as it),
   orthogonal to application auth. Only the auth-coupled DB objects (users table, signup
   trigger, RLS, BYPASSRLS) were removed.
8. **Residual orphan window.** A DB failure *after* a successful storage upload would leave an
   orphan object (logged). This is rare and an accepted simplification versus the old
   compensating-cleanup machinery.

---

## 7. Setup

### 7.1 Create the Supabase Storage bucket (out-of-band — not code/Alembic)

Create a bucket named `rfq-documents` (or whatever `SUPABASE_STORAGE_BUCKET` is set to),
**private**, with hard server-side guards:

- **Private** (no public read; objects reachable only via short-TTL signed URLs).
- **`file_size_limit`** = `MAX_STORED_ARTIFACT_MB` (a second line of defense behind the
  backend's stored-artifact guard; this is the size of what actually lands in the bucket — the
  `.md` for PDFs).
- **`allowed_mime_types`** must include **`text/markdown`** (slimmed PDFs are stored as `.md`),
  the OOXML docx/xlsx types, and `application/vnd.ms-excel`. `application/pdf` may be kept but is
  now unused (raw PDFs are never stored). **Note:** if `text/markdown` is missing, PDF uploads
  fail with Supabase `415 invalid_mime_type`, surfaced by the endpoint as `502`.

The bucket no longer needs browser CORS rules — uploads go through the backend, not the
browser, so the browser never talks to Supabase Storage directly.

### 7.2 Environment variables (`backend/.env`)

```dotenv
# ── Supabase storage ─────────────────────────────────────
SUPABASE_URL=...
SUPABASE_SECRET_KEY=...          # server-side; used by the Storage client
SUPABASE_STORAGE_BUCKET=rfq-documents

# ── Document upload ──────────────────────────────────────
MAX_UPLOAD_SIZE_MB=300           # incoming request-body cap (original PDF is discarded after slimming)
MAX_STORED_ARTIFACT_MB=50        # cap on what's actually stored (the .md for PDFs); matches bucket limit
SIGNED_DOWNLOAD_URL_TTL_S=600
STORAGE_CLIENT_TIMEOUT_S=120     # > storage3's 20s default, for larger objects
ALLOWED_UPLOAD_EXTENSIONS=.pdf,.docx,.xlsx,.xls

# ── Database ─────────────────────────────────────────────
DATABASE_URL=...                 # app DSN (connects as app_user)
MIGRATION_DATABASE_URL=...       # migration DSN (owner role)
APP_USER_PASSWORD=...            # used by the migration to create the app_user role
```

> **`APP_ENV` must be a real environment variable in non-local deploys.** It selects which
> `.env.<APP_ENV>` file is loaded and is read from the OS environment *before* `Settings` is
> built — so an `APP_ENV` written *inside* a dotenv file can't select that file. In production,
> set `APP_ENV=production` as an injected env var (or, cleaner, inject all config as real env
> vars and skip dotenv files — real env vars override dotenv anyway). The app logs the resolved
> `APP_ENV` on startup, so a wrong-file mistake shows up immediately (it would read `local`).

### 7.3 Run the migration

```bash
# From backend/ — single squashed migration (down_revision = None)
uv run alembic upgrade head
```

The migration creates the `app_user` role (if absent), the enum types, `projects` +
`documents`, and emits an explicit `GRANT SELECT, INSERT, UPDATE, DELETE ON projects,
documents TO app_user` (guarded by a role-existence check) — the single most likely place a
fresh environment would otherwise break at runtime ("permission denied"), because
`ALTER DEFAULT PRIVILEGES` doesn't always cover tables created by the migration role.

> **Reusing an old database?** This is a fresh squashed migration with `down_revision = None`,
> so a DB that still carries the previous migration history (or the live
> `on_auth_user_created` trigger on `auth.users`) must be reset first:
> `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` then `uv run alembic upgrade head`. Drop
> the old auth trigger out-of-band if present, so signups don't error against the now-absent
> `public.users`.

---

## 8. How to test it

### 8.1 Unit / integration tests (no network, no Postgres, no Supabase)

```bash
# From backend/
uv run pytest                                   # full suite (138 tests, ~97% cov)
uv run pytest tests/test_services -q            # pure logic: classifier, filetype, validation
uv run pytest tests/test_api/test_documents.py  # endpoint behavior via dependency overrides
```

Coverage of the new code:
- **Pure:** every classification rule + revision variant; magic-byte sniffing; `plan_storage_path`.
- **PDF → Markdown:** `extract_pdf_markdown` against real generated text+table PDFs (table
  preserved as GFM, correct page count) and a textless PDF (`NoExtractableTextError`).
- **Validation:** `validate_upload_bytes` against real generated PDF/XLSX/DOCX fixtures
  (PDF → `.md`/`text/markdown` artifact; office files stored as-is with their MIME), the
  `.xls` blob path, magic mismatch (`422`), parse failure (`422`), scanned-PDF no-text (`422`),
  the incoming-size guard (`413`), and the stored-artifact cap (`413`).
- **Endpoints:** upload (`201` + classification/page_count; PDF stored as a `.md` `text/markdown`
  object; sheet_names for xlsx; `415`; `422` mismatch; `422` unparseable; `422` scanned PDF;
  `413` oversized; `502` storage failure → nothing persisted; `404` missing project), list,
  detail (+`502` signing failure, empty-URL `502`), patch, delete (+storage-error swallow); the
  lifespan storage wiring.

### 8.2 Manual end-to-end (real bucket)

```bash
uv run uvicorn app.main:app --reload --port 8000
```

See [`testing-guide.md`](./testing-guide.md) for a full curl/Apidog walkthrough. The short version:

1. `GET /ready` → `200`.
2. `POST /api/v1/projects` `{"name":"Kohafa WWTP"}` → `201` (no token).
3. `POST /api/v1/projects/{id}/documents` with
   `-F "file=@01_Employer_Technical_Specifications_Rev02.pdf"` → `201`, classified,
   `page_count` set, `retention=persistent`.
4. Upload XLSX bytes named `report.pdf` → `422`. Upload `malware.exe` → `415`.
5. `GET /api/v1/documents/{id}` → metadata + `download_url`. `DELETE` → `204`.

### 8.3 Other gates

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run bandit -c pyproject.toml -r src
```

---

## 9. Risk handling (baked in)

| Risk | How it's handled |
|---|---|
| Large/oversized upload exhausts RAM | Streamed to a temp file in 1 MB chunks; the size cap aborts early (`413`); peak memory ≈ the (capped) file size. |
| `app_user` lacks DML on new tables → "permission denied" | Migration emits an explicit `GRANT … TO app_user` (guarded by a role-existence check). |
| Content ≠ declared type (`.zip`/`.docx` renamed `.xlsx`, garbage `.pdf`) | Magic-byte gate (`422`) then the authoritative deep parse (`422`); nothing is stored. |
| Storage object orphaned when an upload-then-DB-failure occurs | Rare; the upload happens before the insert, and a post-upload DB error is logged so the orphan is observable. |
| Storage object orphaned when a delete's remove fails | Logged (warning) so it's observable; the row is still removed (best-effort). |
| **Open endpoints** (no auth) | **Accepted trade-off.** Front the service with a gateway/proxy that enforces auth if exposure beyond a trusted network is needed. |

---

## 10. Out of scope / explicit follow-ups

- Re-introducing authentication / per-user ownership (removed in this simplification; enforce
  at a gateway, or restore the JWT + owner-scoping layer if multi-tenant access is needed).
- Deleting `transient` objects after RFQ generation (the `retention` tag is the hook; the
  delete fires in the Generate feature) and storing the generated RFQ output.
- **`.docx`/`.xlsx` → Markdown at upload** (deferred; stored as-is for now). These are
  structured (XML / cell grid), not a page-description format, so they need *different* tooling
  than PDF — planned: `.docx` → `mammoth` (MIT), `.xlsx` → `openpyxl` (already a dep) emitting
  one GFM table per sheet.
- OCR for scanned / image-only PDFs (currently `422`).
- Full-text extraction + token-aware LLM chunking (Extract/Generate feature).
- `.xls` sheet-name parsing (would need `xlrd`); accepted/stored/validated as a blob now.
- A true batch upload endpoint (the client loops single-file uploads; the per-file pipeline is reusable).

---

## 11. FAQ

**Q: Why is the upload synchronous now (vs. the old direct-to-storage flow)?**
A: To maximize simplicity. The backend receives the bytes, validates them, and stores them in
one request. The files are bounded by `MAX_UPLOAD_SIZE_MB` and streamed to disk, so RAM stays
bounded — and in exchange we drop the signed-upload handshake, the `status` lifecycle, the
background validation task, and the recovery loop entirely.

**Q: Can a renamed `.zip` (or a `.docx` saved as `.xlsx`) sneak through?**
A: No. Magic bytes can't tell OOXML files apart (they're all ZIP), but the deep parse can:
`openpyxl`/`python-docx`/`pypdf` fail on the wrong/garbage content, the upload returns `422`,
and nothing is stored.

**Q: Why is classification not done by the LLM?**
A: It's pure filename-prefix matching per the SRS — deterministic, instant, free, and
trivially testable. Engineers can override via `PATCH` when a filename doesn't follow the
convention.

**Q: Is there really no authentication?**
A: Correct — every endpoint is open. This is the explicit, accepted design for this branch
(prototype/demo, or auth enforced at a gateway). The `app_user` *database* role is unrelated
and is kept for database least-privilege.

**Q: Why no `RFQ` table?**
A: Most documents (employer requirements, process engineering, equipment list, hydraulic
profile) are shared across a project's RFQs; only templates/datasheets are RFQ-specific, and
that association is a generation-time concern. So documents attach to the project.

**Q: How is the secret key kept safe?**
A: It's used only server-side (Storage client) and is never returned to clients.
`storage_bucket`/`storage_path` are never serialized in API responses.

**Q: Does overriding a document's classification change its retention?**
A: Yes. `PATCH …/documents/{id}` recomputes `retention` from the new `doc_type` (so renaming
an unmatched file to `Equipment List` flips it from `transient` to `persistent`).

---

## 12. PR / review checklist

- [ ] Private Supabase bucket exists with `file_size_limit` + `allowed_mime_types`.
- [ ] `uv run alembic upgrade head` applied (fresh/reset DB); `app_user` can `INSERT`/`SELECT` the new tables.
- [ ] `uv run pytest` green (138) with coverage ≥ 80%.
- [ ] `uv run ruff check .` and `uv run mypy src` clean.
- [ ] `uv run bandit -c pyproject.toml -r src` clean; no secrets committed.
- [ ] Manual end-to-end ([§8.2](#82-manual-end-to-end-real-bucket)) returns `201` for a valid file and `415`/`422` for bad ones.
