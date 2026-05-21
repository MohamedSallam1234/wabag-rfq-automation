# Document Intake — Upload & Classification (PD-32)

The first stage of the RFQ pipeline (`Upload → Classify → Extract → Generate`).
Engineers upload a project's source documents (employer requirements, process
engineering, equipment lists, hydraulic profiles, RFQ templates, datasheets); the
system stores them in Supabase Storage, auto-classifies them by filename, and
validates their contents — without ever buffering an upload through the backend.

---

## TL;DR

- **Scope:** Upload + Classify only. Extraction/generation are out of scope.
- **Hierarchy:** `Project 1:M Document` (per the SRS). No `RFQ` table in this feature.
- **Uploads go direct to Supabase**, not through the backend. The flow is three JSON
  calls: `init` → (client PUTs bytes to a signed URL) → `finalize`. The backend never
  holds the file during transfer (answers the "don't kill RAM / don't block" constraint).
- **Validation is two-tier:** cheap synchronous checks (extension, declared size,
  per-project caps) at `init`; content checks (magic bytes + **deep parse** with
  `pypdf`/`openpyxl`/`python-docx`) run in a **background task** that streams the stored
  object to a temp file. A file that can't be parsed → `failed`, and its object is deleted.
- **Classification** is deterministic filename-prefix matching (no LLM), e.g. `01_*` →
  *Employer Technical Specifications*, `03_RFQ*` → *RFQ Template*. Engineers can override.
- **Retention:** project-common docs (`01`/`02`/`04`/`05`) are `persistent`; RFQ-specific
  docs (RFQ template, datasheets, specs) and unmatched files are `transient` (to be deleted
  after the RFQ is generated). Derived from classification; recomputed on override.
- **Status lifecycle:** `pending` → `processing` → `ready` | `failed` (client polls).
- **Access control:** owner-scoped — you only see projects you created (404 otherwise).
- **Endpoints:** projects CRUD-lite + `init`/`finalize`/list/detail/`PATCH`(override)/`DELETE`
  for documents, all under `/api/v1`.
