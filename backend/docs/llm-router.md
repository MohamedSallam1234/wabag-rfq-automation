# LLM Router — Claude Opus 4.7 + Sonnet 4.6 (PD-00)

The LLM provider layer for the RFQ automation backend. All Claude calls go
through this router; it injects the F-04 AI Operating Rules into every request
and falls back from Opus to Sonnet on transient failures.

---

## 1. What was built

| File                                   | Purpose                                                                                                                                                             |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/app/core/config.py`               | Adds `OPENROUTER_API_KEY`, `PRIMARY_MODEL`, `FALLBACK_MODEL`, `LLM_TIMEOUT_S`, and the env-overridable `SYSTEM_RULES` (the F-04 rule list) to the typed `Settings`. |
| `src/app/agents/llm/router.py`         | Single-file LLM module: `build_system_prompt`, `ClaudeClient`, `LLMRouter`, `build_router`, and the two exception types.                                            |
| `src/app/api/deps.py`                  | New `get_router()` FastAPI dependency that returns the process-wide router.                                                                                         |
| `src/app/main.py`                      | `lifespan` that creates **one** shared `OpenRouter` SDK client + `LLMRouter` and stashes them on `app.state`, plus a `GET /llm/ping` smoke endpoint.                |
| `tests/test_agents/test_llm_router.py` | Tests mock `chat.send_async` with `AsyncMock` — no real network.                                                                                                    |
| `tests/test_core/test_config.py`       | Adds tests for `SYSTEM_RULES` parsing and defaults (env var holds the F-04 rule list).                                                                              |
| `.env.example`                         | Documents the new LLM env vars.                                                                                                                                     |

### Architecture in one picture

```
                  ┌────────────────────────┐
   incoming  ───► │   GET /llm/ping?msg=…  │   (any endpoint that uses get_router)
   request        └────────────┬───────────┘
                               │  Depends(get_router)
                               ▼
                       ┌─────────────────┐
                       │   LLMRouter     │  ← built once at startup
                       └───┬─────────┬───┘
                  primary  │         │  fallback (only on transient errors)
                           ▼         ▼
                   ┌──────────────┐  ┌──────────────┐
                   │ ClaudeClient │  │ ClaudeClient │
                   │  Opus 4.7    │  │  Sonnet 4.6  │
                   └──────┬───────┘  └──────┬───────┘
                          │ shared OpenRouter SDK client
                          ▼
                   OpenRouter Chat Completions endpoint (URL owned by the SDK)
```

### Design decisions you should know about

1. **The system prompt is owned by the client, not the caller.** Callers cannot
   override it. F-04 rules are guaranteed to be present on every call.
2. **F-04 rules are injected via `messages[0]` (the system message)**, which
   drives model behavior. Per-request audit metadata (e.g. `ruleset`, `rfq_id`)
   is not currently forwarded to OpenRouter.
3. **Rules are configurable via env**: set `SYSTEM_RULES` in `.env` as a
   pipe-separated string (the rules are the F-04 AI Operating Rules, named
   generically in the config so future non-F-04 rules can reuse the slot).
   If not set, the defaults in `src/app/core/config.py:_default_system_rules()`
   are used.
4. **Fatal vs. transient error mapping**:
   - Timeouts, transport errors, 429, 5xx → `LLMTransientError` → router tries fallback.
   - 400 / 401 / 404 / other 4xx → `LLMFatalError` → re-raised immediately.
     A 400 from Opus would be a 400 from Sonnet too — don't waste tokens on caller bugs.
5. **One shared `OpenRouter` SDK client for the whole app**, created in
   `lifespan` (entered as an async context manager) and reused for every
   request. The SDK owns its own httpx connection pool; per-request clients
   would tank throughput.
6. **No retries inside the client.** The router IS the retry mechanism.
7. **No abstract base classes, no provider registry.** OpenRouter is the only
   provider. We will add abstraction when we need a second one, not before.

---

## 2. Setup

### 2.1 Add env vars to `backend/.env`

```dotenv
# ── LLM (OpenRouter) ─────────────────────────────────────
OPENROUTER_API_KEY=sk-or-v1-...           # REQUIRED — get from https://openrouter.ai/keys
PRIMARY_MODEL=anthropic/claude-opus-4.7   # optional, this is the default
FALLBACK_MODEL=anthropic/claude-sonnet-4.6 # optional, this is the default
LLM_TIMEOUT_S=60.0                        # optional

