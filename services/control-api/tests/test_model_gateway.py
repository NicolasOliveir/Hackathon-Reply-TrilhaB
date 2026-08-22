"""Testes do gateway de modelo. Não tocam banco, rede nem provedor real."""

from __future__ import annotations

import json

import pytest

from app.model_gateway.base import (
    ModelRequest,
    ModelResponse,
    ModelUsage,
    ProviderNotConfigured,
    ProviderRefused,
)
from app.model_gateway.echo_provider import EchoProvider
from app.model_gateway.routing import DEFAULT_ROUTES, ModelRouter


# ------------------------------------------------------------------ roteamento


def test_router_falls_back_to_the_default_provider():
    route = ModelRouter(default_provider="anthropic").route("po")
    assert route.provider == "anthropic"


def test_router_applies_per_role_effort():
    router = ModelRouter(default_provider="echo")
    assert router.route("qa").effort == "xhigh"
    assert router.route("fake").effort == "low"


def test_qa_gets_more_effort_than_the_fake_worker():
    """Erro do QA libera código quebrado; erro do fake worker não custa nada."""
    order = ["low", "medium", "high", "xhigh", "max"]
    router = ModelRouter()
    assert order.index(router.route("qa").effort) > order.index(
        router.route("fake").effort
    )


def test_override_wins_over_the_default_route():
    router = ModelRouter(
        default_provider="echo",
        overrides={"dev": {"provider": "codex", "model": "gpt-5.6-sol"}},
    )
    route = router.route("dev")
    assert route.provider == "codex"
    assert route.model == "gpt-5.6-sol"
    assert "override" in route.reason


def test_route_reason_names_provider_model_and_effort():
    """A rota escolhida é auditável: ela vai para a tabela e para o painel."""
    reason = ModelRouter(default_provider="anthropic").route("qa").reason
    assert "anthropic" in reason
    assert "xhigh" in reason


def test_unknown_role_still_routes():
    assert ModelRouter(default_provider="echo").route("inexistente").provider == "echo"


def test_every_declared_role_has_a_route():
    router = ModelRouter()
    for role in DEFAULT_ROUTES:
        assert router.route(role).provider


# -------------------------------------------------------------------- provedor


async def test_echo_provider_reports_usage():
    response = await EchoProvider().invoke(ModelRequest(prompt="ola mundo"))
    assert response.provider == "echo"
    assert response.usage.input_tokens > 0
    assert response.usage.output_tokens > 0
    assert response.usage.total_tokens == (
        response.usage.input_tokens + response.usage.output_tokens
    )


async def test_echo_provider_returns_json_when_a_schema_is_requested():
    response = await EchoProvider().invoke(
        ModelRequest(prompt="qualquer", output_schema={"title": "Backlog"})
    )
    assert response.parsed is not None
    assert json.loads(response.text) == response.parsed


async def test_echo_provider_returns_no_parsed_without_schema():
    response = await EchoProvider().invoke(ModelRequest(prompt="qualquer"))
    assert response.parsed is None


# ------------------------------------------------------- provedores concretos


def test_codex_provider_reports_missing_binary_instead_of_failing_late():
    from app.model_gateway.codex_provider import CodexProvider

    with pytest.raises(ProviderNotConfigured) as error:
        CodexProvider(binary="binario-que-nao-existe")._resolve_binary()

    assert "PATH" in str(error.value)


def test_codex_provider_uses_read_only_sandbox():
    """O gateway pede texto; modo de escrita daria ao CLI mais poder que o necessário."""
    from app.model_gateway import codex_provider

    assert codex_provider.SANDBOX == "read-only"


def test_anthropic_provider_defaults_to_opus_5():
    from app.model_gateway.anthropic_provider import DEFAULT_MODEL

    assert DEFAULT_MODEL == "claude-opus-5"


