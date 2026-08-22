"""Montagem dos provedores disponíveis.

Um provedor só é registrado se sua dependência existir. Registrar tudo e falhar
na chamada esconderia um erro de configuração até o meio da demo; falhar no
roteamento diz exatamente o que falta.
"""

from __future__ import annotations

import logging

from ..config import Settings
from .base import ModelProvider
from .echo_provider import EchoProvider
from .routing import ModelRouter

logger = logging.getLogger(__name__)


def build_providers(settings: Settings) -> dict[str, ModelProvider]:
    providers: dict[str, ModelProvider] = {"echo": EchoProvider()}

    for name in settings.model_providers:
        if name in {"echo", ""}:
            continue
        if name == "anthropic":
            from .anthropic_provider import AnthropicProvider

            providers["anthropic"] = AnthropicProvider(
                default_model=settings.anthropic_default_model
            )
        elif name == "codex":
            from .codex_provider import CodexProvider

            providers["codex"] = CodexProvider(
                binary=settings.codex_binary,
                default_model=settings.codex_default_model,
            )
        else:
            logger.warning("provedor desconhecido em MODEL_PROVIDERS: %s", name)

    return providers


def build_router(settings: Settings) -> ModelRouter:
    return ModelRouter(
        default_provider=settings.model_provider,
        overrides=settings.model_routes,
    )