# Optional — pipe-separated. If unset, defaults from config.py are used.
# SYSTEM_RULES=Be concise.|Return JSON when asked.|Never invent values.
```

> Without `OPENROUTER_API_KEY`, the app **will fail to start** with a pydantic
> validation error. This is intentional — it's required configuration.

### 2.2 Why `|` (pipe) as the separator?

Rules contain commas (and likely periods, em-dashes, quotes…). Pipe is the
cleanest character that doesn't collide with rule content. The
`field_validator` in `config.py` strips whitespace and discards empty
fragments, so this works:

```dotenv
SYSTEM_RULES=Rule one, with a comma.|Rule two.|  | Rule three.
```

### 2.3 Install / sync deps

The implementation uses the official [`openrouter`](https://pypi.org/project/openrouter/)
SDK (beta, pinned to `>=0.9,<1.0`) plus `httpx` (kept as a peer dep for error
types). Both are declared in `pyproject.toml`.

```bash
uv sync --dev
```

---

## 3. How to test it

There are three layers of testing. Use them in order.

### 3.1 Unit tests (no network, no API key needed)

The test file mocks `OpenRouter().chat.send_async` with `AsyncMock`, so
nothing reaches the network. Run from `backend/`:

```bash
# Just the router tests
uv run pytest tests/test_agents/test_llm_router.py -v

# Full suite
uv run pytest
```

What's covered (router tests + config tests for SYSTEM_RULES):

- request carries the F-04 system prompt and task instructions in `messages[0]`
- `model` and `timeout_ms` kwargs are forwarded to the SDK
- 429 / 500 / 502 / 503 (raised as `OpenRouterError` with that status) →
  `LLMTransientError` (parametrized)
- 400 / 401 / 404 (raised as `OpenRouterError` with that status) →
  `LLMFatalError` (parametrized)
- `NoResponseError`, `httpx.TimeoutException`, `httpx.ConnectError` →
  `LLMTransientError`
- malformed response shape or `None` content → `LLMFatalError`
- router uses primary when primary works
- router falls back to secondary when primary returns a transient error
- router does **not** fall back on a fatal error (asserts only 1 call was made)
- both failing transiently → `LLMTransientError` propagates
- `SYSTEM_RULES` env var splits on `|` and ignores empty fragments
- `SYSTEM_RULES` defaults are used when env var is unset

Expected output:

```
================ 25 passed in ~1s ================
```

### 3.2 Manual smoke test with a real OpenRouter key

Get a real key at <https://openrouter.ai/keys>, put it in `.env`, then:

```bash
# From backend/
uv run uvicorn app.main:app --reload --port 8000
```

In your browser or any HTTP client, hit:

```
GET http://localhost:8000/llm/ping?msg=Say hello in 5 words.
```

Expected response (`200 OK`):

```json
{ "response": "Hello from your friendly assistant." }
```

That single endpoint exists only to prove the wiring works. Build your real
RFQ endpoints elsewhere and inject `LLMRouter` via `Depends(get_router)`.

### 3.3 Verifying fallback behavior

The unit tests in §3.1 exercise the transient-fallback path with
`httpx.MockTransport`. That is the canonical proof. Don't try to force
fallback against the real OpenRouter — there's no reliable way to inject a
503 from outside.

### 3.4 Logging

The router logs a warning on every fallback:

```
WARNING app.agents.llm.router: primary LLM anthropic/claude-opus-4.7 failed
transiently, falling back to anthropic/claude-sonnet-4.6: <error>
```

Set `LOG_LEVEL=WARNING` (or lower) in `.env` to see these. In production you
should alert on a sustained rate of these warnings — it means Opus is
struggling.

---

## 4. How to use the router from your code

From any FastAPI endpoint:

```python
from typing import Annotated
from fastapi import APIRouter, Depends

from app.agents.llm.router import LLMRouter
from app.api.deps import get_router

router = APIRouter()


@router.post("/my-endpoint")
async def handler(llm: Annotated[LLMRouter, Depends(get_router)]) -> dict[str, str]:
    content = await llm.ask(
        user_message="raw user text or extracted document text",
        task_instructions="Extract X and return JSON with fields a, b, c.",
    )
    return {"content": content}
