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
  per-project caps) at `init`; content checks run in a **background task** that streams
  the stored object to a temp file — magic bytes → **opt-in AV scan** → **OOXML
  decompression-bomb guard** → **deep parse** (`pypdf`/`openpyxl`/`python-docx`). A file
  that fails a *content* check → `failed`, and its object is deleted.
- **Self-healing:** a transient blip (storage download error, scanner unreachable) leaves
  the document `processing`; a **periodic recovery sweep** re-drives it instead of waiting
  for a restart.
- **Classification** is deterministic filename-prefix matching (no LLM), e.g. `01_*` →
  *Employer Technical Specifications*, `03_RFQ*` → *RFQ Template*. Engineers can override.
- **Retention:** project-common docs (`01`/`02`/`04`/`05`) are `persistent`; RFQ-specific
  docs (RFQ template, datasheets, specs) and unmatched files are `transient` (to be deleted
  after the RFQ is generated). Derived from classification; recomputed on override.
- **Status lifecycle:** `pending` → `processing` → `ready` | `failed` (client polls).
- **Access control:** owner-scoped — you only see projects you created (404 otherwise).
- **Endpoints:** projects CRUD-lite + `init`/`finalize`/list/detail/`PATCH`(override)/`DELETE`
  for documents, all under `/api/v1`.
