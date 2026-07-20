"""Tests for the F-04 LLM router (primary Opus, fallback Sonnet via OpenRouter SDK)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from openrouter import errors as openrouter_errors
from pydantic import BaseModel, ValidationError

from app.agents.llm.router import (
    ClaudeClient,
    LLMFatalError,
    LLMRouter,
    LLMTransientError,
)

DEFAULT_TEST_RULES = ["Test rule 1: be brief.", "Test rule 2: never invent."]


async def _stream_chunks(*deltas: str | None):
    """Fake event stream yielding one chunk per content delta (``choices[0].delta.content``)."""
    for delta in deltas:
        yield SimpleNamespace(
            error=None,
            choices=[
                SimpleNamespace(
                    finish_reason=None,
                    delta=SimpleNamespace(content=delta, reasoning=None, refusal=None),
                )
            ],
        )


def _ok_result(text: str | None = "hello"):
    """Return a fake stream yielding a single content delta of ``text``."""
    return _stream_chunks(text)


async def _error_chunk_stream(code: int, message: str = "boom", *, with_error_object: bool = True):
    """Fake stream that surfaces an OpenRouter in-band error (post-200, mid-stream).

    OpenRouter reports errors that occur after the stream has started as a chunk carrying a
    top-level ``error`` object and a choice whose ``finish_reason`` is ``"error"``.
    """
    error = SimpleNamespace(code=code, message=message) if with_error_object else None
    yield SimpleNamespace(
        error=error,
        choices=[
            SimpleNamespace(
                finish_reason="error",
                delta=SimpleNamespace(content=None, reasoning=None, refusal=None),
            )
        ],
    )


async def _refusal_stream(text: str = "I can't help with that."):
    """Fake stream whose only choice carries a refusal delta (and no content)."""
    yield SimpleNamespace(
        error=None,
        choices=[
            SimpleNamespace(
                finish_reason=None,
                delta=SimpleNamespace(content=None, reasoning=None, refusal=text),
            )
        ],
    )


async def _reasoning_stream(text: str = "the answer"):
    """Fake stream that delivers the answer via the reasoning channel with empty content
    (Kimi/DeepSeek/Qwen thinking-model behaviour)."""
    yield SimpleNamespace(
        error=None,
        choices=[
            SimpleNamespace(
                finish_reason=None,
                delta=SimpleNamespace(content=None, reasoning=text, refusal=None),
            )
        ],
    )


def _validation_error() -> ValidationError:
    """Return a real pydantic ``ValidationError`` — the SDK's stream decoder raises one when a chunk
    fails schema validation (e.g. a non-numeric string ``error.code``)."""

    class _Model(BaseModel):
        value: int

    try:
        _Model(value="not-an-int")
    except ValidationError as exc:
        return exc
    raise AssertionError("expected a ValidationError")  # pragma: no cover


def _raw_response(status: int, body: str = "boom") -> httpx.Response:
    """Build a minimal :class:`httpx.Response` for OpenRouterError dataclasses."""
    return httpx.Response(status, text=body)


def _http_error(status: int, body: str = "boom") -> openrouter_errors.OpenRouterError:
    """Build an OpenRouterError with the given status (SDK uses the response's status)."""
    return openrouter_errors.OpenRouterError(
        message=f"HTTP {status}",
        raw_response=_raw_response(status, body),
        body=body,
    )


def _make_client(
    *,
    response_text: str = "hello",
    side_effect: BaseException | None = None,
    model: str = "anthropic/claude-opus-4.7",
    rules: list[str] | None = None,
) -> tuple[ClaudeClient, AsyncMock]:
    """Build a ClaudeClient whose underlying SDK call is mocked with AsyncMock."""
    fake_send = AsyncMock()
    if side_effect is not None:
        fake_send.side_effect = side_effect
    else:
        fake_send.return_value = _ok_result(response_text)
    fake_open_router = MagicMock()
    fake_open_router.chat.send_async = fake_send
    client = ClaudeClient(
        open_router=fake_open_router,
        model=model,
        rules=rules if rules is not None else DEFAULT_TEST_RULES,
    )
    return client, fake_send


# ─────────────────────────── Section A: payload + auth ───────────────────────


async def test_request_carries_system_prompt() -> None:
    client, fake_send = _make_client(rules=["My one rule."])

    await client.ask(
        user_message="hi",
        task_instructions="extract fields",
    )

    kwargs = fake_send.call_args.kwargs
    assert kwargs["model"] == "anthropic/claude-opus-4.7"
    messages = kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert "My one rule." in messages[0]["content"]
    assert "extract fields" in messages[0]["content"]
    assert messages[1] == {"role": "user", "content": "hi"}
    assert "timeout_ms" not in kwargs  # no client-side timeout; OpenRouter governs it
    assert kwargs["stream"] is True


async def test_reasoning_disabled_by_default() -> None:
    client, fake_send = _make_client()

    await client.ask("hi")

    assert fake_send.call_args.kwargs["reasoning"] is None


async def test_reasoning_effort_is_passed_when_enabled() -> None:
    fake_send = AsyncMock(return_value=_ok_result("hello"))
    fake_open_router = MagicMock()
    fake_open_router.chat.send_async = fake_send
    client = ClaudeClient(
        open_router=fake_open_router,
        model="anthropic/claude-opus-4.8",
        rules=DEFAULT_TEST_RULES,
        reasoning_effort="high",
    )

    await client.ask("hi")

    assert fake_send.call_args.kwargs["reasoning"] == {"effort": "high"}


async def test_returns_assistant_text() -> None:
    client, _ = _make_client(response_text="hello from the model")

    result = await client.ask("hi")

    assert result == "hello from the model"


async def test_accumulates_streamed_content_deltas() -> None:
    client, fake_send = _make_client()
    fake_send.return_value = _stream_chunks("Hello, ", "world", "!")

    result = await client.ask("hi")

    assert result == "Hello, world!"


# ─────────────────────────── Section B: error mapping ────────────────────────


@pytest.mark.parametrize("status", [429, 500, 502, 503])
async def test_transient_status_codes_raise_transient_error(status: int) -> None:
    client, _ = _make_client(side_effect=_http_error(status))

    with pytest.raises(LLMTransientError):
        await client.ask("hi")


@pytest.mark.parametrize("status", [400, 401, 404])
async def test_fatal_status_codes_raise_fatal_error(status: int) -> None:
    client, _ = _make_client(side_effect=_http_error(status))

    with pytest.raises(LLMFatalError):
        await client.ask("hi")


async def test_no_response_error_is_transient() -> None:
    client, _ = _make_client(side_effect=openrouter_errors.NoResponseError("network gone"))

    with pytest.raises(LLMTransientError):
        await client.ask("hi")


async def test_timeout_raises_transient_error() -> None:
    client, _ = _make_client(side_effect=httpx.TimeoutException("slow"))

    with pytest.raises(LLMTransientError):
        await client.ask("hi")


async def test_transport_error_raises_transient_error() -> None:
    client, _ = _make_client(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(LLMTransientError):
        await client.ask("hi")


async def test_malformed_response_raises_fatal_error() -> None:
    client, fake_send = _make_client()
    fake_send.return_value = SimpleNamespace(choices=[])

    with pytest.raises(LLMFatalError):
        await client.ask("hi")


async def test_none_content_raises_transient_error() -> None:
    # Neither content nor reasoning after a clean finish → transient, so the router falls back
    # instead of hard-failing (e.g. filtered output).
    client, fake_send = _make_client()
    fake_send.return_value = _ok_result(text=None)  # type: ignore[arg-type]

    with pytest.raises(LLMTransientError):
        await client.ask("hi")


async def test_reasoning_only_content_returns_reasoning() -> None:
    # Thinking models stream the answer via the reasoning channel with empty content; ask() must
    # fall back to it instead of failing with "returned no content".
    client, fake_send = _make_client()
    fake_send.return_value = _reasoning_stream("the answer")

    result = await client.ask("hi")

    assert result == "the answer"


async def test_content_wins_over_reasoning() -> None:
    # When both channels are present, the answer channel is used and reasoning is ignored.
    async def _both():
        yield SimpleNamespace(
            error=None,
            choices=[
                SimpleNamespace(
                    finish_reason=None,
                    delta=SimpleNamespace(content="answer", reasoning="thinking", refusal=None),
                )
            ],
        )

    client, fake_send = _make_client()
    fake_send.return_value = _both()

    result = await client.ask("hi")

    assert result == "answer"


async def test_undecodable_chunk_is_transient() -> None:
    # The SDK's stream decoder raises a bare pydantic ValidationError when a chunk fails schema
    # decode (e.g. a non-numeric string error.code, mid-iteration). It must map to transient so the
    # router can fall back rather than escaping as an unhandled 500.
    client, _ = _make_client(side_effect=_validation_error())

    with pytest.raises(LLMTransientError):
        await client.ask("hi")


@pytest.mark.parametrize("code", [500, 502, 503])
async def test_in_stream_server_error_is_transient(code: int) -> None:
    # A provider that errors mid-stream (common with non-Anthropic models) is delivered as an
    # in-band error chunk, not a raised OpenRouterError — it must still be classified transient.
    client, fake_send = _make_client()
    fake_send.return_value = _error_chunk_stream(code)

    with pytest.raises(LLMTransientError):
        await client.ask("hi")


@pytest.mark.parametrize("code", [400, 401, 404])
async def test_in_stream_client_error_is_fatal(code: int) -> None:
    client, fake_send = _make_client()
    fake_send.return_value = _error_chunk_stream(code)

    with pytest.raises(LLMFatalError):
        await client.ask("hi")


async def test_finish_reason_error_without_error_object_is_transient() -> None:
    client, fake_send = _make_client()
    fake_send.return_value = _error_chunk_stream(0, with_error_object=False)

    with pytest.raises(LLMTransientError):
        await client.ask("hi")


async def test_refusal_delta_raises_fatal() -> None:
    client, fake_send = _make_client()
    fake_send.return_value = _refusal_stream("I won't do that.")

    with pytest.raises(LLMFatalError):
        await client.ask("hi")


# ─────────────────────────── Section C: router behavior ──────────────────────


def _router(
    primary_client: ClaudeClient,
    fallback_client: ClaudeClient,
) -> LLMRouter:
    return LLMRouter(primary=primary_client, fallback=fallback_client)


async def test_router_returns_primary_when_primary_succeeds() -> None:
    primary, primary_send = _make_client(response_text="from-primary", model="primary")
    fallback, fallback_send = _make_client(response_text="from-fallback", model="fallback")

    result = await _router(primary, fallback).ask("hi")

    assert result == "from-primary"
    assert primary_send.await_count == 1
    assert fallback_send.await_count == 0


async def test_router_falls_back_on_transient_error() -> None:
    primary, primary_send = _make_client(side_effect=_http_error(503), model="primary")
    fallback, fallback_send = _make_client(response_text="from-fallback", model="fallback")

    result = await _router(primary, fallback).ask("hi")

    assert result == "from-fallback"
    assert primary_send.await_count == 1
    assert fallback_send.await_count == 1


async def test_router_falls_back_on_in_stream_transient_error() -> None:
    # Regression: a primary that errors mid-stream (the non-Anthropic failure mode) used to be
    # misreported as a fatal "no content" and never fell back. It must now fall back.
    primary, primary_send = _make_client(model="primary")
    primary_send.return_value = _error_chunk_stream(503)
    fallback, fallback_send = _make_client(response_text="from-fallback", model="fallback")

    result = await _router(primary, fallback).ask("hi")

    assert result == "from-fallback"
    assert primary_send.await_count == 1
    assert fallback_send.await_count == 1


async def test_router_falls_back_on_undecodable_chunk() -> None:
    # An undecodable stream chunk (bare pydantic ValidationError) is transient → the router falls
    # back to the secondary model instead of escaping as an unhandled error.
    primary, primary_send = _make_client(side_effect=_validation_error(), model="primary")
    fallback, fallback_send = _make_client(response_text="from-fallback", model="fallback")

    result = await _router(primary, fallback).ask("hi")

    assert result == "from-fallback"
    assert primary_send.await_count == 1
    assert fallback_send.await_count == 1


async def test_router_does_not_fall_back_on_fatal_error() -> None:
    primary, primary_send = _make_client(side_effect=_http_error(400), model="primary")
    fallback, fallback_send = _make_client(response_text="should-not-be-used", model="fallback")

    with pytest.raises(LLMFatalError):
        await _router(primary, fallback).ask("hi")

    assert primary_send.await_count == 1
    assert fallback_send.await_count == 0


async def test_router_raises_when_both_primary_and_fallback_fail_transiently() -> None:
    primary, _ = _make_client(side_effect=_http_error(503), model="primary")
    fallback, _ = _make_client(side_effect=_http_error(502), model="fallback")

    with pytest.raises(LLMTransientError):
        await _router(primary, fallback).ask("hi")