```

From a service / non-endpoint context (e.g. a background worker), call
`build_router(settings, open_router)` once at startup and pass the router
around — do **not** call it per-request.

### What `ask()` returns

A plain `str` — the assistant's `messages[0].content`. If you need JSON,
include "return JSON" in your `task_instructions` (the default F-04 rules
already mandate "return ONLY valid JSON" when JSON is asked for) and
`json.loads()` the result yourself. Validate with `pydantic` before trusting
it.

### What `ask()` raises

| Exception           | When                                      | Should you retry?                    |
| ------------------- | ----------------------------------------- | ------------------------------------ |
| `LLMTransientError` | Both Opus and Sonnet failed transiently   | Maybe — surface as 503 to the caller |
| `LLMFatalError`     | Either model returned 4xx (excluding 429) | No — your prompt or auth is broken   |

The router has already attempted the fallback before raising. Don't re-wrap in
your own retry loop.

---

## 5. Editing the F-04 rules

### Quickest: change `.env` (no code change, no redeploy of code, just restart)

```dotenv
SYSTEM_RULES=Be concise.|Return JSON when asked.|Never invent values.
```

Restart the app. New rules are picked up at `Settings()` construction time.

### Permanent: change the defaults in `config.py`

The defaults live in `_default_system_rules()` at the top of
`src/app/core/config.py`. Edit that function if you want the change to apply
even when `SYSTEM_RULES` is unset.

The full canonical F-04 specification (10 rules: source-of-truth, precedence,
confidence-based fields, hard-stop conditions, etc.) lives in the top-level
`README.md` §F-04. The defaults currently in code are simplified placeholders
that the team will expand to match the canonical spec.

---

## 6. FAQ

**Q: Why the `openrouter` SDK and not `anthropic` / `openai`?**
A: We talk to OpenRouter, not Anthropic or OpenAI directly. The official
`openrouter` Python SDK is auto-generated from OpenRouter's OpenAPI spec, so
it ships typed request/response models, owns the base URL and auth, and
stays in sync with new OpenRouter features automatically. We still own
status-code → exception mapping (`OpenRouterError.status_code` → transient
vs. fatal) on top of it.

**Q: Why is there no streaming / function-calling / `response_format` support?**
A: Not needed for the extraction pipeline yet. Keep the surface small. Add
when there's a concrete user.

**Q: Why is `base.py` still in the package if we're not using ABCs?**
A: It's a leftover docstring stub from the initial scaffold. Harmless;
delete in a cleanup pass.

**Q: Where does timeout get enforced?**
A: Per-call, via the SDK's `timeout_ms` kwarg on `chat.send_async`. We
convert `LLM_TIMEOUT_S` (seconds, float) to milliseconds (int) at the call
site so each request gets the same configured budget.

**Q: How is the API key kept out of logs?**
A: `OPENROUTER_API_KEY` is typed as `pydantic.SecretStr`. `repr(settings)`
prints `OPENROUTER_API_KEY=SecretStr('**********')`. The actual value is only
read inside `build_router()` via `.get_secret_value()`.

**Q: Can a caller pass their own system prompt to bypass F-04?**
A: No. `ClaudeClient.ask()` takes `user_message` and `task_instructions`
only. The system message is constructed internally and always leads with the
F-04 rules.

**Q: Where's the `/api/v1/rfq/extract` endpoint that the earlier doc mentioned?**
A: Removed. It was demo scaffolding. The only LLM-touching endpoint shipped
today is `GET /llm/ping` in `main.py`, which is a smoke test only — delete it
or hide it behind a debug flag before shipping to prod. Build your real RFQ
endpoints in `src/app/api/v1/rfq.py` (currently a stub).

---

## 7. PR / review checklist

- [ ] `OPENROUTER_API_KEY` is set in your local `.env`
- [ ] `uv run pytest` is green (25/25)
- [ ] `uv run ruff check src tests` is clean
- [ ] `uv run mypy src` is clean
- [ ] Manual smoke test (§3.2) returns a sensible response
- [ ] No real API key committed (check `git diff` and pre-commit's
      `detect-secrets` output)
