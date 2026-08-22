"""Diagnóstico de credencial — o caminho de plano (assinatura), sem chave de API.

Estes testes fixam o comportamento verificado no SDK `anthropic` 1.0.0: perfil
em `<config_dir>/configs/<perfil>.json`, perfil ativo em `active_config`, e
gravação de volta no refresh — que é o motivo de o diretório precisar ser
gravável dentro do container.
"""

from __future__ import annotations

import json
import os

import pytest

from app.model_gateway.credentials import (
    describe,
    describe_anthropic,
    describe_codex,
)


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    for name in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_PROFILE",
        "ANTHROPIC_CONFIG_DIR",
        "CODEX_HOME",
    ):
        monkeypatch.delenv(name, raising=False)


def _write_profile(root, name: str = "default") -> None:
    configs = root / "configs"
    configs.mkdir(parents=True, exist_ok=True)
    (configs / f"{name}.json").write_text(
        json.dumps({"auth_type": "user_oauth"}), encoding="utf-8"
    )


# ------------------------------------------------------------------ anthropic


def test_static_key_wins_over_profile(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-qualquer")
    monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", str(tmp_path))
    _write_profile(tmp_path)

    status = describe_anthropic()

    assert status.ready
    assert status.source == "ANTHROPIC_API_KEY"


def test_diagnostic_never_returns_the_credential_value(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-segredo-que-nao-pode-vazar")

    status = describe_anthropic()

    assert "sk-ant-segredo" not in json.dumps(status.as_dict())


def test_profile_is_detected_without_any_api_key(monkeypatch, tmp_path):
    """Caminho do plano: não existe chave, e mesmo assim está pronto."""
    monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", str(tmp_path))
    _write_profile(tmp_path)

    status = describe_anthropic()

    assert status.ready
    assert "default" in status.source


def test_active_config_selects_the_profile(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", str(tmp_path))
    _write_profile(tmp_path, "trabalho")
    (tmp_path / "active_config").write_text("trabalho", encoding="utf-8")

    status = describe_anthropic()

    assert status.ready
    assert "trabalho" in status.source


def test_env_profile_overrides_active_config(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_PROFILE", "demo")
    _write_profile(tmp_path, "demo")
    (tmp_path / "active_config").write_text("outro", encoding="utf-8")

    assert "demo" in describe_anthropic().source


def test_missing_profile_says_to_run_ant_auth_login(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", str(tmp_path))

    status = describe_anthropic()

    assert not status.ready
    assert "ant auth login" in status.detail


@pytest.mark.skipif(os.name == "nt", reason="permissão POSIX não se aplica no Windows")
def test_warns_when_the_profile_directory_is_read_only(monkeypatch, tmp_path):
    """O SDK grava o token renovado de volta; read-only quebra após a expiração."""
    monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", str(tmp_path))
    _write_profile(tmp_path)
    (tmp_path / "configs").chmod(0o500)

    status = describe_anthropic()

    try:
        assert status.ready
        assert any("gravável" in w for w in status.warnings)
    finally:
        (tmp_path / "configs").chmod(0o700)


@pytest.mark.skipif(os.name == "nt", reason="permissão POSIX não se aplica no Windows")
def test_warns_when_the_credential_is_group_readable(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", str(tmp_path))
    _write_profile(tmp_path)
    (tmp_path / "configs" / "default.json").chmod(0o644)

    assert any("chmod 600" in w for w in describe_anthropic().warnings)


# ---------------------------------------------------------------------- codex


def test_codex_without_binary_is_not_ready():
    status = describe_codex(binary="binario-que-nao-existe")

    assert not status.ready
    assert "PATH" in status.detail


# -------------------------------------------------------------------- resumo


def test_echo_is_always_ready():
    (status,) = describe(["echo"])

    assert status.ready
    assert status.source == "nenhuma"


def test_describe_covers_every_requested_provider():
    statuses = describe(["echo", "anthropic", "codex"])

    assert {s.provider for s in statuses} == {"echo", "anthropic", "codex"}
