"""LLM provider layer: F-04 rules, OpenRouter SDK client, and primary/fallback router."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import cast

import httpx
from openrouter import OpenRouter
from openrouter.components import (
    ChatMessagesTypedDict,
    ChatStreamChunk,
    ChatSystemMessageTypedDict,
    ChatUserMessageTypedDict,
    ReasoningConfigTypedDict,
)
from openrouter.errors import NoResponseError, OpenRouterError
from pydantic import ValidationError

from app.core.config import LLMReasoningEffort, Settings

logger = logging.getLogger(__name__)

_HTTP_REQUEST_TIMEOUT = 408
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
        reasoning_effort: LLMReasoningEffort = "none",
    ) -> None:
        """Bind the client to a shared :class:`OpenRouter` SDK instance and one model.

        ``reasoning_effort`` enables extended thinking on every call (OpenRouter ``reasoning``);
        ``"none"`` leaves thinking off. No client-side request timeout is set: calls are
        long-running streams and OpenRouter enforces its own server-side timeout.
        """
        self._open_router = open_router
        self._model = model
        self._rules = rules
        self._reasoning_effort = reasoning_effort

    @property
    def model(self) -> str:
        """Return the OpenRouter model identifier this client targets."""
        return self._model

    def _classify(self, code: int, detail: str) -> LLMTransientError | LLMFatalError:
        """Map an HTTP-style status ``code`` to a transient or fatal error.

        Shared by the pre-stream HTTP error path and the in-stream ``error``-chunk path so both
        classify identically: 429 / 408 / 5xx are recoverable (the router retries the fallback);
        anything else is fatal.
        """
        message = f"{self._model} returned {code}: {detail[:200]}"
        if code in {_HTTP_RATE_LIMITED, _HTTP_REQUEST_TIMEOUT} or code >= _HTTP_SERVER_ERROR:
            return LLMTransientError(message)
        return LLMFatalError(message)

    def _accumulate_chunk(
        self, chunk: ChatStreamChunk, parts: list[str], reasoning_parts: list[str]
    ) -> None:
        """Accumulate a stream chunk's answer text, or raise on an in-band error.

        OpenRouter reports errors that occur *after* the stream has started (HTTP 200 already sent)
        in-band, not as a raised OpenRouterError: a chunk carrying a top-level ``error`` object,
        and/or a choice with ``finish_reason == "error"`` and no content. We surface these instead
        of accumulating nothing and failing later with a misleading "returned no content"; that is
        what made non-Anthropic providers (which hit mid-stream errors far more often) look broken.

        Reasoning/thinking models (Kimi, DeepSeek, Qwen, …) stream their answer via the reasoning
        channel (``delta.reasoning``, OpenRouter's alias for ``reasoning_content``) with
        ``delta.content`` empty. We collect it into ``reasoning_parts`` so :meth:`ask` can fall
        back to it and the answer text isn't lost.
        """
        if chunk.error is not None:
            raise self._classify(chunk.error.code, chunk.error.message)
        for choice in chunk.choices:
            if choice.finish_reason == "error":
                raise LLMTransientError(f"{self._model} ended the stream with an error")
            if choice.delta.refusal:
                raise LLMFatalError(f"{self._model} refused the request: {choice.delta.refusal}")
            content_delta = choice.delta.content
            if content_delta:
                parts.append(str(content_delta))
            reasoning_delta = choice.delta.reasoning
            if reasoning_delta:
                reasoning_parts.append(str(reasoning_delta))

    async def ask(
        self,
        user_message: str,
        task_instructions: str | None = None,
    ) -> str:
        """Send a user message and return the assistant's text response.

        Raises:
            LLMTransientError: Timeouts, 429, 5xx, a transient in-stream error, an undecodable
                stream chunk, or a completion with neither content nor reasoning text.
            LLMFatalError: Any 4xx response other than 429, a refusal, or a malformed response.
        """
        system_prompt = "\n\n".join(self._rules)
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
        reasoning: ReasoningConfigTypedDict | None = (
            None if self._reasoning_effort == "none" else {"effort": self._reasoning_effort}
        )
        # Always stream and accumulate the content deltas: with extended thinking enabled a single
        # generation can exceed the provider's non-streaming window. Reasoning/thinking models
        # stream their answer via the reasoning channel with ``content`` empty, so we keep it as a
        # fallback. No ``timeout_ms`` is passed, so the SDK applies httpx ``timeout=None`` and
        # OpenRouter governs the timeout.
        parts: list[str] = []
        reasoning_parts: list[str] = []
        try:
            stream = cast(
                AsyncIterator[ChatStreamChunk],
                await self._open_router.chat.send_async(
                    model=self._model,
                    messages=messages,
                    reasoning=reasoning,
                    stream=True,
                ),
            )
            async for chunk in stream:
                self._accumulate_chunk(chunk, parts, reasoning_parts)
        except OpenRouterError as exc:
            raise self._classify(exc.status_code, exc.body) from exc
        except NoResponseError as exc:
            raise LLMTransientError(f"no response from {self._model}: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise LLMTransientError(f"timeout calling {self._model}") from exc
        except httpx.TransportError as exc:
            raise LLMTransientError(f"transport error calling {self._model}: {exc}") from exc
        except ValidationError as exc:
            # A chunk failed to decode against the SDK's schema — e.g. a mid-stream error chunk
            # whose ``error.code`` is a non-numeric string (the SDK types it as int), a
            # ``reasoning_details`` variant the SDK doesn't model, or a null ``delta``. The stream
            # decoder raises a bare pydantic ValidationError; treat it as transient so the router
            # falls back instead of raising an unhandled 500.
            raise LLMTransientError(f"{self._model} returned an undecodable stream chunk") from exc
        except (AttributeError, IndexError, TypeError) as exc:
            raise LLMFatalError(f"{self._model} returned a malformed stream") from exc

        # Prefer the answer channel; fall back to the reasoning channel for thinking models that
        # stream the answer there with ``content`` empty (Kimi/DeepSeek/Qwen).
        content = "".join(parts) or "".join(reasoning_parts)
        if not content:
            # Neither content nor reasoning after a clean finish (e.g. filtered output): let the
            # router try the fallback model rather than hard-failing.
            raise LLMTransientError(f"{self._model} returned no content")
        return content


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
    ) -> str:
        """Try primary; on transient failure, try fallback. Fatal errors bubble up."""
        try:
            return await self._primary.ask(user_message, task_instructions)
        except LLMTransientError as exc:
            logger.warning(
                "primary LLM %s failed transiently, falling back to %s: %s",
                self._primary.model,
                self._fallback.model,
                exc,
            )
            return await self._fallback.ask(user_message, task_instructions)


# ─────────────────────────────────────────────────────────────────────────────
# Section D — Factory
# ─────────────────────────────────────────────────────────────────────────────


def build_router(settings: Settings, open_router: OpenRouter) -> LLMRouter:
    """Build an :class:`LLMRouter` wired with the configured primary and fallback models."""
    primary = ClaudeClient(
        open_router=open_router,
        model=settings.PRIMARY_MODEL,
        rules=settings.SYSTEM_RULES,
        reasoning_effort=settings.LLM_REASONING_EFFORT,
    )
    fallback = ClaudeClient(
        open_router=open_router,
        model=settings.FALLBACK_MODEL,
        rules=settings.SYSTEM_RULES,
        reasoning_effort=settings.LLM_REASONING_EFFORT,
    )
    return LLMRouter(primary=primary, fallback=fallback)
