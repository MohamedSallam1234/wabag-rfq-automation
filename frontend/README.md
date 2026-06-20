# WABAG RFQ Automation — Frontend

React + Tailwind single-page app over the
[WABAG RFQ Automation](../README.md) backend API. It covers what the backend
exposes today: project management, document intake & classification, and RFQ
generation.

## Stack

- **Vite 5 + React 18 + TypeScript** (SPA)
- **React Router v6** (data routers)
- **TanStack Query v5** (server state)
- **Tailwind CSS v3.4** + **shadcn/ui** (Radix + Tailwind, copy-in components)
- **React Hook Form + Zod** (forms)
- **Sonner** (toasts), **lucide-react** (icons)
- **Inter** (self-hosted via `@fontsource-variable/inter` — no external CDN)
- **npm** as the package manager

## Pages

| Route | Purpose |
|-------|---------|
| `/projects` | Projects dashboard: KPI row + all-projects table + create project |
| `/projects/:projectId` | Project detail: upload documents, override classification, download/delete, generate RFQ |
| `*` | 404 catch-all |

The dashboard is **derived only from real endpoints** — see
[Design system & the derivable dashboard](#design-system--the-derivable-dashboard)
below for what's shown and what was deliberately omitted.

## Prerequisites

- **Node ≥ 20** (developed on Node 24)
- **The backend running** on `http://127.0.0.1:8000` (see `../backend/`):
  ```sh
  cd ../backend && make dev
  ```
- **CORS enabled on the backend.** The backend reads `CORS_ORIGINS` from
  `backend/.env`; the local dev value
  `http://localhost:3000,http://localhost:5173` is already in
  `backend/.env.example`. If the frontend can't reach the API (browser
  console shows a CORS error), confirm `CORS_ORIGINS` includes
  `http://localhost:5173` in `backend/.env` and that `CORSMiddleware` is wired
  in `backend/src/app/main.py`.

## Setup

```sh
cd frontend
npm install
cp .env.example .env.local   # optional; defaults to http://127.0.0.1:8000/api/v1
npm run dev
```

The dev server runs on **http://localhost:5173**.

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start the Vite dev server (HMR) |
| `npm run build` | Type-check and build for production into `dist/` |
| `npm run preview` | Serve the production build locally |
| `npm run lint` | Run ESLint |
| `npm run lint:fix` | Run ESLint and auto-fix |
| `npm run typecheck` | Run `tsc` with no emit |
| `npm run format` | Format `src/` with Prettier |
| `npm run format:check` | Check formatting without writing |

## Environment variables

| Var | Default | Description |
|-----|---------|-------------|
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000/api/v1` | Base URL of the backend API |

Copy `.env.example` to `.env.local` to override.

## Architecture

```
src/
├── main.tsx            Entry point (imports Inter)
├── App.tsx             Providers (QueryClient, Tooltip) + RouterProvider + Toaster
├── index.css           Tailwind directives + WABAG design tokens (DESIGN.md)
├── vite-env.d.ts       Vite client + env + fontsource module decl
├── lib/
│   ├── utils.ts        cn(), formatBytes(), formatDate()
│   ├── derive.ts       pure helpers: doc counts, RFQ status, totals
│   └── api/
│       ├── client.ts   fetch wrapper + ApiError
│       ├── types.ts    TS types mirroring backend Pydantic schemas
│       ├── projects.ts / documents.ts / rfqs.ts   resource modules
├── hooks/              TanStack Query wrappers (use-projects / -documents / -rfqs / -projects-documents)
├── components/
│   ├── ui/             shadcn primitives (rethemed to WABAG tokens)
│   ├── layout/         RootLayout, Header, Sidebar (navy)
│   ├── dashboard/      KpiCard, ProjectsTable
│   ├── projects/       CreateProjectDialog
│   ├── documents/      DocumentUpload, DocumentTable, ClassificationBadge, OverrideClassDialog
│   └── rfqs/           GenerateRfqDialog, RfqSummaryCard
└── routes/
    ├── NotFoundPage.tsx
    └── projects/       ProjectsPage (dashboard), ProjectDetailPage