async def test_anthropic_provider_uses_adaptive_thinking_and_effort():
    """Verifica o payload enviado ao SDK sem fazer chamada real."""
    from app.model_gateway.anthropic_provider import AnthropicProvider

    captured: dict = {}

    class _Messages:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return _Message()

    class _Message:
        content = [type("B", (), {"type": "text", "text": "ok"})()]
        usage = type(
            "U",
            (),
            {
                "input_tokens": 11,
                "output_tokens": 7,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        )()
        stop_reason = "end_turn"
        model = "claude-opus-5"

    class _Client:
        messages = _Messages()

    response = await AnthropicProvider(client=_Client()).invoke(
        ModelRequest(prompt="oi", effort="xhigh")
    )

    assert captured["model"] == "claude-opus-5"
    assert captured["thinking"] == {"type": "adaptive"}
    assert captured["output_config"] == {"effort": "xhigh"}
    assert response.usage.input_tokens == 11
    assert response.usage.output_tokens == 7


async def test_anthropic_provider_raises_on_refusal():
    from app.model_gateway.anthropic_provider import AnthropicProvider

    class _Message:
        content = []
        usage = None
        stop_reason = "refusal"
        stop_details = type("D", (), {"category": "cyber"})()
        model = "claude-opus-5"

    class _Client:
        messages = type(
            "M", (), {"create": staticmethod(lambda **kw: _awaited(_Message()))}
        )()

    with pytest.raises(ProviderRefused) as error:
        await AnthropicProvider(client=_Client()).invoke(ModelRequest(prompt="oi"))

    assert error.value.category == "cyber"


async def _awaited(value):
    return value


async def test_missing_credential_says_what_to_configure():
    """Regressão: o SDK levanta `TypeError` cru quando nada resolve.

    Sem tradução, o operador recebia só "TypeError" — e esse é exatamente o
    primeiro erro de quem ainda não configurou a chave.
    """
    from app.model_gateway.anthropic_provider import AnthropicProvider

    class _Messages:
        async def create(self, **kwargs):
            raise TypeError(
                "Could not resolve authentication method. Expected one of "
                "api_key, auth_token, or credentials to be set."
            )

    class _Client:
        messages = _Messages()

    with pytest.raises(ProviderNotConfigured) as error:
        await AnthropicProvider(client=_Client()).invoke(ModelRequest(prompt="oi"))

    message = str(error.value)
    assert "ANTHROPIC_API_KEY" in message
    assert "ant auth login" in message


# ------------------------------------------------------------------ agregação


def test_usage_totals_match_the_event_envelope_meta_fields():
    """`meta` do EventEnvelope declara model, tokens_in, tokens_out e latency_ms."""
    from app.model_gateway.gateway import UsageTotals

    meta = UsageTotals(
        model="claude-opus-5", tokens_in=10, tokens_out=20, latency_ms=1234
    ).as_event_meta()

    assert set(meta) == {"model", "tokens_in", "tokens_out", "latency_ms"}
    assert meta["tokens_in"] == 10


def test_role_scopes_keep_model_invoke_away_from_the_fake_worker():
    from app.config import ROLE_SCOPES

    assert "model:invoke" not in ROLE_SCOPES["fake"]
    assert "model:invoke" in ROLE_SCOPES["po"]
    assert "model:invoke" in ROLE_SCOPES["qa"]


def test_codex_schema_removes_unsupported_unique_items_without_mutating_source():
    from app.model_gateway.codex_provider import _codex_output_schema

    source = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "uniqueItems": True,
                "items": {"$ref": "https://reply.local/common.json#/$defs/text"},
            }
        },
    }

    normalized = _codex_output_schema(source)

    assert "uniqueItems" not in normalized["properties"]["items"]
    assert normalized["properties"]["items"]["items"] == {}
    assert source["properties"]["items"]["uniqueItems"] is True


def test_scopes_come_from_a_single_source():
    """Emissor de token e gateway leem do mesmo lugar."""
    from app.config import ROLE_SCOPES
    from app.orchestration import tokens

    assert tokens.scopes_for("po") == list(ROLE_SCOPES["po"])
    assert tokens.FAKE_WORKER_SCOPES == list(ROLE_SCOPES["fake"])
