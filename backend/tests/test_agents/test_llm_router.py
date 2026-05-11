"""Tests for the F-04 LLM router (primary Opus, fallback Sonnet via OpenRouter)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.agents.llm.router import (
    OPENROUTER_URL,
    ClaudeClient,
    LLMFatalError,
    LLMRouter,
    LLMTransientError,
)

DEFAULT_TEST_RULES = ["Test rule 1: be brief.", "Test rule 2: never invent."]


def _ok_response(text: str = "hello") -> httpx.Response:
    """Return a 200 OpenRouter-shaped chat completion response."""
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": text}}]},
    )


def _make_client(
    handler: httpx.MockTransport,
    *,
    model: str = "anthropic/claude-opus-4.7",
    api_key: str = "test-key",
    rules: list[str] | None = None,
    timeout_s: float = 5.0,
) -> tuple[ClaudeClient, httpx.AsyncClient]:
    """Build a ClaudeClient backed by a MockTransport-driven AsyncClient."""
    http = httpx.AsyncClient(transport=handler)
    client = ClaudeClient(
        http_client=http,
        api_key=api_key,
        model=model,
        rules=rules if rules is not None else DEFAULT_TEST_RULES,
        timeout_s=timeout_s,
    )
    return client, http


# ─────────────────────────── Section A: payload + auth ───────────────────────


async def test_request_body_carries_system_prompt_and_metadata() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return _ok_response()

    client, http = _make_client(
        httpx.MockTransport(handler),
        rules=["My one rule."],
    )
    try:
        await client.ask(
            user_message="hi",
            task_instructions="extract fields",
            rfq_id="RFQ-42",
        )
    finally:
        await http.aclose()

    body = captured["body"]
    assert isinstance(body, dict)
    messages = body["messages"]
    assert messages[0]["role"] == "system"
    assert "F-04 AI Operating Rules" in messages[0]["content"]
    assert "My one rule." in messages[0]["content"]
    assert "extract fields" in messages[0]["content"]
    assert messages[1] == {"role": "user", "content": "hi"}

    metadata = body["metadata"]
    assert metadata == {"ruleset": "F-04", "rfq_id": "RFQ-42"}

    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["authorization"] == "Bearer test-key"


async def test_request_targets_openrouter_url() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return _ok_response()

    client, http = _make_client(httpx.MockTransport(handler))
    try:
        await client.ask("hi")
    finally:
        await http.aclose()

    assert seen["url"] == OPENROUTER_URL


# ─────────────────────────── Section C: error mapping ────────────────────────


@pytest.mark.parametrize("status", [429, 500, 502, 503])
async def test_transient_status_codes_raise_transient_error(status: int) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="boom")

    client, http = _make_client(httpx.MockTransport(handler))
    try:
        with pytest.raises(LLMTransientError):
            await client.ask("hi")
    finally:
        await http.aclose()


@pytest.mark.parametrize("status", [400, 401, 404])
async def test_fatal_status_codes_raise_fatal_error(status: int) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="bad")

    client, http = _make_client(httpx.MockTransport(handler))
    try:
        with pytest.raises(LLMFatalError):
            await client.ask("hi")
    finally:
        await http.aclose()


async def test_timeout_raises_transient_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    client, http = _make_client(httpx.MockTransport(handler))
    try:
        with pytest.raises(LLMTransientError):
            await client.ask("hi")
    finally:
        await http.aclose()


# ─────────────────────────── Section D: router behavior ──────────────────────


def _router_with_handlers(
    primary_handler: httpx.MockTransport,
    fallback_handler: httpx.MockTransport,
) -> tuple[LLMRouter, httpx.AsyncClient, httpx.AsyncClient]:
    primary, primary_http = _make_client(primary_handler, model="primary")
    fallback, fallback_http = _make_client(fallback_handler, model="fallback")
    return LLMRouter(primary=primary, fallback=fallback), primary_http, fallback_http


async def test_router_returns_primary_when_primary_succeeds() -> None:
    primary_calls = 0
    fallback_calls = 0

    def primary_handler(_: httpx.Request) -> httpx.Response:
        nonlocal primary_calls
        primary_calls += 1
        return _ok_response("from-primary")

    def fallback_handler(_: httpx.Request) -> httpx.Response:
        nonlocal fallback_calls
        fallback_calls += 1
        return _ok_response("from-fallback")

    router, p_http, f_http = _router_with_handlers(
        httpx.MockTransport(primary_handler),
        httpx.MockTransport(fallback_handler),
    )
    try:
        result = await router.ask("hi")
    finally:
        await p_http.aclose()
        await f_http.aclose()

    assert result == "from-primary"
    assert primary_calls == 1
    assert fallback_calls == 0


async def test_router_falls_back_on_transient_error() -> None:
    primary_calls = 0
    fallback_calls = 0

    def primary_handler(_: httpx.Request) -> httpx.Response:
        nonlocal primary_calls
        primary_calls += 1
        return httpx.Response(503, text="overloaded")

    def fallback_handler(_: httpx.Request) -> httpx.Response:
        nonlocal fallback_calls
        fallback_calls += 1
        return _ok_response("from-fallback")

    router, p_http, f_http = _router_with_handlers(
        httpx.MockTransport(primary_handler),
        httpx.MockTransport(fallback_handler),
    )
    try:
        result = await router.ask("hi")
    finally:
        await p_http.aclose()
        await f_http.aclose()

    assert result == "from-fallback"
    assert primary_calls == 1
    assert fallback_calls == 1


async def test_router_does_not_fall_back_on_fatal_error() -> None:
    primary_calls = 0
    fallback_calls = 0

    def primary_handler(_: httpx.Request) -> httpx.Response:
        nonlocal primary_calls
        primary_calls += 1
        return httpx.Response(400, text="bad request")

    def fallback_handler(_: httpx.Request) -> httpx.Response:
        nonlocal fallback_calls
        fallback_calls += 1
        return _ok_response("should-not-be-used")

    router, p_http, f_http = _router_with_handlers(
        httpx.MockTransport(primary_handler),
        httpx.MockTransport(fallback_handler),
    )
    try:
        with pytest.raises(LLMFatalError):
            await router.ask("hi")
    finally:
        await p_http.aclose()
        await f_http.aclose()

    assert primary_calls == 1
    assert fallback_calls == 0


async def test_router_raises_when_both_primary_and_fallback_fail_transiently() -> None:
    def primary_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    def fallback_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(502)

    router, p_http, f_http = _router_with_handlers(
        httpx.MockTransport(primary_handler),
        httpx.MockTransport(fallback_handler),
    )
    try:
        with pytest.raises(LLMTransientError):
            await router.ask("hi")
    finally:
        await p_http.aclose()
        await f_http.aclose()
