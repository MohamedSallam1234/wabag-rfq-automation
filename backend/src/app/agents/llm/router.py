"""LLM provider layer: F-04 rules, OpenRouter Claude client, and primary/fallback router."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_HTTP_CLIENT_ERROR = 400
_HTTP_RATE_LIMITED = 429
_HTTP_SERVER_ERROR = 500


# ─────────────────────────────────────────────────────────────────────────────
# Section A — Exceptions
# ─────────────────────────────────────────────────────────────────────────────


class LLMTransientError(Exception):
    """Recoverable error (timeout, 429, 5xx) — the router should try the fallback."""


class LLMFatalError(Exception):
    """Unrecoverable error (4xx other than 429) — the request itself is broken."""


# ─────────────────────────────────────────────────────────────────────────────
# Section B — ClaudeClient (single-model HTTP client)
# ─────────────────────────────────────────────────────────────────────────────


class ClaudeClient:
    """Async OpenRouter client bound to a single Claude model.

    The system prompt is owned by the client (not the caller) so F-04 rules
    cannot be bypassed by passing a custom system message.
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        api_key: str,
        model: str,
        rules: list[str],
        timeout_s: float,
    ) -> None:
        """Bind the client to a shared :class:`httpx.AsyncClient` and one model."""
        self._http = http_client
        self._api_key = api_key
        self._model = model
        self._rules = rules
        self._timeout_s = timeout_s

    @property
    def model(self) -> str:
        """Return the OpenRouter model identifier this client targets."""
        return self._model

    async def ask(
        self,
        user_message: str,
        task_instructions: str | None = None,
        rfq_id: str | None = None,
    ) -> str:
        """Send a user message and return the assistant's text response.

        Raises:
            LLMTransientError: Timeouts, 429, or any 5xx response.
            LLMFatalError: Any 4xx response other than 429.
        """
        system_prompt = "F-04 AI Operating Rules\n\n" + "\n\n".join(self._rules)
        if task_instructions:
            system_prompt = f"{system_prompt}\n\nTask: {task_instructions}"
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "metadata": {
                "ruleset": "F-04",
                "rfq_id": rfq_id,
            },
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = await self._http.post(
                OPENROUTER_URL,
                json=payload,
                headers=headers,
                timeout=self._timeout_s,
            )
        except httpx.TimeoutException as exc:
            raise LLMTransientError(f"timeout calling {self._model}") from exc
        except httpx.TransportError as exc:
            raise LLMTransientError(f"transport error calling {self._model}: {exc}") from exc

        status = response.status_code
        if status >= _HTTP_SERVER_ERROR or status == _HTTP_RATE_LIMITED:
            raise LLMTransientError(f"{self._model} returned {status}: {response.text[:200]}")
        if status >= _HTTP_CLIENT_ERROR:
            raise LLMFatalError(f"{self._model} returned {status}: {response.text[:200]}")

        data = response.json()
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMFatalError(f"{self._model} returned malformed response: {data}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# Section C — LLMRouter (primary → fallback)
# ─────────────────────────────────────────────────────────────────────────────


class LLMRouter:
    """Routes calls to a primary client; falls back to secondary on transient errors only."""

    def __init__(self, primary: ClaudeClient, fallback: ClaudeClient) -> None:
        """Wrap a primary and fallback :class:`ClaudeClient`."""
        self._primary = primary
        self._fallback = fallback

    async def ask(
        self,
        user_message: str,
        task_instructions: str | None = None,
        rfq_id: str | None = None,
    ) -> str:
        """Try primary; on transient failure, try fallback. Fatal errors bubble up."""
        try:
            return await self._primary.ask(user_message, task_instructions, rfq_id)
        except LLMTransientError as exc:
            logger.warning(
                "primary LLM %s failed transiently, falling back to %s: %s",
                self._primary.model,
                self._fallback.model,
                exc,
            )
            return await self._fallback.ask(user_message, task_instructions, rfq_id)


# ─────────────────────────────────────────────────────────────────────────────
# Section D — Factory
# ─────────────────────────────────────────────────────────────────────────────


def build_router(settings: Settings, http_client: httpx.AsyncClient) -> LLMRouter:
    """Build an :class:`LLMRouter` wired with the configured primary and fallback models."""
    api_key = settings.OPENROUTER_API_KEY.get_secret_value()
    primary = ClaudeClient(
        http_client=http_client,
        api_key=api_key,
        model=settings.PRIMARY_MODEL,
        rules=settings.SYSTEM_RULES,
        timeout_s=settings.LLM_TIMEOUT_S,
    )
    fallback = ClaudeClient(
        http_client=http_client,
        api_key=api_key,
        model=settings.FALLBACK_MODEL,
        rules=settings.SYSTEM_RULES,
        timeout_s=settings.LLM_TIMEOUT_S,
    )
    return LLMRouter(primary=primary, fallback=fallback)
