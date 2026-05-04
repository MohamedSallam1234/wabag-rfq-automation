# Project Setup Guide — Backend

> **For new teammates.** This document explains how the backend is wired up, why we made the choices we did, and how to get a working local environment so you can start contributing.

If you only have 5 minutes, read [TL;DR](#tldr) and [Quick Start](#quick-start) and ask the team for the secrets. The rest is reference material for when you need it.

---

## TL;DR

**Stack:** FastAPI + Supabase (Auth + Storage + Realtime + Postgres) + SQLAlchemy 2.x async + Alembic + uv.

**Mental model:** Two access paths to the same Postgres database.

1. **Frontend → Supabase** for auth, storage, realtime (via Supabase JS SDK).
2. **Frontend → FastAPI → Postgres** for business logic (via SQLAlchemy + asyncpg).

**Rules of the road:**
- Alembic owns the schema. **Never** click around in Supabase Studio to change tables.
- FastAPI uses **SQLAlchemy** for DB queries, **not** the Supabase Python client.
- `app_user` is the role our app connects as. `postgres` is for migrations only.
- Local dev runs against a local Supabase stack via the CLI, **not** the hosted project.

---

## Quick Start

Prereqs: Python 3.12, Docker Desktop, [uv](https://github.com/astral-sh/uv), [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started), Git.

```bash
# 1. Clone and install deps
git clone <repo-url>
cd backend
uv sync

# 2. Start local Supabase (Docker must be running)
supabase start
# Save the printed anon key, service_role key, and JWT secret

# 3. Get .env.local from a teammate (or create from .env.example)
#    Required: SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_JWT_SECRET

# 4. Run migrations against the local DB
uv run alembic upgrade head

# 5. Run the API
uv run uvicorn app.main:app --reload --app-dir src
```

Open http://127.0.0.1:8000/docs for Swagger. Open http://127.0.0.1:54323 for Supabase Studio (local dashboard).

---

## Project Structure

```
backend/
├── alembic/
│   ├── versions/         # Migration files — one per schema change
│   └── env.py            # Async-configured Alembic environment
├── alembic.ini
├── src/
│   └── app/
│       ├── core/
│       │   ├── config.py       # Pydantic Settings (loads .env.<APP_ENV>)
│       │   ├── database.py     # Async engine + session factory + Base
│       │   └── security.py     # JWT verification via Supabase JWKS
│       ├── models/             # SQLAlchemy ORM models
│       ├── schemas/            # Pydantic request/response schemas
│       ├── api/
│       │   ├── deps.py         # FastAPI dependencies (get_db)
│       │   └── routes/         # API endpoints
│       ├── services/           # Business logic
│       └── main.py             # FastAPI app
├── supabase/                   # Local Supabase config (committed)
│   └── config.toml
├── .env.example                # Template — committed
├── .env.local                  # Local secrets — NEVER committed
├── .env.production             # Prod secrets — NEVER committed, share via password manager
└── pyproject.toml
```

---

## The Two-Path Architecture

This is the most important concept to internalize. Supabase gives you a database, but it also gives you Auth, Storage, and Realtime — and those services talk to the database directly using their own roles and access patterns. We have a backend that *also* talks to the database. Both paths coexist.

| Concern | Who handles it |
|---|---|
| User signup, login, password reset, email confirmation, OAuth | Supabase Auth (frontend uses Supabase JS SDK) |
| File uploads, signed URLs | Supabase Storage (frontend uploads directly with signed URLs) |
| Live subscriptions, presence | Supabase Realtime (frontend subscribes directly) |
| All business logic, validation, complex queries | **Our FastAPI backend** |
| Schema migrations | **Alembic, run by us** |

**What our FastAPI does NOT do:**
- It does not handle signup or login. The frontend does that against Supabase Auth and gets a JWT.
- It does not use the `supabase-py` client for database queries. Use SQLAlchemy.

**What it DOES do:**
- It receives the JWT from the frontend in `Authorization: Bearer <token>` headers.
- It verifies the JWT against Supabase's JWKS (public keys).
- It runs business logic and queries the database via SQLAlchemy.

---

## Database Roles

We use **two different Postgres roles** for least-privilege access:

| Role | What it can do | Used by |
|---|---|---|
| `postgres` | Everything (superuser) | Alembic migrations only |
| `app_user` | SELECT, INSERT, UPDATE, DELETE on `public.*`. Has BYPASSRLS. | FastAPI runtime |

**Why two roles?**
- The app should never have permission to drop tables, even by accident.
- It forces us to think about RLS for defense-in-depth.
- `BYPASSRLS` on `app_user` lets our backend enforce auth in Python instead of via RLS (simpler), while RLS still protects us if anyone connects directly with the anon key.

The `app_user` role is created by an Alembic migration locally. In production it was created manually with a strong password (so the password isn't in version control).

---

## Connection Strings (important — don't mix these up)

Supabase exposes **three** connection strings. Each has a purpose:

| Type | Port | Use for | Notes |
|---|---|---|---|
| Direct | 5432 | Alembic migrations | Persistent connection, supports DDL fully |
| Session pooler (Supavisor) | 5432 | Long-lived app servers | Supports prepared statements |
| Transaction pooler (Supavisor) | 6543 | Serverless / short-lived | **No prepared statements** — set `statement_cache_size=0` |

**What we use:**
- **Local:** Direct connection (port 54322) for everything — local stack has no pooler.
- **Production migrations** (`MIGRATION_DATABASE_URL`): Session pooler with `postgres` user.
- **Production app traffic** (`DATABASE_URL`): Session pooler with `app_user`.

**Common gotcha:** Supabase production URLs use `aws-0-<region>.pooler.supabase.com` for the pooler. Username for the pooler is `postgres.<project-ref>` (dotted form), not just `postgres`.

---

## Environment Configuration

We use [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) loading from `.env.<APP_ENV>` files.

| File | When loaded | Where the values come from |
|---|---|---|
| `.env.local` | `APP_ENV` unset or `local` | `supabase status` output |
| `.env.production` | `APP_ENV=production` | Prod Supabase dashboard → Settings → API/Database |

**Required keys** (see `.env.example`):

```bash
APP_ENV=local
DATABASE_URL=postgresql+asyncpg://app_user:...@host:port/postgres
MIGRATION_DATABASE_URL=postgresql+asyncpg://postgres:...@host:port/postgres
SUPABASE_URL=http://127.0.0.1:54321        # or https://<ref>.supabase.co for prod
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...               # server-only, NEVER expose to frontend
SUPABASE_JWT_SECRET=...                     # legacy; not used since we verify via JWKS
```

`.env.production` is **not committed**. Get it from a teammate via a password manager.

---

## Authentication Flow

We use **ES256 asymmetric JWTs** (Supabase's modern default). Verification happens via JWKS (the public key endpoint), not a shared secret.

```
1. User signs up/logs in via Supabase Auth (frontend calls supabase.auth.signUp / signInWithPassword)
2. Supabase returns a JWT signed with their private key
3. Frontend sends requests to FastAPI with Authorization: Bearer <jwt>
4. FastAPI's get_current_user dependency:
   - Fetches Supabase's public keys from {SUPABASE_URL}/auth/v1/.well-known/jwks.json (cached)
   - Verifies the JWT signature, audience, and expiry
   - Returns the decoded payload (contains sub = user UUID, email, role, etc.)
5. Routes use Depends(get_current_user) to require auth
6. Use auth["sub"] as the user_id everywhere in business logic
```

The JWKS client caches keys with a 5-minute TTL. If Supabase rotates keys, we pick them up automatically.

---

## User Profiles — How They Work

Supabase Auth manages `auth.users` (login, password, sessions). We have our own `public.users` table for profile data (name and whatever else we need).

**One profile per auth user, same UUID.** The `id` column in `public.users` matches `auth.users.id` exactly.

**Profiles are auto-created by a database trigger.** When a row is inserted into `auth.users` (i.e., when someone signs up), the trigger fires and creates the matching `public.users` row.

```sql
-- Defined in an Alembic migration
CREATE FUNCTION public.handle_new_user() RETURNS trigger
SECURITY DEFINER
AS $$
BEGIN
    INSERT INTO public.users (id, name)
    VALUES (NEW.id, COALESCE(NEW.raw_user_meta_data->>'name', NEW.email));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER on_auth_user_created
AFTER INSERT ON auth.users
FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
```

**Frontend signup:**

```javascript
await supabase.auth.signUp({
  email,
  password,
  options: { data: { name: "Jane Doe" } }   // ends up in raw_user_meta_data
});
```

By the time signup returns, the profile row already exists. **The backend never creates profile rows directly.** It only reads/updates them.

Our routes for users should be:
- `GET /users/me` — get current user's profile
- `PATCH /users/me` — update current user's profile

Never `POST /users` — that's the trigger's job.

---

## Row Level Security (RLS)

RLS is enabled on all our tables. Policies check `auth.uid()` (the authenticated user's UUID).

**For `users` table:**
- `users_select_own`: Users can read their own profile (`id = auth.uid()`)
- `users_update_own`: Users can update their own profile

**No INSERT policy** — only the trigger creates rows, and it runs as the function owner (postgres) which bypasses RLS.

**No DELETE policy** — profile deletion happens via cascade from `auth.users` deletion or via admin action, never user action.

**Important:** Our backend connects as `app_user`, which has `BYPASSRLS`. This means RLS doesn't constrain our backend — we enforce auth in Python (`get_current_user` + filtering by `auth["sub"]`). RLS exists as defense-in-depth for any code path that connects with the anon key (e.g., the frontend if it ever queries Supabase directly).

---

## Working with Migrations

**Every schema change goes through Alembic.** No exceptions. No clicking in Studio.

### Creating a migration

```bash
# 1. Edit your model in src/app/models/
# 2. Generate migration
uv run alembic revision --autogenerate -m "add description to items"

# 3. ALWAYS review the generated file in alembic/versions/
#    Autogenerate is not perfect — check the SQL it produced.

# 4. Apply locally
uv run alembic upgrade head

# 5. Test that things still work
uv run pytest    # if we have tests yet
```

### Useful commands

```bash
uv run alembic current          # what revision is the DB at?
uv run alembic history          # all revisions
uv run alembic heads            # latest revision in code
uv run alembic check            # detect drift between models and migrations
uv run alembic downgrade -1     # roll back one migration (locally only!)
uv run alembic upgrade head     # apply all pending
```

### Important: async + Alembic gotchas

Our setup uses asyncpg, which has stricter rules than psycopg:

1. **One SQL statement per `op.execute()` call.** asyncpg can't execute multiple statements in one prepared statement. Split them up.
2. **Don't use `op.execute()` for DDL when there's an `op.create_table()` equivalent** — let Alembic generate native operations where possible.
3. **`DO $$ ... $$` blocks count as a single statement** — those are fine in one execute.

Example of the right way:

```python
def upgrade():
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")  # one statement
    op.execute("CREATE POLICY foo ON users FOR SELECT USING (...)")  # one statement
    # NOT: op.execute("ALTER TABLE ...; CREATE POLICY ...;")  -- would fail
```

### Running migrations against production

```bash
# Set the env, run, unset
$env:APP_ENV="production"             # PowerShell
# or: export APP_ENV=production       # bash/zsh

uv run alembic upgrade head

Remove-Item Env:APP_ENV               # PowerShell
# or: unset APP_ENV                   # bash/zsh
```

**Currently we do this manually from a developer machine.** Eventually this will move to CI/CD (see [Future Work](#future-work)).

---

## Local Development Workflow

```bash
# Start of day
supabase start                                 # spin up local stack
uv run uvicorn app.main:app --reload --app-dir src

# Stop end of day
# Ctrl+C the uvicorn process
supabase stop                                  # stop local stack
```

**Local URLs:**
- API: http://127.0.0.1:8000
- Swagger: http://127.0.0.1:8000/docs
- Supabase Studio (local dashboard): http://127.0.0.1:54323
- Supabase API (auth, storage): http://127.0.0.1:54321
- Postgres: `localhost:54322` (user `postgres`, password `postgres`)
- Inbucket (catches local emails): http://127.0.0.1:54324

**Creating a test user:** Local Studio → Authentication → Users → "Add user" → check "Auto Confirm User."

**Getting a JWT for testing:**

```powershell
$anonKey = "<from supabase status>"
$body = @{ email = "test@example.com"; password = "<your-password>" } | ConvertTo-Json
$headers = @{ "apikey" = $anonKey; "Content-Type" = "application/json" }
$response = Invoke-RestMethod -Uri "http://127.0.0.1:54321/auth/v1/token?grant_type=password" -Method Post -Headers $headers -Body $body
$response.access_token
```

Use that token in Swagger's "Authorize" button or as `Authorization: Bearer <token>` in curl.

---

## Common Gotchas

| Symptom | Likely cause |
|---|---|
| `cannot insert multiple commands into a prepared statement` | Multiple SQL statements in one `op.execute()` — split them. |
| `ModuleNotFoundError: No module named 'app'` | Run with `--app-dir src` or set `PYTHONPATH=src`. |
| `Invalid token: The specified alg value is not allowed` | JWT is ES256, code expects HS256. We use ES256 + JWKS now. |
| `Unable to find a signing key that matches: "<kid>"` | Either `SUPABASE_URL` is pointing at the wrong project, or PyJWKClient cached an old JWKS. Restart uvicorn. |
| `permission denied for schema public` (during migration) | `MIGRATION_DATABASE_URL` is using `app_user` instead of `postgres`. |
| `duplicate key value violates unique constraint "users_pkey"` on POST | You're trying to create a profile that already exists (the trigger already made it). |
| Requests hang / API freezes | DB pool exhausted from leaked sessions. Restart uvicorn; check `get_db` cleanup. |
| `Settings` validation error: extra fields | Add `extra="ignore"` to `SettingsConfigDict` or declare the field. |
| `socket.gaierror: getaddrinfo failed` | Hostname in connection URL is wrong (placeholder, typo, or DNS issue). |

---

## Production

- **Prod Supabase project:** see team password manager for project URL and credentials.
- **Migrations:** run manually from a dev machine with `APP_ENV=production`. Always test against local first.
- **`app_user`:** created manually in prod with a strong password (not the same as local). Password lives in `.env.production` and the team password manager.
- **`postgres` user:** never use except for migrations. Has full DDL privileges.

**Before running anything against production:**
1. Have you tested it locally? (Yes is the only correct answer.)
2. Did you verify `APP_ENV=production` is the env var you set?
3. For migrations: did you read what `alembic upgrade head` is about to apply?
4. Take a backup if you're doing anything destructive (Database → Backups in dashboard).

---

## What's NOT Set Up Yet (Future Work)

These are deliberate omissions for the current stage:

- **Staging environment.** Currently only local + production. Add staging when "breaking prod" becomes costly.
- **CI/CD.** Migrations and deploys are manual. Add GitHub Actions when:
  - More than one person works on the repo, OR
  - We have real users in prod, OR
  - We catch ourselves running migrations from the wrong terminal.
- **Tests.** No test suite yet. Add `pytest` + `pytest-asyncio` with a transactional fixture before the codebase grows much further.
- **Observability.** No Sentry, no logging aggregation. Add Sentry before launch.
- **Rate limiting, CORS hardening, security headers.** Add when we have a frontend in prod.
- **Backups beyond Supabase's defaults.** Free tier gets 7 days of daily backups. Upgrade or add custom backups when data matters more.

When you start to feel pain in any of these areas, that's the signal to address it.

---

## Making Changes — Checklist

When adding a new feature that touches the database:

- [ ] Add/update SQLAlchemy model in `src/app/models/`
- [ ] Run `uv run alembic revision --autogenerate -m "..."`
- [ ] Review the generated migration file — fix it up if autogenerate missed anything
- [ ] If the table is user-owned, add RLS policies in the migration
- [ ] Run `uv run alembic upgrade head` locally and verify in Studio
- [ ] Add the route in `src/app/api/routes/`
- [ ] Make sure routes that need auth use `Depends(get_current_user)`
- [ ] Make sure routes scope queries by `auth["sub"]` for user-owned data
- [ ] Test via Swagger with a real JWT
- [ ] Commit migration + code together — never one without the other

---

## Where to Read More

- [SQLAlchemy 2.0 Async docs](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Alembic with async](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic)
- [Supabase Auth (JWTs, JWKS)](https://supabase.com/docs/guides/auth)
- [Supabase Local Development](https://supabase.com/docs/guides/local-development)
- [FastAPI dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)

---

## Questions?

- For setup help: ask the team Slack/chat
- For bugs in this doc: open a PR
- For "why did we do it this way?" — most decisions are explained inline above. If a decision isn't explained, that's a doc bug.