```

**API client** — a thin `fetch` wrapper in `src/lib/api/client.ts`. Multipart
uploads pass `FormData` straight through (fetch sets the boundary). Errors are
thrown as `ApiError` with `status`, `detail`, and the parsed body. No axios.

**Server state** — TanStack Query. Mutations invalidate the right query keys
(e.g. uploading a document invalidates the project's document list; generating
an RFQ does too, because it creates a new `doc_type="RFQ Package"` row).

## RFQ generation is long-running

`POST /api/v1/projects/:id/rfqs` is **synchronous** and runs map-reduce LLM
calls over the project's documents. A single generation can take **5–30
minutes** (the backend's `LLM_TIMEOUT_S` ceiling is 1800s). The generation
dialog warns about this up front and shows a spinner while the request is
open — keep the dialog open until it finishes. There is no background-job
endpoint yet (a documented backend follow-up, see SRS §F-06).

## Known dev-only advisories

`npm audit` reports two high-severity advisories in Vite's transitive dev
dependencies (dev-server probing on Windows). They affect the local dev server
only — not the production build. The fix is a major Vite upgrade (v5 → v8),
deliberately deferred to avoid destabilizing a fresh scaffold.

## What's intentionally out of scope

- **No auth layer** — the backend exposes every endpoint open today. When
  auth is added, wire it into `src/lib/api/client.ts` (e.g. an `Authorization`
  header) and protect routes in `App.tsx`.
- **No Docker/compose** — run the backend and frontend as two terminals.
  There's no Dockerfile for the backend either; the DB is remote Supabase.
- **No frontend pre-commit hook** — CI (`.github/workflows/ci.yaml`'s
  `frontend` job) runs lint/typecheck/build on PRs. A local pre-commit hook
  mirroring that is a follow-up.
- **High-fidelity RFQ result rendering** — the summary card shows the
  aggregate `extracted / conflict / tbd / vtf` counts. The full per-field
  confidence/provenance data lives inside the generated `.xlsx`, not a JSON
  endpoint.

## Design system & the derivable dashboard

The UI follows [`DESIGN.md`](../DESIGN.md): a navy sidebar, light app shell,
Inter type with tabular numerals, 12px cards with hairline borders and very
soft shadows, and a single semantic color palette (info / success / warning /
extraction / danger / low) used consistently for badges, KPI icon tiles,
status pills, and stat tiles. Tokens live as HSL channel triplets in
`src/index.css` and are surfaced as Tailwind colors in `tailwind.config.ts`
(`bg-info`, `text-success`, `bg-success-soft`, `text-on-navy`, etc.).

**The dashboard is derived, not served.** The backend has no aggregation,
audit, activity, pipeline-health, or per-project status endpoints — so the
landing page is built entirely from the two real list endpoints:

| KPI | Source |
|-----|--------|
| Active Projects | `len(GET /projects)` |
| Documents Uploaded | Σ over `GET /projects/{id}/documents` per project |
| RFQ Packages Generated | count of documents with `doc_type === "RFQ Package"` |

The per-project **Documents** count and **RFQ Status** badge in the table are
likewise derived from `GET /projects/{id}/documents` (RFQ Ready if any RFQ
Package doc exists, else In Progress, else No documents). This is an **N+1**
fetch (`src/hooks/use-projects-documents.ts`) — acceptable for modest project
counts, and it reuses the same query keys as the detail page so the data is
shared, not double-fetched. Revisit if a summary endpoint is ever added.

### Deliberately omitted from DESIGN.md (no backing API)

These DESIGN.md components were **removed, not faked**, because the backend
exposes nothing to populate them:

- **Sidebar items 2–10** (Templates, Documents, Equipment, Validation, RFQ
  Output, Audit Trail, Reports, Settings) — no routes exist. Sidebar shows
  only Projects (minimal & honest).
- **Header search + `Ctrl+K`, notifications bell, help icon** — no search,
  notifications, or help endpoints.
- **KPIs "Open Conflicts", "TBD Fields", "Avg. Confidence"** — these values
  are only ever returned transiently inside an `RFQGenerationResponse.summary`
  and are never persisted or queryable. KPI trend lines ("↑ X from last
  week") need historical data that doesn't exist.
- **Recent Projects "Equipment" column** — no equipment endpoint (Equipment
  List is a document classification type, not structured data).
- **Pipeline Health, Attention Required, Recent Activity, Quick Actions**
  panels — no aggregation / audit / activity endpoints, and no DB tables to
  back them (`audit`, `rfq`, `equipment`, `review` models are empty stubs).
- **DESIGN.md §11 enhancements** (command palette, density toggle,
  sparklines, dark-mode toggle) — out of scope for this pass.

When any of these land as backend endpoints, add the route + hook and surface
the panel; the API layer in `src/lib/api/` is the place to extend.
