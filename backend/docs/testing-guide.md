# Testing the Document Intake feature with Apidog / Postman / curl

A practical, end‑to‑end walkthrough for exercising the **upload + classification**
pipeline against a running backend and a live Supabase project. It covers the happy
path, classification checks, and the failure scenarios — all verified against the
running app.

> For the feature design and API reference, see [`document-intake.md`](./document-intake.md).
> For the next stage (extraction/validation), see
> [`extraction-and-validation-guide.md`](./extraction-and-validation-guide.md).

---

## 1. The mental model

- **Auth:** every `/api/v1/**` route needs `Authorization: Bearer <user JWT>`. The JWT is a
  **Supabase user access token** (algorithm **ES256**, verified by the backend via the
  project's JWKS endpoint — no shared secret). The API **keys** below are only used to talk
  to Supabase Auth, never sent to our API.
- **API keys (new Supabase scheme):** `sb_publishable_…` (client‑safe, used as the `apikey`
  header when logging in) and `sb_secret_…` (server‑only, used for the Admin API). They live
  in `backend/.env` as `SUPABASE_PUBLISHABLE_KEY` / `SUPABASE_SECRET_KEY`.
- **Upload is 3 steps and step 2 does NOT hit our backend:**
  1. `POST …/documents/init` → returns a signed `upload_url` + `token`.
  2. `PUT` the bytes **directly to Supabase Storage** (the signed URL; no Bearer needed).
  3. `POST …/documents/{id}/finalize` → backend verifies the object and runs validation in
     the background; you then **poll** `GET …/documents/{id}` until `ready` / `failed`.

---

## 2. Prerequisites

```bash
# from backend/ — point .env at the target Supabase project, then:
uv run alembic upgrade head                       # applies all migrations (incl. the trigger + retention)
uv run uvicorn app.main:app --reload --port 8000  # app on http://127.0.0.1:8000
```

- The Storage bucket (`SUPABASE_STORAGE_BUCKET`, default `rfq-documents`) must exist in that
  project — **private**, with `file_size_limit` and `allowed_mime_types` set (see
  `document-intake.md` §6.1).
- Quick liveness/readiness check:
  - `GET http://127.0.0.1:8000/health` → `{"status":"ok",...}` (process is up).
  - `GET http://127.0.0.1:8000/ready` → `200 {"status":"ready"}` when the DB is reachable
    and the storage client is wired; `503` otherwise. Use `/ready` as the deploy gate.

---

## 3. Getting a test user — use the **Admin API**, not public sign‑up

This project has email **confirmation** + **deliverability validation** enabled, so the public
`POST /auth/v1/signup` endpoint will reject synthetic addresses:

| You send | Supabase returns |
|---|---|
| `…@example.com` (or any RFC‑2606 reserved domain) | `400 email_address_invalid` |
| a made‑up domain with no MX record | `400 email_address_invalid` |
| a real domain (e.g. `gmail.com`) | sends a real confirmation email → `429 over_email_send_rate_limit` once you retry |

So for automated/manual testing, **create a confirmed user via the Admin API** (which bypasses
this), then log in for a token. A DB trigger (`on_auth_user_created`) mirrors the new auth user
into `public.users`, satisfying the `projects.owner_id` foreign key automatically.

```bash
SUPA="https://<project-ref>.supabase.co"
PUB="sb_publishable_..."     # SUPABASE_PUBLISHABLE_KEY
SEC="sb_secret_..."          # SUPABASE_SECRET_KEY
EMAIL="qa+$(date +%s)@gmail.com"
PASS='Apidog!Test123'

# create a confirmed user (Admin API; secret key in BOTH apikey and Authorization)
curl -s -X POST "$SUPA/auth/v1/admin/users" \
  -H "apikey: $SEC" -H "Authorization: Bearer $SEC" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\",\"email_confirm\":true}"

# log in -> access_token (publishable key as apikey)
TOKEN=$(curl -s -X POST "$SUPA/auth/v1/token?grant_type=password" \
  -H "apikey: $PUB" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" | jq -r .access_token)
```

---

## 4. Apidog / Postman setup

Create an **environment** with these variables (pre‑declare so scripts can persist them):

| Variable | Value |
|---|---|
| `base_url` | `http://127.0.0.1:8000` |
| `supabase_url` | `https://<project-ref>.supabase.co` |
| `publishable_key` | `sb_publishable_…` |
| `secret_key` | `sb_secret_…` (only for creating test users) |
| `token`, `project_id`, `document_id`, `upload_url`, `upload_token` | filled at runtime |

Set the **collection‑level Auth** to **Bearer `{{token}}`**, and turn it **off** on the single
direct‑to‑Supabase PUT (step 2).

> Scripts must use `pm.environment.set(...)` (Postman) / the equivalent in Apidog —
> `pm.variables.set(...)` is run‑scoped and cleared after the request. Guard saves so a failed
> call doesn't blank a good value: `if (pm.response.code < 300) { … }`.

**Save‑token test script** (on the login request):
```javascript
if (pm.response.code < 300) pm.environment.set("token", pm.response.json().access_token);
```

---

## 5. Happy path

### 5.1 Create a project
`POST {{base_url}}/api/v1/projects` (Bearer) — body `{ "name": "Kohafa WWTP", "client": "WABAG" }` → **201**.
Save: `pm.environment.set("project_id", pm.response.json().id)`.

```bash
curl -s -X POST "$BASE/api/v1/projects" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"name":"Kohafa WWTP","client":"WABAG"}'
```

### 5.2 Init the upload
`POST {{base_url}}/api/v1/projects/{{project_id}}/documents/init` (Bearer) — body:
```json
{ "filename": "01_Employer_Technical_Specifications_Rev02.pdf",
  "size_bytes": 2400000 }
```
→ **201**. Verify `document.doc_type == "Employer Technical Specifications"`,
`revision_number == 2`, `retention == "persistent"`, `status == "pending"`. Save:
```javascript
const j = pm.response.json();
pm.environment.set("document_id", j.document.id);
pm.environment.set("upload_url", j.upload_url);
pm.environment.set("upload_token", j.token);
```

### 5.3 Upload bytes **directly to Supabase** (no Bearer)
`PUT {{upload_url}}`. Two ways that work — pick one:
- **Multipart** (matches the official SDK and is the most reliable):
  `Body → form-data`, one field named **`file`** of type *File*. Add header `x-upsert: true`.
- **Binary:** `Body → Binary` = the file, header `Content-Type` matching the file.

```bash
curl -s -X PUT "$UPLOAD_URL" -H "x-upsert: true" \
  -F "file=@01_Employer_Technical_Specifications_Rev02.pdf;type=application/pdf"
# → {"Key":"rfq-documents/<project>/<document>.pdf"}
```

> The `upload_url`/`token` are single‑use and short‑lived (the TTL is controlled by
> Supabase, not the backend). Re‑run `init` for a fresh pair if a step expires.

### 5.4 Finalize
`POST {{base_url}}/api/v1/documents/{{document_id}}/finalize` (Bearer, no body) → **200**,
`status == "processing"`.

### 5.5 Poll until done
`GET {{base_url}}/api/v1/documents/{{document_id}}` (Bearer) until `status` is `ready` or
`failed`. On `ready`: PDFs have `page_count`, XLSX have `sheet_names`, and a `download_url` is
returned.

---

## 6. Classification checks

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
and recomputes `retention`).

