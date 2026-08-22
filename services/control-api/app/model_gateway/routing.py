"""Roteamento de modelo por papel.

Cada papel do squad tem exigência diferente. O QA precisa julgar critério contra
evidência — errar ali libera código quebrado. O `fake` só ecoa. Cobrar o mesmo
modelo e o mesmo esforço dos dois desperdiça de um lado e arrisca do outro.

A rota escolhida entra no evento e na tabela de auditoria, então a decisão fica
visível no painel em vez de escondida em configuração.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

DEFAULT_PROVIDER = "echo"

# `effort` controla profundidade de raciocínio e gasto. `high` é o equilíbrio
# recomendado; `xhigh` fica para o QA, cujo erro é o mais caro da cadeia.
DEFAULT_ROUTES: dict[str, dict[str, str | None]] = {
    "fake": {"provider": None, "model": None, "effort": "low"},
    "po": {"provider": None, "model": None, "effort": "high"},
    "dev": {"provider": None, "model": None, "effort": "high"},
    "qa": {"provider": None, "model": None, "effort": "xhigh"},
    "runner": {"provider": None, "model": None, "effort": "low"},
}


@dataclass(frozen=True)
class Route:
    provider: str
    model: str | None
    effort: str | None
    reason: str


class ModelRouter:
    def __init__(
        self,
        default_provider: str = DEFAULT_PROVIDER,
        overrides: dict[str, dict] | None = None,
    ) -> None:
        self._default_provider = default_provider
        self._overrides = overrides or {}

    @classmethod
    def from_environment(cls) -> "ModelRouter":
        """Lê `MODEL_ROUTES` como JSON.

        Exemplo:
            {"qa": {"provider": "anthropic", "model": "claude-opus-5",
                    "effort": "xhigh"}}
        """
        raw = os.getenv("MODEL_ROUTES", "").strip()
        overrides: dict[str, dict] = {}
        if raw:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("MODEL_ROUTES deve ser um objeto JSON por papel")
            overrides = parsed
        return cls(
            default_provider=os.getenv("MODEL_PROVIDER", DEFAULT_PROVIDER).lower(),
            overrides=overrides,
        )

    def route(self, role: str) -> Route:
        base = DEFAULT_ROUTES.get(role, {"provider": None, "model": None, "effort": None})
        override = self._overrides.get(role, {})
        provider = (
            override.get("provider") or base.get("provider") or self._default_provider
        )
        model = override.get("model") or base.get("model")
        effort = override.get("effort") or base.get("effort")
        origin = "override" if override else "padrao"
        return Route(
            provider=provider,
            model=model,
            effort=effort,
            reason=(
                f"papel {role} roteado para {provider}/{model or 'modelo padrao do provedor'} "
                f"com esforco {effort or 'padrao'} ({origin})"
            ),
        )
