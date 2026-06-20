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
- **npm** as the package manager

## Pages

| Route | Purpose |
|-------|---------|
| `/projects` | List and create projects |
| `/projects/:projectId` | Project detail: upload documents, override classification, download/delete, generate RFQ |
| `*` | 404 catch-all |

No dashboard, audit-trail, or equipment-list screens — those backend endpoints
don't exist yet. When they land, add the routes and hooks; the API layer in
`src/lib/api/` is the place to extend.

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
├── main.tsx            Entry point
├── App.tsx             Providers (QueryClient, Tooltip) + RouterProvider + Toaster
├── index.css           Tailwind directives + shadcn CSS variables
├── vite-env.d.ts       Vite client + env type declarations
├── lib/
│   ├── utils.ts        cn(), formatBytes(), formatDate()
│   └── api/
│       ├── client.ts   fetch wrapper + ApiError
│       ├── types.ts    TS types mirroring backend Pydantic schemas
│       ├── projects.ts / documents.ts / rfqs.ts   resource modules
├── hooks/              TanStack Query wrappers (use-projects / -documents / -rfqs)
├── components/
│   ├── ui/             shadcn primitives
│   ├── layout/         RootLayout, Header
│   ├── projects/       CreateProjectDialog, ProjectCard
│   ├── documents/      DocumentUpload, DocumentTable, ClassificationBadge, OverrideClassDialog
│   └── rfqs/           GenerateRfqDialog, RfqSummaryCard
└── routes/
    ├── NotFoundPage.tsx
    └── projects/       ProjectsPage, ProjectDetailPage
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