- **Frontend devs:** see [§3 Frontend integration guide](#3-frontend-integration-guide) for
  the end-to-end browser flow, TypeScript types, and error handling.
- **For downstream (F-03/F-04):** a reusable `download_object_to_tempfile()` streams a stored
  object to disk (RAM-bounded) for extraction. See [§11 FAQ](#11-faq).
- **Quality:** 171 tests passing, **~97%** coverage; ruff, mypy (strict), bandit,
  detect-secrets all clean.
- **Before it runs anywhere:** create the private Supabase bucket (with size/MIME limits)
  and run `uv run alembic upgrade head`. See [§7 Setup](#7-setup).

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
| `src/app/services/ingestion/archive.py` | OOXML **decompression-bomb guard** — inspects the ZIP central directory (no extraction) and rejects archives over the uncompressed-size / ratio / entry-count caps. |
| `src/app/services/ingestion/antivirus.py` | **Opt-in ClamAV** scan (`scan_file`) — lazy client, runs off the event loop, **fails closed** (an unreachable scanner is retryable, never silently accepted). |
| `src/app/services/ingestion/upload.py` | Orchestration: request validation, storage paths, background object validation (magic → AV → zip-guard → parse), stale-pending purge, the periodic **`run_recovery_loop`**, and the reusable `download_object_to_tempfile()` helper. |
| `src/app/core/supabase.py` | `create_supabase_client()` — secret-key async client built once in the lifespan. |
| `src/app/api/deps.py` | `get_storage()` dependency + owner-scoped loaders (`load_owned_project`, `load_owned_document`, `current_user_id`). |
| `src/app/api/v1/projects.py` | Project create / list / get (owner-scoped). |
| `src/app/api/v1/documents.py` | `init` / `finalize` (with per-file **and** project-total size re-check) / list / detail / `PATCH` (override) / `DELETE`. |
| `src/app/api/v1/router.py` | Aggregates the v1 routers; included by `main.py`. |
| `src/app/schemas/project.py` / `document.py` | Pydantic request/response models (`storage_path`/`storage_bucket` are never exposed). |
| `src/app/core/config.py` | Storage/upload settings (bucket, caps, TTLs, timeout, allowed extensions) + recovery-sweep interval + validation-hardening (zip-bomb caps, ClamAV toggle/connection). |
| `src/app/main.py` | Lifespan creates/closes the Supabase client, includes the v1 router, and runs the periodic recovery sweep (`run_recovery_loop`). |
| `alembic/versions/f1a2b3c4d5e6_create_projects_and_documents.py` | Creates `projects` + `documents`, enum types, indexes, FKs, and explicit `app_user` GRANTs. |
| `alembic/versions/a1b2c3d4e5f6_add_document_retention.py` | Adds the `retention` enum type + column to `documents`. |
| `tests/test_services/*`, `tests/test_api/*`, `tests/test_core/*` | 171 tests, ~97% coverage (incl. `test_archive.py`, `test_antivirus.py`), no live Postgres/Supabase. |
| `.env.example`, `pyproject.toml` | New env keys documented; `clamd` dependency + mypy override; `openpyxl` mypy override. |

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
       │     backend: storage.info() → size check (per-file + project-total)
       │     → status=processing → schedule background task ───────┐
       ▼                                                           ▼
   response (status=processing)            ┌────────────────────────────┐
   client polls GET .../{id}               │ background validation        │
                                           │ stream object → temp file    │ RAM-bounded
                                           │ magic bytes → AV scan*       │ off event loop
                                           │ → zip-bomb guard → deep parse│ (*AV opt-in)
                                           │ → ready | failed             │ deletes object
                                           └────────────────────────────┘  on permanent fail

   A periodic recovery sweep re-drives any doc left in `processing` by a crash/restart
   or a transient blip (storage download error / scanner unreachable).
```

---

## 2. API reference

All endpoints require a Supabase JWT (`Authorization: Bearer <token>`) and are
**owner-scoped**: a project/document owned by another user returns **404** (not 403,
to avoid leaking existence). A missing/invalid token returns **401**.

### Projects
| Method & path | Purpose |
|---|---|
| `POST /api/v1/projects` | Create a project owned by the caller. |
| `GET /api/v1/projects` | List the caller's projects. |
| `GET /api/v1/projects/{project_id}` | Fetch one (404 if not owned). |

### Documents
| Method & path | Purpose | Notable responses |
|---|---|---|
| `POST /api/v1/projects/{project_id}/documents/init` | Validate + classify a planned upload; create a `pending` row; return a signed upload URL. | `201`; `415` bad ext; `413` too large (file or project total); `409` over per-project file-count cap; `404` project not owned. |
| `POST /api/v1/documents/{document_id}/finalize` | Verify the uploaded object; set `processing`; schedule background validation. | `200` (processing); `400` object not uploaded yet (retryable, row stays `pending`); `409` not awaiting finalize; `413` actual object breaks the per-file **or** project-total cap (marked `failed`, object removed). |
| `GET /api/v1/projects/{project_id}/documents` | List a project's documents (classification + status), newest first. | `200`. |
| `GET /api/v1/documents/{document_id}` | Document metadata + a short-lived signed **download** URL. | `200`; `404`; `502` if a download URL can't be minted for a doc that should have bytes. |
| `PATCH /api/v1/documents/{document_id}` | Override classification (`doc_type`); sets `doc_type_source=manual`, recomputes `retention`. | `200`; `422` unknown `doc_type`. |
| `DELETE /api/v1/documents/{document_id}` | Delete the row + best-effort remove the storage object (orphans on storage failure are logged). | `204`. |

### `init` request / response

```jsonc
// POST /api/v1/projects/{project_id}/documents/init
{ "filename": "01_Employer_Spec_Rev01.pdf", "size_bytes": 2400000 }

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
`supabase.storage.from(bucket).uploadToSignedUrl(storage_path, token, file)`; any HTTP
client: `PUT` the file body to `upload_url`), and finally calls `finalize`. See
[§3](#3-frontend-integration-guide) for a full walkthrough.

> **`download_url` is only populated for `ready`/`processing` documents** (those have stored
> bytes). For `pending`/`failed` it is `""`. If signing fails for a doc that *should* have
> bytes, the detail endpoint returns `502` rather than a misleading empty string.

---

## 3. Frontend integration guide

This is everything a web/UI developer needs to drive intake. The only unusual part is
**step 2: the file bytes go straight to Supabase Storage, not to our API.** Everything else
is plain JSON over HTTPS with a Bearer token.

### 3.1 Prerequisites & auth

- The browser authenticates with Supabase (e.g. `@supabase/supabase-js`) and sends the
  resulting **access token** as `Authorization: Bearer <token>` on every API call.
- For the direct upload you need the **bucket name** (the API never returns it — it's the
  same value the backend uses for `SUPABASE_STORAGE_BUCKET`, e.g. `rfq-documents`; expose it
  to the frontend as a public build-time config such as `NEXT_PUBLIC_SUPABASE_BUCKET`).
  *(If you upload by raw `PUT` to `upload_url` instead, you don't need the bucket name — the
  signed URL already encodes it.)*
- The bucket must allow your web origin via CORS (see [§7.1](#71-create-the-supabase-storage-bucket-out-of-band--not-codealembic)).

### 3.2 TypeScript types

```ts
type DocumentStatus  = "pending" | "processing" | "ready" | "failed";
type DocTypeSource   = "auto" | "manual";
type RetentionPolicy = "persistent" | "transient";

interface DocumentRead {
  id: string;
  project_id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number | null;
  sha256: string | null;
  doc_type: string | null;           // null until classified/overridden
  doc_type_source: DocTypeSource;
  revision_label: string | null;
  revision_number: number | null;
  page_count: number | null;         // PDFs once ready
  sheet_names: string[] | null;      // .xlsx once ready
  status: DocumentStatus;
  retention: RetentionPolicy;
  failure_reason: string | null;     // set when status === "failed"
  uploaded_by: string | null;
  created_at: string;                // ISO-8601
  updated_at: string;
}

interface DocumentInitResponse {
  document: DocumentRead;            // status === "pending"
  upload_url: string;               // PUT the bytes here (Supabase, short-lived)
  token: string;                    // for supabase-js uploadToSignedUrl
  storage_path: string;             // "<project_id>/<document_id>.<ext>"
}

interface DocumentDetail extends DocumentRead {
  download_url: string;             // signed, short-lived; "" for pending/failed
}
```

### 3.3 The upload flow (end to end)

```ts
import { createClient } from "@supabase/supabase-js";

const supabase = createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY);
const API_BASE = "/api/v1";
const BUCKET = process.env.NEXT_PUBLIC_SUPABASE_BUCKET!; // == backend SUPABASE_STORAGE_BUCKET

async function authHeaders(): Promise<HeadersInit> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new Error("Not signed in");
  return { Authorization: `Bearer ${token}` };
}

/** Upload one file and resolve once it is `ready` (throws with a reason on `failed`). */
async function uploadDocument(projectId: string, file: File): Promise<DocumentDetail> {
  // 1) init — validate + classify + reserve a signed upload URL
  const initRes = await fetch(`${API_BASE}/projects/${projectId}/documents/init`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ filename: file.name, size_bytes: file.size }),
  });
  if (!initRes.ok) throw await apiError(initRes); // 415 / 413 / 409 / 404
  const init: DocumentInitResponse = await initRes.json();

  // 2) upload bytes DIRECTLY to Supabase Storage (not our API)
  const { error } = await supabase.storage
    .from(BUCKET)
    .uploadToSignedUrl(init.storage_path, init.token, file, { contentType: file.type });
  if (error) throw error;
  // — or, without supabase-js:
  //   await fetch(init.upload_url, { method: "PUT", body: file,
  //                                  headers: { "Content-Type": file.type } });

  // 3) finalize — backend checks the real object size, flips to "processing"
  const finRes = await fetch(`${API_BASE}/documents/${init.document.id}/finalize`, {
    method: "POST",
    headers: await authHeaders(),
  });
  if (!finRes.ok) throw await apiError(finRes); // 400 (retry) / 409 / 413

  // 4) poll until ready | failed
  return pollUntilDone(init.document.id);
}

async function pollUntilDone(
  documentId: string,
  { intervalMs = 1500, maxMs = 120_000 } = {},
): Promise<DocumentDetail> {
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    const res = await fetch(`${API_BASE}/documents/${documentId}`, { headers: await authHeaders() });
    if (!res.ok) throw await apiError(res);
    const doc: DocumentDetail = await res.json();
    if (doc.status === "ready") return doc;                 // doc.download_url is usable
    if (doc.status === "failed") throw new Error(doc.failure_reason ?? "Validation failed");
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  // Still "processing": NOT necessarily broken — a transient blip is retried by the
  // backend's recovery sweep. Show "still processing" and let the user check back.
  throw new Error("Still processing — check back shortly");
}

async function apiError(res: Response): Promise<Error> {
  const detail = await res.json().then((b) => b?.detail).catch(() => res.statusText);
  return Object.assign(new Error(detail), { status: res.status });
}
```

### 3.4 Other operations

```ts
// List a project's documents (newest first)
const docs: DocumentRead[] = await fetch(
  `${API_BASE}/projects/${projectId}/documents`, { headers: await authHeaders() },
).then((r) => r.json());

// Override a misclassified document (doc_type must be one of the known labels — see §5)
await fetch(`${API_BASE}/documents/${documentId}`, {
  method: "PATCH",
  headers: { "Content-Type": "application/json", ...(await authHeaders()) },
  body: JSON.stringify({ doc_type: "Equipment List" }), // 422 if not a valid label
});

// Download: fetch detail → use the short-lived signed download_url
const detail: DocumentDetail = await fetch(
  `${API_BASE}/documents/${documentId}`, { headers: await authHeaders() },
).then((r) => r.json());
window.open(detail.download_url, "_blank"); // re-fetch detail if it expires

// Delete
await fetch(`${API_BASE}/documents/${documentId}`, { method: "DELETE", headers: await authHeaders() });
```

### 3.5 Status semantics (drive the UI off these)

| `status` | Meaning | Suggested UI |
|---|---|---|
| `pending` | Row created; bytes not uploaded/finalized yet. | Transient internal state; usually you go straight through it. |
| `processing` | Bytes uploaded; background validation running. | Spinner / "Validating…"; keep polling. |
| `ready` | Validated; usable. `page_count`/`sheet_names`/`download_url` populated. | Show the doc, its `doc_type`, revision, and a download link. |
| `failed` | A content check failed. `failure_reason` explains why; the object was deleted. | Show `failure_reason` and let the user re-upload. |

### 3.6 Error handling

| When | Code | Meaning | What the UI should do |
|---|---|---|---|
| any | `401` | Missing/expired token | Re-authenticate, retry. |
| any | `404` | Not found or not owned | Treat as "doesn't exist". |
| `init` | `415` | Extension not allowed | Tell the user the allowed types (`.pdf/.docx/.xlsx/.xls`). |
| `init`/`finalize` | `413` | File or project size cap exceeded | Show the limit; `finalize` 413 also means the doc is now `failed`. |
| `init` | `409` | Project already at the file-count cap | Tell the user to remove a document first. |
| `finalize` | `400` | Object not in storage yet | Retryable — the row stays `pending`; re-do the upload + finalize. |
| `finalize` | `409` | Doc not awaiting finalize (already finalized) | Refresh the doc; it's already past `pending`. |
| `detail` | `502` | Couldn't mint a download URL (storage blip) | Transient — retry shortly. |
| `PATCH` | `422` | Unknown `doc_type` | Restrict the picker to the known labels (§5). |

### 3.7 Gotchas

- **The `upload_url`/`token` are single-use and short-lived.** If the user dawdles between
  `init` and the PUT, re-run `init` for a fresh pair.
- **Upload is direct to Supabase** — do **not** send `Authorization` on that request, and set
  `Content-Type` to match the file (the bucket enforces `allowed_mime_types`).
- **Validation is asynchronous.** A `200` from `finalize` means "accepted for processing", not
  "valid". Only `status === "ready"` means valid.
- **Long `processing` ≠ failure.** Transient infrastructure issues are retried server-side, so
  surface "still processing" rather than erroring out hard.
- **Batch uploads:** there is no batch endpoint — loop `init`→PUT→`finalize` per file (they run
  concurrently fine; quota is enforced per call).

---

## 4. Data model

`Project 1:M Document` (CASCADE delete). UUID primary keys, timezone-aware timestamps.

**`projects`** — `id`, `name`, `location?`, `client?`, `consultant?`, `project_number?`,
`capacity_m3d?`, `owner_id → users.id (CASCADE, indexed)`, `created_at`, `updated_at`.

**`documents`** — `id` (also the storage object name), `project_id → projects.id
(CASCADE, indexed)`, `original_filename`, `storage_bucket`, `storage_path`,
`content_type`, `size_bytes?`, `sha256?` (reserved for future content dedup/integrity — no
consumer yet), `doc_type?` (indexed, **plain string** so the taxonomy can evolve without
migrations), `doc_type_source` (`auto`/`manual` enum), `revision_label?`, `revision_number?`,
`page_count?`, `sheet_names?` (JSONB), `status` (`pending`/`processing`/`ready`/`failed`
enum), `retention` (`persistent`/`transient` enum), `failure_reason?`,
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

1. **Signed direct-to-storage uploads, not a proxy.** File bytes never traverse the
   backend during upload — the strongest answer to the "don't exhaust RAM / don't hold
   a request open" constraints. The only server-side read is the background validation
   download, which is streamed chunk-by-chunk to a temp file (peak ≈ one chunk).
2. **Content validation is asynchronous, with self-healing.** Because the upload is direct,
   magic-byte/AV/zip/deep-parse checks can only run after the object exists. They run in a
   FastAPI `BackgroundTask`; the document carries a `status` the client polls. `finalize`
   commits `processing` **before** scheduling the task so the task's own session can't read a
   stale `pending`. A *content* failure is permanent (`failed` + object deleted); a *transient*
   failure (storage download error, scanner unreachable) leaves the row `processing`, and the
   periodic **`run_recovery_loop`** re-drives it (so a blip doesn't strand a document).
3. **The deep parse is the authoritative type gate.** `.docx` and `.xlsx` are both ZIP
   (OOXML) containers and share magic bytes, so the magic check is only a coarse first
   filter. A disguised/renamed ZIP is rejected by failing to parse with `openpyxl`
   (`.xlsx`) / `python-docx` (`.docx`) / `pypdf` (`.pdf`). `.xls` (OLE2) is accepted as a
   stored blob — no `xlrd`, so no sheet parsing.
4. **Validation hardening for untrusted files.** Before an OOXML file is handed to a parser,
   `archive.py` inspects the ZIP **central directory** (no extraction) and rejects
   decompression bombs (caps on total uncompressed size, compression ratio, and entry count).
   Optionally (`AV_SCAN_ENABLED`), the downloaded bytes are scanned with ClamAV first; the
   scan **fails closed** — if the scanner is unreachable the document is retried, never
   accepted unscanned. AV is off by default and requires a running clamd (see [§7.4](#74-optional-enable-clamav-malware-scanning)).
5. **`doc_type` is a string column, not a DB enum.** The taxonomy will churn (new
   equipment types / sections); a DB enum would need an `ALTER TYPE` per label. Allowed
   labels are a Python `StrEnum` validated in the pydantic layer instead.
6. **Owner-scoped, single-instance storage client.** The Supabase client is created once
   in `lifespan` (secret key, raised timeout) and shared via `get_storage` — a
   lifecycle-scoped singleton, like the OpenRouter client. Not a module-level global,
   because the httpx client must bind to the running loop and be closed on shutdown.
7. **Two non-transactional systems, compensating order.** `init` inserts the row then
   signs the URL (no object exists yet, so a rollback leaves nothing orphaned). On a
   permanent validation failure the background task deletes the storage object. No object is
   ever written before its row exists. `finalize` re-checks the *actual* object size against
   both the per-file and project-total caps (the quota lock is held at `init`; this is a
   single-instance backstop that closes the gap where a client under-declared its size).

---

## 7. Setup

### 7.1 Create the Supabase Storage bucket (out-of-band — not code/Alembic)

Create a bucket named `rfq-documents` (or whatever `SUPABASE_STORAGE_BUCKET` is set to),
**private**, with hard server-side guards so the direct upload is constrained before our
validation even runs:

- **Private** (no public read; objects reachable only via short-TTL signed URLs).
- **`file_size_limit`** = `MAX_UPLOAD_SIZE_MB` (Supabase rejects oversized PUTs at upload
  time, even if the client lies about declared size at `init`).
- **`allowed_mime_types`** = `application/pdf`, the OOXML docx/xlsx types, and
  `application/vnd.ms-excel`.
- **CORS / allowed origins** = your web app origin, so browser `uploadToSignedUrl` works.

### 7.2 Environment variables (`backend/.env`)

```dotenv
# ── Document storage / upload ────────────────────────────
SUPABASE_STORAGE_BUCKET=rfq-documents
MAX_UPLOAD_SIZE_MB=100          # per single file
MAX_FILES_PER_PROJECT=50        # per-project document count cap
MAX_PROJECT_TOTAL_SIZE_MB=1000  # per-project total size cap (re-checked at finalize)
SIGNED_DOWNLOAD_URL_TTL_S=600
STORAGE_CLIENT_TIMEOUT_S=120    # > storage3's 20s default, for streaming large objects
PENDING_UPLOAD_TTL_MIN=60       # stale-`pending` cutoff for opportunistic GC
COMPUTE_SHA256=true             # reserved for future dedup/integrity; safe to disable

# ── Background validation / recovery ─────────────────────
RECOVERY_SWEEP_INTERVAL_S=300   # how often stuck-`processing` docs are re-driven
ALLOWED_UPLOAD_EXTENSIONS=.pdf,.docx,.xlsx,.xls

# ── File-content safety (validation hardening) ───────────
MAX_DECOMPRESSED_SIZE_MB=500    # OOXML zip-bomb caps (central-directory check, no extraction)
MAX_COMPRESSION_RATIO=100
MAX_ARCHIVE_ENTRIES=10000
AV_SCAN_ENABLED=false           # opt-in ClamAV scan; requires a running clamd (§7.4)
CLAMD_HOST=
CLAMD_PORT=3310
CLAMD_SOCKET=
CLAMD_TIMEOUT_S=30.0
```

`SUPABASE_URL` / `SUPABASE_SECRET_KEY` (already required by the app) are reused for
storage. All values above have sensible defaults and are tunable.

> The signed **upload** URL/token TTL is controlled by Supabase (the token is short-lived
> and single-use); the backend does not configure it. (The former `SIGNED_UPLOAD_URL_TTL_S`
> setting was removed because storage3's `create_signed_upload_url` takes no expiry.)

### 7.3 Run the migration

```bash
# From backend/
uv run alembic upgrade head     # applies BOTH migrations: projects+documents, then retention
```

There are two migrations in this feature (`…_create_projects_and_documents` then
`…_add_document_retention`); `upgrade head` runs both. The first emits explicit
`GRANT SELECT, INSERT, UPDATE, DELETE ON projects, documents TO app_user` — the single most
likely place a fresh environment would otherwise break at runtime ("permission denied"),
because `ALTER DEFAULT PRIVILEGES` doesn't always cover tables created by the migration role.

### 7.4 (Optional) Enable ClamAV malware scanning

AV scanning is **off by default** and is a separate concern from the Python `clamd` client
that ships with the backend: `clamd` is only the *client* that talks to a **ClamAV daemon**
(`clamd`), which you run as its own service. To turn scanning on:

1. **Run a ClamAV daemon** reachable from the backend — e.g. the `clamav/clamav` Docker
   image as a sidecar (TCP `3310`), or `apt install clamav-daemon` on the same host (unix
   socket).
2. **Point the backend at it:** set `AV_SCAN_ENABLED=true` plus either `CLAMD_SOCKET` (same
   host) or `CLAMD_HOST`/`CLAMD_PORT` (networked daemon).
3. Because scanning **fails closed**, an unreachable daemon will keep documents in
   `processing` (retried by the recovery sweep) rather than accept them — so stand the daemon
   up *before* flipping the flag in any environment. Local Windows dev is best left with
   AV off.

---

## 8. How to test it

### 8.1 Unit / integration tests (no network, no Postgres, no Supabase)

```bash
# From backend/
uv run pytest                                  # full suite (171 tests, ~97% cov)
uv run pytest tests/test_services -q           # pure logic: classifier, filetype, upload, archive, antivirus
uv run pytest tests/test_api/test_documents.py # endpoint behavior via dependency overrides
```

Coverage of the new code:
- **Pure:** every classification rule + revision variant; magic-byte sniffing; the
  upload-request validators; `_extract_size`; the zip-bomb caps (`test_archive.py`).
- **Mocked:** `validate_stored_object` against real generated PDF/XLSX/DOCX fixtures plus
  garbage/parse-failure/download-error/**malware**/**zip-bomb** paths; `run_document_validation`
  success/failure/transient; `purge_stale_pending_documents`; `run_recovery_loop`
  (sweeps-then-sleeps, survives a sweep error); the ClamAV wrapper (`test_antivirus.py`:
  disabled/clean/infected/unreachable).
- **Endpoints:** `init` (success, `415`, `409`-via-caps, `404` not-owned),
  `finalize` (processing+schedule, `400` missing, `413` per-file → removed, `413`
  project-total → removed, `409`), list/detail (+`502` signing failure, empty URL for
  `failed`)/patch/delete (+storage-error swallow); the lifespan storage wiring; `get_storage`
  + owner loaders.

### 8.2 Manual end-to-end (real bucket + JWT)

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

### 8.3 Other gates

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run bandit -c pyproject.toml -r src
```

### 8.4 Testing with Apidog / Postman

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
`supabase_url`, `publishable_key`, `secret_key` (only to create a test user), and the
runtime-filled `token`, `project_id`, `document_id`, `upload_url`, `upload_token`,
`storage_path`. **Pre-declare them** so they persist, and set collection-level **Bearer
`{{token}}`** (turn it **off** for the one direct Supabase PUT).

> Apidog/Postman gotcha: extraction scripts must use `pm.environment.set(...)`
> (`pm.variables.set(...)` is run-scoped and is cleared after the request). Guard them so a
> failed request doesn't blank good values (`if (pm.response.code < 300) { … }`).

**0. Get a JWT** — `POST {{supabase_url}}/auth/v1/token?grant_type=password` with header
`apikey: {{publishable_key}}` and body `{ "email", "password" }`. (Create a confirmed user first
via `POST {{supabase_url}}/auth/v1/admin/users` with the `secret_key` and
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

> The signed `upload_url`/`token` are single-use and short-lived (controlled by Supabase) —
> re-run `init` to get a fresh pair if a step expires.

---

## 9. Risk handling (baked in)

| Risk | How it's handled |
|---|---|
| storage3's 20s httpx timeout aborts large streams | `STORAGE_CLIENT_TIMEOUT_S=120` on the client; bucket `file_size_limit` bounds object size. |
| `app_user` lacks DML on new tables → "permission denied" | Migration emits explicit `GRANT … TO app_user` unconditionally. |
| storage3 `download()` buffers the whole object in RAM | Background validation streams via a signed URL + `httpx.AsyncClient.stream`, chunked to disk — never `download()`. |
| OOXML **decompression bomb** (small upload → huge expansion) | `archive.py` reads the ZIP central directory (no extraction) and rejects over the uncompressed-size / ratio / entry-count caps before parsing → permanent `failed`. |
| **Malicious content** | Optional ClamAV scan (`AV_SCAN_ENABLED`) of the downloaded bytes, **fail-closed**; plus private bucket, `allowed_mime_types` + `file_size_limit`, prompt deletion of `failed` objects, and files only ever downloaded server-side for validation — never executed/served inline. |
| Async rejection, orphaned `pending` uploads, or docs stuck `processing` | `status`/`failure_reason` lifecycle for polling; `purge_stale_pending_documents` runs opportunistically on every `init`; **`run_recovery_loop`** periodically re-drives stuck-`processing` docs (crash/restart or transient blip). |
| Client under-declares size at `init` to dodge the project cap | `finalize` re-checks the *actual* object size against the per-file **and** project-total caps; on breach the doc is `failed` and the object removed. |
| Storage object orphaned when a delete's remove fails | Logged (warning) so it's observable; the row is still removed (best-effort). |
| Browser direct upload needs CORS | Bucket runbook sets allowed origins; `init` returns everything the client needs for `uploadToSignedUrl`. |

---

## 10. Out of scope / explicit follow-ups

- Deleting `transient` objects after RFQ generation (the `retention` tag is the hook; the
  delete fires in the Generate feature) and storing the generated RFQ output.
- Full-text extraction + token-aware LLM chunking (Extract/Generate feature; intake already
  provides the RAM-bounded byte download via `download_object_to_tempfile()`).
- **AV is opt-in, not turnkey:** enabling it requires standing up a ClamAV daemon ([§7.4](#74-optional-enable-clamav-malware-scanning)).
- A durable task queue / horizontal scaling for background validation (today it's an
  in-process `BackgroundTask` + a single-instance recovery loop, which is enough for one
  instance; multi-instance would want `SELECT … FOR UPDATE SKIP LOCKED` in the sweep).
- `.xls` sheet-name parsing (would need `xlrd`); accepted/stored/validated as a blob now.
- Content dedup/integrity using the stored `sha256` (computed and persisted; no consumer yet).
- Teams / collaboration sharing (v1 is owner-scoped).
- RLS policies on the new tables (no runtime effect while `app_user` has `BYPASSRLS`).
- A true batch upload endpoint (the client loops single-file `init`/`finalize`; the per-file
  pipeline is reusable).

---

## 11. FAQ

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
`failed`. A ZIP designed to explode on open is caught earlier by the central-directory
zip-bomb guard.

**Q: Is malware scanning on?**
A: Off by default. It's opt-in (`AV_SCAN_ENABLED`) and needs a running ClamAV daemon
([§7.4](#74-optional-enable-clamav-malware-scanning)). When on, it scans before parsing and
fails closed (an unreachable scanner leaves the doc `processing` for retry, never accepted).

**Q: A document has been `processing` for a while — is it stuck?**
A: Probably just slow, or it hit a transient blip (storage/scanner). The periodic recovery
sweep (`RECOVERY_SWEEP_INTERVAL_S`) re-drives such documents, so they resolve without a
restart. Treat long `processing` as "check back", not "failed".

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

**Q: How is the secret key kept safe?**
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

## 12. PR / review checklist

- [ ] Private Supabase bucket exists with `file_size_limit` + `allowed_mime_types` + CORS.
- [ ] `uv run alembic upgrade head` applied (both migrations); `app_user` can `INSERT`/`SELECT` the new tables.
- [ ] `uv run pytest` green (171) with coverage ≥ 80%.
- [ ] `uv run ruff check src tests` and `uv run mypy src` clean.
- [ ] `uv run bandit -c pyproject.toml -r src` clean; no secrets committed.
- [ ] Manual end-to-end ([§8.2](#82-manual-end-to-end-real-bucket--jwt)) reaches `ready`, and a garbage file reaches `failed`.
- [ ] If enabling AV: a ClamAV daemon is reachable and `AV_SCAN_ENABLED` is set ([§7.4](#74-optional-enable-clamav-malware-scanning)).