- **For downstream (F-03/F-04):** a reusable `download_object_to_tempfile()` streams a stored
  object to disk (RAM-bounded) for extraction. See [§10 FAQ](#10-faq).
- **Quality:** 143 tests passing, **97.8%** coverage; ruff, mypy (strict), bandit,
  detect-secrets all clean.
- **Before it runs anywhere:** create the private Supabase bucket (with size/MIME limits)
  and run `uv run alembic upgrade head`. See [§6 Setup](#6-setup).

---

## 1. What was built

| File | Purpose |
|---|---|
| `src/app/models/project.py` | `Project` ORM model (name, location, client, consultant, project_number, capacity, `owner_id`). |
| `src/app/models/document.py` | `Document` ORM model + `DocumentStatus` / `DocTypeSource` / `RetentionPolicy` enums (enum columns persist lowercase values via `values_callable`). |
| `src/app/models/__init__.py` | Registers `Project` and `Document` so Alembic autogenerate sees them. |
| `src/app/services/ingestion/classifier.py` | Pure filename → `(doc_type, revision_label, revision_number)`; `DocType` enum of known labels; `retention_for(doc_type)` policy. |
| `src/app/services/ingestion/filetype.py` | Magic-byte sniffing + extension/MIME helpers (no native `libmagic`). |
| `src/app/services/ingestion/pdf_parser.py` / `excel_parser.py` / `word_parser.py` | Deep-parse helpers; opening the file is the integrity check. |
| `src/app/services/ingestion/upload.py` | Orchestration: request validation, storage paths, background object validation, stale-pending purge, and the reusable `download_object_to_tempfile()` helper. |
| `src/app/core/supabase.py` | `create_supabase_client()` — service-role async client built once in the lifespan. |
| `src/app/api/deps.py` | New `get_storage()` dependency + owner-scoped loaders (`load_owned_project`, `load_owned_document`, `current_user_id`). |
| `src/app/api/v1/projects.py` | Project create / list / get (owner-scoped). |
| `src/app/api/v1/documents.py` | `init` / `finalize` / list / detail / `PATCH` (override) / `DELETE`. |
| `src/app/api/v1/router.py` | Aggregates the v1 routers; included by `main.py`. |
| `src/app/schemas/project.py` / `document.py` | Pydantic request/response models (`storage_path` is never exposed). |
| `src/app/core/config.py` | Adds storage/upload settings (bucket, caps, TTLs, timeout, allowed extensions). |
| `src/app/main.py` | Lifespan now also creates/closes the Supabase client and includes the v1 router. |
| `alembic/versions/f1a2b3c4d5e6_create_projects_and_documents.py` | Creates `projects` + `documents`, enum types, indexes, FKs, and explicit `app_user` GRANTs. |
| `alembic/versions/a1b2c3d4e5f6_add_document_retention.py` | Adds the `retention` enum type + column to `documents`. |
| `tests/test_services/*`, `tests/test_api/*`, `tests/test_core/test_supabase.py` | 143 tests, 97.8% coverage, no live Postgres/Supabase. |
| `.env.example`, `pyproject.toml` | New env keys documented; `openpyxl` mypy override; pylint `max-args`; test `S105/S106` ignores. |

### Architecture in one picture

```
  ┌──────────┐  1. POST .../documents/init        ┌──────────────┐
  │  Client  │ ─────────────────────────────────► │   Backend    │
  │ (web/UI) │ ◄───────────────────────────────── │  (FastAPI)   │
  └────┬─────┘     { upload_url, token, doc }      └──────┬───────┘
       │                                                  │ validate ext/size/caps,
       │ 2. PUT bytes (signed URL)                        │ classify by filename,
       ▼                                                  │ insert row (status=pending)
  ┌─────────────────┐                                     │
  │ Supabase Storage│ ◄───────────────────────────────────
  │ (private bucket)│
  └────────┬────────┘
       │ 3. POST .../{id}/finalize
       │     backend: storage.info() → size check → status=processing
       │     schedule background task ──────────────┐
       ▼                                            ▼
   response (status=processing)            ┌──────────────────────┐
   client polls GET .../{id}               │ background validation │
                                           │ stream object → temp  │  RAM-bounded
                                           │ magic bytes + deep    │  off event loop
                                           │ parse → ready|failed  │  (deletes object
                                           └──────────────────────┘   on failure)
```

---

## 2. API reference

All endpoints require a Supabase JWT (`Authorization: Bearer <token>`) and are
**owner-scoped**: a project/document owned by another user returns **404** (not 403,
to avoid leaking existence).

### Projects
| Method & path | Purpose |
|---|---|
| `POST /api/v1/projects` | Create a project owned by the caller. |
| `GET /api/v1/projects` | List the caller's projects. |
| `GET /api/v1/projects/{project_id}` | Fetch one (404 if not owned). |

### Documents
| Method & path | Purpose | Notable responses |
|---|---|---|
| `POST /api/v1/projects/{project_id}/documents/init` | Validate + classify a planned upload; create a `pending` row; return a signed upload URL. | `201`; `415` bad ext; `413` too large; `409` over per-project cap; `404` project not owned. |
| `POST /api/v1/documents/{document_id}/finalize` | Verify the uploaded object; set `processing`; schedule background validation. | `200` (processing); `400` object not uploaded yet (retryable, row stays `pending`); `409` not awaiting finalize; `413` actual object too large (marked `failed`, object removed). |
| `GET /api/v1/projects/{project_id}/documents` | List a project's documents (classification + status). | `200`. |
| `GET /api/v1/documents/{document_id}` | Document metadata + a short-lived signed **download** URL. | `200`; `404`. |
| `PATCH /api/v1/documents/{document_id}` | Override classification (`doc_type`); sets `doc_type_source=manual`. | `200`; `422` unknown `doc_type`. |
| `DELETE /api/v1/documents/{document_id}` | Delete the row + best-effort remove the storage object. | `204`. |

### `init` request / response

```jsonc
// POST /api/v1/projects/{project_id}/documents/init
{ "filename": "01_Employer_Spec_Rev01.pdf", "size_bytes": 2400000, "content_type": null }

// 201 Created
{
  "document": { "id": "…", "status": "pending", "doc_type": "Employer Technical Specifications",
                "revision_number": 1, "revision_label": "Rev01", "doc_type_source": "auto", … },
  "upload_url": "https://<project>.supabase.co/storage/v1/object/upload/sign/…",
  "token": "…",
  "storage_path": "<project_id>/<document_id>.pdf"
}
```

The client then uploads the bytes directly to Supabase (browser:
`supabase.storage.from(bucket).uploadToSignedUrl(path, token, file)`; server clients:
`PUT` the file body to `upload_url`), and finally calls `finalize`.

---

## 3. Data model

`Project 1:M Document` (CASCADE delete). UUID primary keys, timezone-aware timestamps.

**`projects`** — `id`, `name`, `location?`, `client?`, `consultant?`, `project_number?`,
`capacity_m3d?`, `owner_id → users.id (CASCADE, indexed)`, `created_at`, `updated_at`.

**`documents`** — `id` (also the storage object name), `project_id → projects.id
(CASCADE, indexed)`, `original_filename`, `storage_bucket`, `storage_path`,
`content_type`, `size_bytes?`, `sha256?`, `doc_type?` (indexed, **plain string** so the
taxonomy can evolve without migrations), `doc_type_source` (`auto`/`manual` enum),
`revision_label?`, `revision_number?`, `page_count?`, `sheet_names?` (JSONB),
`status` (`pending`/`processing`/`ready`/`failed` enum),
`retention` (`persistent`/`transient` enum), `failure_reason?`,
`uploaded_by → users.id (SET NULL, indexed)`, `created_at`, `updated_at`.

> **Enum storage:** the `*_source` / `status` / `retention` columns use real Postgres enum
> types whose labels are the **lowercase values** (`failed`, not `FAILED`); the ORM binds
> values via `values_callable` so they match.

> **RLS is intentionally not added** to these tables: the runtime role `app_user` has
> `BYPASSRLS`, so policies would have no effect at runtime — authorization is enforced
> in Python (auth required + owner filtering). Noted as an optional parity follow-up.

### Retention policy

Not every uploaded file is kept long-term. `retention` is derived from the classification
(`retention_for(doc_type)`) at `init` and **recomputed when the classification is overridden**
via `PATCH`:

| Retention | Documents | Lifecycle |
|---|---|---|
| `persistent` | Project-common inputs: `01_*` Employer, `02_*` Process, `04_*` Hydraulic, `05_*` Equipment List (and, later, the generated RFQ output) | Kept for the life of the project. |
| `transient` | RFQ-specific inputs: RFQ template (`03_RFQ*`), datasheets, specs, and any **unmatched** file | Needed only during generation; **deleted from storage once the RFQ has been generated**. |

The deletion of `transient` objects happens in the **Generate** feature (the `retention` tag
is the hook); intake only records the policy.

---

## 4. Classification rules

Deterministic, ordered, first-match-wins (`src/app/services/ingestion/classifier.py`).
**Tender-section patterns (SectionII–SectionVII) are intentionally excluded** (out of scope).

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

## 5. Design decisions you should know about

1. **Signed direct-to-storage uploads, not a proxy.** File bytes never traverse the
   backend during upload — the strongest answer to the "don't exhaust RAM / don't hold
   a request open" constraints. The only server-side read is the background validation
   download, which is streamed chunk-by-chunk to a temp file (peak ≈ one chunk).
2. **Content validation is asynchronous.** Because the upload is direct, magic-byte and
   deep-parse checks can only run after the object exists. They run in a FastAPI
   `BackgroundTask`; the document carries a `status` the client polls. `finalize` commits
   `processing` **before** scheduling the task so the task's own session can't read a stale
   `pending`.
3. **The deep parse is the authoritative type gate.** `.docx` and `.xlsx` are both ZIP
   (OOXML) containers and share magic bytes, so the magic check is only a coarse first
   filter. A disguised/renamed ZIP is rejected by failing to parse with `openpyxl`
   (`.xlsx`) / `python-docx` (`.docx`) / `pypdf` (`.pdf`). `.xls` (OLE2) is accepted as a
   stored blob — no `xlrd`, so no sheet parsing.
4. **`doc_type` is a string column, not a DB enum.** The taxonomy will churn (new
   equipment types / sections); a DB enum would need an `ALTER TYPE` per label. Allowed
   labels are a Python `StrEnum` validated in the pydantic layer instead.
5. **Owner-scoped, single-instance storage client.** The Supabase client is created once
   in `lifespan` (service-role key, raised timeout) and shared via `get_storage` — a
   lifecycle-scoped singleton, like the OpenRouter client. Not a module-level global,
   because the httpx client must bind to the running loop and be closed on shutdown.
6. **Two non-transactional systems, compensating order.** `init` inserts the row then
   signs the URL (no object exists yet, so a rollback leaves nothing orphaned). On failed
   validation the background task deletes the storage object. No object is ever written
   before its row exists.

---

## 6. Setup

### 6.1 Create the Supabase Storage bucket (out-of-band — not code/Alembic)

Create a bucket named `rfq-documents` (or whatever `SUPABASE_STORAGE_BUCKET` is set to),
**private**, with hard server-side guards so the direct upload is constrained before our
validation even runs:

- **Private** (no public read; objects reachable only via short-TTL signed URLs).
- **`file_size_limit`** = `MAX_UPLOAD_SIZE_MB` (Supabase rejects oversized PUTs at upload
  time, even if the client lies about declared size at `init`).
- **`allowed_mime_types`** = `application/pdf`, the OOXML docx/xlsx types, and
  `application/vnd.ms-excel`.
- **CORS / allowed origins** = your web app origin, so browser `uploadToSignedUrl` works.

### 6.2 Environment variables (`backend/.env`)

```dotenv
# ── Document storage / upload ────────────────────────────
SUPABASE_STORAGE_BUCKET=rfq-documents
MAX_UPLOAD_SIZE_MB=100          # per single file
MAX_FILES_PER_PROJECT=50        # per-project document count cap
MAX_PROJECT_TOTAL_SIZE_MB=1000  # per-project total size cap
SIGNED_UPLOAD_URL_TTL_S=300
SIGNED_DOWNLOAD_URL_TTL_S=600
STORAGE_CLIENT_TIMEOUT_S=120    # > storage3's 20s default, for streaming large objects
PENDING_UPLOAD_TTL_MIN=60       # stale-`pending` cutoff for opportunistic GC
COMPUTE_SHA256=true
ALLOWED_UPLOAD_EXTENSIONS=.pdf,.docx,.xlsx,.xls
```

`SUPABASE_URL` / `SUPABASE_SECRET_KEY` (already required by the app) are reused for
storage. All values above have sensible defaults and are tunable.

### 6.3 Run the migration

```bash
# From backend/
uv run alembic upgrade head     # applies BOTH migrations: projects+documents, then retention
```

There are two migrations in this feature (`…_create_projects_and_documents` then
`…_add_document_retention`); `upgrade head` runs both. The first emits explicit
`GRANT SELECT, INSERT, UPDATE, DELETE ON projects, documents TO app_user` — the single most
likely place a fresh environment would otherwise break at runtime ("permission denied"),
because `ALTER DEFAULT PRIVILEGES` doesn't always cover tables created by the migration role.

---

## 7. How to test it

### 7.1 Unit / integration tests (no network, no Postgres, no Supabase)

```bash
# From backend/
uv run pytest                                  # full suite (143 tests)
uv run pytest tests/test_services -q           # pure logic: classifier, filetype, upload, models
uv run pytest tests/test_api/test_documents.py # endpoint behavior via dependency overrides
```

Coverage of the new code:
- **Pure:** every classification rule + revision variant; magic-byte sniffing; the
  upload-request validators; `_extract_size`.
- **Mocked:** `validate_stored_object` against real generated PDF/XLSX/DOCX fixtures plus a
  garbage/parse-failure/download-error path; `run_document_validation` success/failure;
  `purge_stale_pending_documents`.
- **Endpoints:** `init` (success, `415`, `409`-via-caps, `404` not-owned),
  `finalize` (processing+schedule, `400` missing, `413` oversized→removed, `409`),
  list/detail/patch/delete; the lifespan storage wiring; `get_storage` + owner loaders.

### 7.2 Manual end-to-end (real bucket + JWT)

```bash
uv run uvicorn app.main:app --reload --port 8000
```

1. `POST /api/v1/projects` → create a project.
2. `POST /api/v1/projects/{id}/documents/init` with `01_Employer_Spec_Rev01.pdf` →
   document is `pending`, `doc_type = "Employer Technical Specifications"`,
   `revision_number = 1`, `retention = "persistent"`.
3. `PUT` the bytes to the returned `upload_url` (curl or `uploadToSignedUrl`).
4. `POST /api/v1/documents/{id}/finalize` → `processing`; poll
   `GET /api/v1/documents/{id}` until `ready`, with `page_count` set and a working
   `download_url`.
5. Upload a renamed garbage file (`notes.pdf` containing text) → ends `failed` with a
   reason and the storage object removed.
6. With a second user's JWT, the project/document endpoints return `404` (owner-scoping).

### 7.3 Other gates

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run bandit -c pyproject.toml -r src
```

### 7.4 Testing with Apidog / Postman

The tricky part: **step 3 (the file upload) goes directly to Supabase, not to the backend.**
Everything else is normal JSON against the API with a Bearer token.

**Prerequisites**

```bash
# from backend/, against the target Supabase project (e.g. cloud):
$env:APP_ENV = "dev"            # PowerShell: load .env only (skip .env.local); bash: export APP_ENV=dev
uv run alembic upgrade head     # MUST include the retention migration
uv run uvicorn app.main:app --reload --port 8000
```

The bucket (`SUPABASE_STORAGE_BUCKET`, default `rfq-documents`) must exist in that project —
private, with the size limit + allowed MIME types.

**Environment variables (Apidog/Postman):** `base_url` (`http://localhost:8000`),
`supabase_url`, `anon_key`, `service_role_key` (only to create a test user), and the
runtime-filled `token`, `project_id`, `document_id`, `upload_url`, `upload_token`,
`storage_path`. **Pre-declare them** so they persist, and set collection-level **Bearer
`{{token}}`** (turn it **off** for the one direct Supabase PUT).

> Apidog/Postman gotcha: extraction scripts must use `pm.environment.set(...)`
> (`pm.variables.set(...)` is run-scoped and is cleared after the request). Guard them so a
> failed request doesn't blank good values (`if (pm.response.code < 300) { … }`).

**0. Get a JWT** — `POST {{supabase_url}}/auth/v1/token?grant_type=password` with header
`apikey: {{anon_key}}` and body `{ "email", "password" }`. (Create a confirmed user first via
`POST {{supabase_url}}/auth/v1/admin/users` with the `service_role_key` and
`"email_confirm": true`.) Save the token:
```javascript
if (pm.response.code < 300) pm.environment.set("token", pm.response.json().access_token);
```

**1. Create project** — `POST {{base_url}}/api/v1/projects` body `{ "name": "Kohafa WWTP" }` →
`201`. Script: `pm.environment.set("project_id", pm.response.json().id);`

**2. Init** — `POST {{base_url}}/api/v1/projects/{{project_id}}/documents/init` body
`{ "filename": "05_Equipment List_Rev02.xlsx", "size_bytes": <real byte size> }` → `201`.
Script:
```javascript
const j = pm.response.json();
pm.environment.set("upload_url", j.upload_url);
pm.environment.set("upload_token", j.token);
pm.environment.set("document_id", j.document.id);
```
Verify `doc_type` = `"Equipment List"`, `retention` = `"persistent"`, `status` = `"pending"`.

**3. Upload to Supabase (direct)** — `PUT {{upload_url}}`, **Auth: No Auth**, **Body → Binary**
= the file, header `Content-Type` matching the file (`application/pdf`, or for `.xlsx`
`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`) → `200`. *(Fallback if
rejected: Body → form-data, one field named `file` of type File.)*

**4. Finalize** — `POST {{base_url}}/api/v1/documents/{{document_id}}/finalize` (Bearer, no
body) → `200`, `status` = `"processing"`.

**5. Poll** — `GET {{base_url}}/api/v1/documents/{{document_id}}` until `status` = `"ready"`.
PDFs show `page_count`; xlsx shows `sheet_names`; both expose a `download_url`.

**Other endpoints / negative checks**

| Test | Request | Expect |
|---|---|---|
| List | `GET {{base_url}}/api/v1/projects/{{project_id}}/documents` | `200` array w/ `doc_type`/`status`/`retention` |
| Override | `PATCH {{base_url}}/api/v1/documents/{{document_id}}` `{ "doc_type": "Equipment List" }` | `200`, `doc_type_source: "manual"`, `retention` recomputed |
| Delete | `DELETE {{base_url}}/api/v1/documents/{{document_id}}` | `204` (object removed) |
| Bad extension | init `"filename": "malware.exe"` | `415` |
| Oversized (declared) | init `"size_bytes": 999999999999` | `413` |
| Unparseable | init `notes.pdf` → PUT a text file renamed `.pdf` → finalize → poll | ends `failed` + object removed |
| Finalize too early | finalize without doing the PUT | `400` (stays `pending`) |
| Finalize twice | finalize a `processing`/`ready` doc | `409` |
| Owner-scoping | repeat step 0 as a 2nd user, `GET …/projects/{{project_id}}` | `404` |
| Bad override | `PATCH … { "doc_type": "Nonsense" }` | `422` |

> The signed `upload_url`/`token` are single-use and short-lived (`SIGNED_UPLOAD_URL_TTL_S`,
> default 300s) — re-run `init` to get a fresh pair if a step expires.

---

## 8. Risk handling (baked in)

| Risk | How it's handled |
|---|---|
| storage3's 20s httpx timeout aborts large streams | `STORAGE_CLIENT_TIMEOUT_S=120` on the client; bucket `file_size_limit` bounds object size. |
| `app_user` lacks DML on new tables → "permission denied" | Migration emits explicit `GRANT … TO app_user` unconditionally. |
| storage3 `download()` buffers the whole object in RAM | Background validation streams via a signed URL + `httpx.AsyncClient.stream`, chunked to disk — never `download()`. |
| Async rejection + orphaned `pending` uploads | `status`/`failure_reason` lifecycle for polling; `purge_stale_pending_documents` runs opportunistically on every `init` (no scheduler needed; reusable by a future cron). |
| Browser direct upload needs CORS | Bucket runbook sets allowed origins; `init` returns everything the client needs for `uploadToSignedUrl`. |
| Malicious bytes briefly resident before async validation | Private bucket, bucket-level `allowed_mime_types` + `file_size_limit`, prompt deletion of `failed` objects, files only ever downloaded server-side for validation — never executed/served inline. |

---

## 9. Out of scope / explicit follow-ups

- Deleting `transient` objects after RFQ generation (the `retention` tag is the hook; the
  delete fires in the Generate feature) and storing the generated RFQ output.
- Full-text extraction + token-aware LLM chunking (Extract/Generate feature; intake already
  provides the RAM-bounded byte download via `download_object_to_tempfile()`).
- True antivirus (ClamAV) content scanning.
- A scheduled GC sweep (the purge function is ready; only the scheduler is deferred).
- `.xls` sheet-name parsing (would need `xlrd`); accepted/stored/validated as a blob now.
- Teams / collaboration sharing (v1 is owner-scoped).
- RLS policies on the new tables (no runtime effect while `app_user` has `BYPASSRLS`).
- A true batch upload endpoint (the client loops single-file `init`/`finalize`; the per-file
  pipeline is reusable).

---

## 10. FAQ

**Q: Why don't uploads go through the backend?**
A: The files are heavy. Routing them through FastAPI would hold a request open for the
whole transfer and risk RAM/bandwidth pressure. Signed direct-to-storage uploads keep the
backend out of the byte path entirely.

**Q: Then how can it "reject unparseable files" if it never sees the bytes?**
A: It sees them once, in the background: `finalize` schedules a task that streams the stored
object to a temp file (RAM-bounded) and runs the real parser. Rejection is therefore
asynchronous — reflected as `status = failed` with a `failure_reason`, which the client polls.

**Q: Can a renamed `.zip` (or a `.docx` saved as `.xlsx`) sneak through?**
A: No. Magic bytes can't tell OOXML files apart (they're all ZIP), but the deep parse can:
`openpyxl`/`python-docx`/`pypdf` fail on the wrong/garbage content and the document is marked
`failed`.

**Q: Why is classification not done by the LLM?**
A: It's pure filename-prefix matching per the SRS — deterministic, instant, free, and
trivially testable. Engineers can override via `PATCH` when a filename doesn't follow the
convention.

**Q: Why no `RFQ` table?**
A: Most documents (employer requirements, process engineering, equipment list, hydraulic
profile) are shared across a project's RFQs; only templates/datasheets are RFQ-specific, and
that association is a generation-time concern. So documents attach to the project. (The
`models/rfq.py` stub is untouched.)

**Q: What guarantees the background task sees `processing` and not `pending`?**
A: `finalize` calls `await db.commit()` before `background_tasks.add_task(...)`, so the
status is durable before the in-process task opens its own session.

**Q: How is the service-role key kept safe?**
A: It's used only server-side to mint short-TTL signed URLs and to manage objects; it's never
returned to clients, and `storage_path`/`storage_bucket` are never serialized in responses.

**Q: How will the extraction/validation feature (F-03/F-04) consume this?**
A: List a project's `ready` documents (`GET /projects/{id}/documents`, or query `Document`
directly if running in-process), then for each one stream the bytes to disk with
`download_object_to_tempfile(storage, bucket=…, storage_path=…, settings=…)`. **Document
formats can't be parsed from a byte range** (PDF xref / OOXML zip directory live at the end),
so the whole file is fetched — but streamed to disk so RAM stays ~one chunk. The extractor
then parses text (extending the parser modules — full-text extraction is F-03 work), chunks
the **text** only when it exceeds the model context (Claude's ~200K means many docs fit in one
call), and uses `doc_type`/`revision_*` to drive the F-04 precedence/reference-matrix logic.
LLM calls go through the existing `LLMRouter` (`Depends(get_router)`).

**Q: Does overriding a document's classification change its retention?**
A: Yes. `PATCH …/documents/{id}` recomputes `retention` from the new `doc_type` (so renaming
an unmatched file to `Equipment List` flips it from `transient` to `persistent`).

---

## 11. PR / review checklist

- [ ] Private Supabase bucket exists with `file_size_limit` + `allowed_mime_types` + CORS.
- [ ] `uv run alembic upgrade head` applied (both migrations); `app_user` can `INSERT`/`SELECT` the new tables.
- [ ] `uv run pytest` green (143) with coverage ≥ 80%.
- [ ] `uv run ruff check src tests` and `uv run mypy src` clean.
- [ ] `uv run bandit -c pyproject.toml -r src` clean; no secrets committed.
- [ ] Manual end-to-end (§7.2) reaches `ready`, and a garbage file reaches `failed`.
