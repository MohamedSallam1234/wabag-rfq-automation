"""LLM provider layer: F-04 rules, OpenRouter SDK client, and primary/fallback router."""

from __future__ import annotations

import logging

import httpx
from openrouter import OpenRouter
from openrouter.components import (
    ChatMessagesTypedDict,
    ChatSystemMessageTypedDict,
    ChatUserMessageTypedDict,
)
from openrouter.errors import NoResponseError, OpenRouterError

from app.core.config import Settings

logger = logging.getLogger(__name__)

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
# Section B — ClaudeClient (single-model SDK wrapper)
# ─────────────────────────────────────────────────────────────────────────────


class ClaudeClient:
    """Async OpenRouter SDK client bound to a single Claude model.

    The system prompt is owned by the client (not the caller) so F-04 rules
    cannot be bypassed by passing a custom system message.
    """

    def __init__(
        self,
        open_router: OpenRouter,
        model: str,
        rules: list[str],
        timeout_s: float,
    ) -> None:
        """Bind the client to a shared :class:`OpenRouter` SDK instance and one model."""
        self._open_router = open_router
        self._model = model
        self._rules = rules
        self._timeout_ms = int(timeout_s * 1000)

    @property
    def model(self) -> str:
        """Return the OpenRouter model identifier this client targets."""
        return self._model

    async def ask(
        self,
        user_message: str,
        task_instructions: str | None = None,
        rfq_id: str | None = None,  # noqa: ARG002
    ) -> str:
        """Send a user message and return the assistant's text response.

        ``rfq_id`` is part of the public router contract (documented for audit
        wiring) and is intentionally accepted but not currently forwarded to
        the SDK.

        Raises:
            LLMTransientError: Timeouts, 429, or any 5xx response.
            LLMFatalError: Any 4xx response other than 429, or a malformed response.
        """
        system_prompt = "F-04 AI Operating Rules\n\n" + "\n\n".join(self._rules)
        if task_instructions:
            system_prompt = f"{system_prompt}\n\nTask: {task_instructions}"

        system_msg: ChatSystemMessageTypedDict = {
            "role": "system",
            "content": system_prompt,
        }
        user_msg: ChatUserMessageTypedDict = {
            "role": "user",
            "content": user_message,
        }
        messages: list[ChatMessagesTypedDict] = [system_msg, user_msg]
        try:
            result = await self._open_router.chat.send_async(
                model=self._model,
                messages=messages,
                timeout_ms=self._timeout_ms,
            )
        except OpenRouterError as exc:
            status = exc.status_code
            if status == _HTTP_RATE_LIMITED or status >= _HTTP_SERVER_ERROR:
                raise LLMTransientError(
                    f"{self._model} returned {status}: {exc.body[:200]}"
                ) from exc
            if status >= _HTTP_CLIENT_ERROR:
                raise LLMFatalError(f"{self._model} returned {status}: {exc.body[:200]}") from exc
            raise LLMFatalError(f"{self._model}: {exc}") from exc
        except NoResponseError as exc:
            raise LLMTransientError(f"no response from {self._model}: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise LLMTransientError(f"timeout calling {self._model}") from exc
        except httpx.TransportError as exc:
            raise LLMTransientError(f"transport error calling {self._model}: {exc}") from exc

        try:
            content = result.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise LLMFatalError(f"{self._model} returned malformed response") from exc
        if content is None:
            raise LLMFatalError(f"{self._model} returned no content")
        return str(content)


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


def build_router(settings: Settings, open_router: OpenRouter) -> LLMRouter:
    """Build an :class:`LLMRouter` wired with the configured primary and fallback models."""
    primary = ClaudeClient(
        open_router=open_router,
        model=settings.PRIMARY_MODEL,
        rules=settings.SYSTEM_RULES,
        timeout_s=settings.LLM_TIMEOUT_S,
    )
    fallback = ClaudeClient(
        open_router=open_router,
        model=settings.FALLBACK_MODEL,
        rules=settings.SYSTEM_RULES,
        timeout_s=settings.LLM_TIMEOUT_S,
    )
    return LLMRouter(primary=primary, fallback=fallback)