---

## 7. Failure scenarios (negative tests)

All verified against the running app. `<doc>` = run init→PUT→finalize→poll.

### A. Rejected at `init` (cheap, before any upload)
| Test | Request | Expect |
|---|---|---|
| bad extension | init `"filename":"malware.exe"` | **415** |
| invalid size | init `"size_bytes":0` | **422** (Pydantic `gt=0`) |
| declared too large | init `"size_bytes": 209715200` (200 MB) | **413** |
| project not yours / missing | init on a random `project_id` | **404** |

### B. Content ≠ declared type (the layered validation)
| Test | What to upload | Expect (after poll) |
|---|---|---|
| XLSX bytes as `report.pdf` | xlsx file, declared `.pdf` | `failed` — *"File content is not a valid .pdf file"* (magic‑byte gate) |
| XLSX bytes as `spec.docx` | xlsx file, declared `.docx` | `failed` — *"could not be parsed as .docx …"* (magic matches OOXML, **deep parse** catches it) |
| junk text as `broken.pdf` | a `.txt` renamed `.pdf` | `failed` — *"not a valid .pdf file"* |

These are **permanent** failures → the document ends `failed` **and its storage object is
removed**.

### C. Size mismatch under the cap (server trusts the actual size)
| Test | Steps | Expect |
|---|---|---|
| declared ≠ actual | init `"size_bytes": 999`, upload a real (smaller/larger but ≤ cap) file, finalize, poll | `ready`; `size_bytes` is **auto‑corrected** to the real size read from storage |

The client's declared size is not trusted — `finalize` reads the true size via
`storage.info()` and corrects it. It only hard‑fails (`413`, `failed`) if the *actual* object
exceeds the cap.

### D. Lifecycle / state guards
| Test | Request | Expect |
|---|---|---|
| finalize without uploading | init, then finalize (skip the PUT) | **400** "Uploaded object not found"; document stays `pending` (retryable) |
| finalize twice | finalize an already‑`ready`/`processing` doc | **409** |

### E. Auth & ownership
| Test | Request | Expect |
|---|---|---|
| no token | `GET …/projects` with no `Authorization` | **401** |
| malformed token | `Authorization: Bearer not.a.jwt` | **401** "Invalid or expired token" (no internals leaked) |
| random document id | `GET …/documents/<random uuid>` | **404** |
| another project's documents | `GET …/projects/<random uuid>/documents` | **404** (hides existence) |

> **Transient** failures (a real storage/network outage during validation) behave differently
> from the permanent failures above: the document is **left `processing`, its bytes kept**, and
> retried by the startup recovery sweep (`recover_stuck_processing_documents`). That path is hard
> to trigger on demand against live Supabase; it's covered by the unit tests instead.

---

## 8. Cleanup

There's no `DELETE /projects` endpoint, but deleting documents removes their storage objects,
and deleting the auth user cascades the `public.users` row → projects → documents.

```bash
# per test user: delete their docs (removes storage objects), then the user
curl -s -X DELETE "$BASE/api/v1/documents/$DOC_ID" -H "Authorization: Bearer $TOKEN"   # 204
curl -s -X DELETE "$SUPA/auth/v1/admin/users/$USER_ID" -H "apikey: $SEC" -H "Authorization: Bearer $SEC"
```

An **orphaned** storage object = a bucket object whose path is not in any live
`documents.storage_path` row (happens if a user/project was deleted outside the API). Only those
are safe to delete from the bucket — never delete an object that still has a live document row.

---

## 9. Gotchas

- **PowerShell:** variables are case‑insensitive (`$xlsx` and `$XLSX` are the *same* variable),
  and `curl` is an alias for `Invoke-WebRequest` — call `curl.exe` explicitly. `.env` values may
  be single‑quoted; strip the quotes when parsing them in a script.
- **`jq`** is used in the bash snippets to read JSON; on Windows use Git Bash or parse with
  PowerShell's `ConvertFrom-Json`.
- **One PUT, no Bearer:** the only request that must *not* carry the API Bearer token is the
  direct‑to‑Supabase upload (step 5.3) — its auth is the signed `token` in the URL.
