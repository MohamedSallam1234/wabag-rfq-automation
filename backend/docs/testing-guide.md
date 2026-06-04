# Testing the Document Intake feature with curl / Apidog / Postman

A practical, end-to-end walkthrough for exercising the **upload + classification** pipeline
against a running backend and a live Supabase project. It covers the happy path,
classification checks, and the failure scenarios.

> For the feature design and API reference, see [`document-intake.md`](./document-intake.md).

---

## 1. The mental model

- **No authentication.** Every `/api/v1/**` route is **open** — there is no `Authorization`
  header and no owner-scoping. (If you front the service with a gateway that injects auth,
  that's transparent to these calls.)
- **Upload is a single request.** `POST …/projects/{id}/documents` as `multipart/form-data`
  with one field named **`file`**. The backend validates the bytes, stores them in Supabase
  Storage, classifies the filename, and returns the created document — all synchronously. A
  `201` means *validated and stored*; a `4xx` means *nothing was stored*. There is no
  `init`/`finalize`, no direct-to-Supabase PUT, and no polling.
- **The secret key** (`sb_secret_…`, in `backend/.env` as `SUPABASE_SECRET_KEY`) is used only
  by the backend to talk to Supabase Storage — never sent by a client.

---

## 2. Prerequisites

```bash
# from backend/ — point .env at the target Supabase project, then:
uv run alembic upgrade head                       # single squashed migration
uv run uvicorn app.main:app --reload --port 8000  # app on http://127.0.0.1:8000
```

- The Storage bucket (`SUPABASE_STORAGE_BUCKET`, default `rfq-documents`) must exist in that
  project — **private**, with `file_size_limit` and `allowed_mime_types` set (see
  `document-intake.md` §7.1).
- **Reusing an old database?** The squashed migration starts from scratch
  (`down_revision = None`), so a DB that still carries the previous migration history must be
  reset first: `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` then re-run the migration.
- Quick liveness/readiness check:
  - `GET http://127.0.0.1:8000/health` → `{"status":"ok",...}` (process is up).
  - `GET http://127.0.0.1:8000/ready` → `200 {"status":"ready"}` when the DB is reachable and
    the storage client is wired; `503` otherwise. Use `/ready` as the deploy gate.

---

## 3. Happy path (curl)

```bash
BASE="http://127.0.0.1:8000"

# 3.1 Create a project  → 201
PROJECT_ID=$(curl -s -X POST "$BASE/api/v1/projects" \
  -H "Content-Type: application/json" \
  -d '{"name":"Kohafa WWTP","client":"WABAG"}' | jq -r .id)

# 3.2 Upload a document (multipart, field "file")  → 201, classified, bytes stored
curl -s -X POST "$BASE/api/v1/projects/$PROJECT_ID/documents" \
  -F "file=@01_Employer_Technical_Specifications_Rev02.pdf;type=application/pdf" | jq

# Expect: doc_type="Employer Technical Specifications", revision_number=2,
#         retention="persistent", page_count set, doc_type_source="auto".

# 3.3 List the project's documents (newest first)  → 200
curl -s "$BASE/api/v1/projects/$PROJECT_ID/documents" | jq

# 3.4 Fetch detail + a signed download URL  → 200
DOC_ID=$(curl -s "$BASE/api/v1/projects/$PROJECT_ID/documents" | jq -r '.[0].id')
curl -s "$BASE/api/v1/documents/$DOC_ID" | jq .download_url

# 3.5 Delete (also best-effort removes the storage object)  → 204
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE "$BASE/api/v1/documents/$DOC_ID"
```

> `jq` is used to read JSON; on Windows use Git Bash or parse with PowerShell's
> `ConvertFrom-Json`. PowerShell aliases `curl` to `Invoke-WebRequest` — call `curl.exe`
> explicitly.

---

## 4. Classification checks

Upload these filenames (any valid PDF/XLSX bytes of the right type) and confirm the result.
This exercises the prefix rules, the `DataSheet` suffix rule, revision parsing, and retention
mapping:

| filename | expected `doc_type` | `rev` | `retention` |
|---|---|---|---|
| `01_Employer_Technical_Specifications_Rev02.pdf` | Employer Technical Specifications | 2 | persistent |
| `02_Process_Engineering_Rev00.pdf` | Process Engineering Profile | 0 | persistent |
| `03_RFQ_Blower_Template_Rev01.xlsx` | RFQ Template | 1 | transient |
| `04_Hydraulic_Profile.pdf` | Hydraulic Calculation Profile | – | persistent |
| `05_Equipment_List_Rev01.xlsx` | Equipment List | 1 | persistent |
| `Centrifugal_Pump_DataSheet_Rev03.pdf` | Equipment DataSheet | 3 | transient |
| `random_notes.pdf` | *(null)* | – | transient |

A **`null` doc_type** is expected for unmatched names — set it later with
`PATCH …/documents/{id}` `{ "doc_type": "Equipment List" }` (sets `doc_type_source: "manual"`
and recomputes `retention`):

```bash
curl -s -X PATCH "$BASE/api/v1/documents/$DOC_ID" \
  -H "Content-Type: application/json" -d '{"doc_type":"Equipment List"}' | jq
```

---

## 5. Failure scenarios (negative tests)

The upload is synchronous, so failures come back immediately and **nothing is stored**.

| Test | Request | Expect |
|---|---|---|
| bad extension | upload `malware.exe` | **415** (rejected before any storage) |
| content ≠ extension | upload XLSX bytes named `report.pdf` | **422** "File content is not a valid .pdf file" (magic-byte gate) |
| disguised OOXML | upload XLSX bytes named `spec.docx` | **422** "could not be parsed as .docx …" (magic matches OOXML; the **deep parse** catches it) |
| unparseable | upload a `.txt` renamed `broken.pdf` | **422** "not a valid .pdf file" |
| oversized | upload a file larger than `MAX_UPLOAD_SIZE_MB` | **413** |
| missing project | upload to a random `project_id` | **404** |
| missing document | `GET …/documents/<random uuid>` | **404** |
| bad override | `PATCH … {"doc_type":"Nonsense"}` | **422** (not a known label) |

```bash
# bad extension → 415
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  "$BASE/api/v1/projects/$PROJECT_ID/documents" -F "file=@malware.exe"

# XLSX bytes presented as .pdf → 422
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  "$BASE/api/v1/projects/$PROJECT_ID/documents" \
  -F "file=@report.pdf;type=application/pdf"   # report.pdf actually contains XLSX bytes
```

---

## 6. Apidog / Postman setup

Create an **environment** with `base_url` (`http://127.0.0.1:8000`), and (filled at runtime)
`project_id` and `document_id`. **No collection-level auth is needed** — the endpoints are open.

| Request | Method & URL | Body | Save script |
|---|---|---|---|
| Create project | `POST {{base_url}}/api/v1/projects` | JSON `{ "name": "Kohafa WWTP" }` | `if (pm.response.code < 300) pm.environment.set("project_id", pm.response.json().id)` |
| Upload | `POST {{base_url}}/api/v1/projects/{{project_id}}/documents` | **form-data**, one field **`file`** of type *File* | `if (pm.response.code < 300) pm.environment.set("document_id", pm.response.json().id)` |
| List | `GET {{base_url}}/api/v1/projects/{{project_id}}/documents` | – | – |
| Detail | `GET {{base_url}}/api/v1/documents/{{document_id}}` | – | – |
| Override | `PATCH {{base_url}}/api/v1/documents/{{document_id}}` | JSON `{ "doc_type": "Equipment List" }` | – |
| Delete | `DELETE {{base_url}}/api/v1/documents/{{document_id}}` | – | – |

> Apidog/Postman gotcha: extraction scripts must use `pm.environment.set(...)`
> (`pm.variables.set(...)` is run-scoped and cleared after the request). Guard saves so a
> failed request doesn't blank a good value (`if (pm.response.code < 300) { … }`).

---

## 7. Cleanup

There's no `DELETE /projects` endpoint, but deleting a document removes its storage object:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE "$BASE/api/v1/documents/$DOC_ID"  # 204
```

An **orphaned** storage object = a bucket object whose path is not in any live
`documents.storage_path` row (e.g. if a row was removed out-of-band, or a rare upload-then-DB
failure occurred). Only those are safe to delete from the bucket — never delete an object that
still has a live document row.
