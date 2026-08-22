"""Configuração do control-api.

Lê apenas variáveis de ambiente. Nenhum segredo é embutido no código e nenhum
valor de banco é exposto a containers de agente.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CONTRACT_VERSION = "1.0.0"
CONTROL_SCHEMA = "control"

DEFAULT_TASK_TIMEOUT_SECONDS = 300
DEFAULT_TASK_MAX_ATTEMPTS = 3

# Nomes espelhados de infra/compose.yaml. O projeto Compose se chama
# `rivexx-squad`, e o Docker prefixa o nome da rede com ele.
DEFAULT_FAKE_WORKER_IMAGE = "rivexx/fake-worker:local"
DEFAULT_AGENT_NETWORK = "rivexx-squad_agent_net"

BASE_SCOPES = ("context:read", "output:write", "heartbeat:write")

# `model:invoke` e concedido por papel, nao por padrao. O fake worker nao fala
# com modelo; dar-lhe o escopo abriria o gateway a uma tarefa que nao precisa
# dele, e escopo nao usado e superficie gratuita.
ROLE_SCOPES: dict[str, tuple[str, ...]] = {
    "fake": BASE_SCOPES,
    "llm": BASE_SCOPES + ("model:invoke",),
    "po": BASE_SCOPES + ("model:invoke",),
    "dev": BASE_SCOPES + ("model:invoke", "artifact:write"),
    "qa": BASE_SCOPES + ("model:invoke", "artifact:write"),
    "runner": ("context:read", "output:write", "artifact:write"),
}


def _find_contracts_dir() -> Path:
    """Localiza `packages/contracts` subindo a partir deste arquivo.

    Em container o caminho vem de `CONTRACTS_DIR`; localmente a busca evita
    duplicar a estrutura do monorepo em configuração.
    """
    override = os.getenv("CONTRACTS_DIR")
    if override:
        return Path(override).resolve()

    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "packages" / "contracts"
        if candidate.is_dir():
            return candidate
    raise RuntimeError(
        "packages/contracts não encontrado; defina CONTRACTS_DIR apontando para o "
        "diretório de contratos versionado."
    )


@dataclass(frozen=True)
class Settings:
    database_url: str
    contracts_dir: Path
    public_base_url: str
    task_timeout_seconds: int
    task_max_attempts: int
    initial_task_role: str
    sql_echo: bool
    # Runtime e despacho (I1-005)
    runtime_backend: str
    fake_worker_image: str
    allowed_images: frozenset[str]
    agent_network: str
    internal_base_url: str
    scheduler_id: str
    scheduler_enabled: bool
    scheduler_idle_seconds: float
    worker_memory_limit: str
    worker_cpu_limit: float
    worker_pids_limit: int
    # Gateway de modelo (I1-008)
    model_provider: str
    model_providers: tuple[str, ...]
    model_routes: dict
    anthropic_default_model: str
    codex_binary: str
    codex_default_model: str
    anthropic_profile: str | None
    codex_home: str | None

    @property
    def state_machine_path(self) -> Path:
        return self.contracts_dir / "state-machine" / "v1.json"

    def scopes_for_role(self, role: str) -> tuple[str, ...]:
        """Escopos do token emitido para um papel.

        Fonte unica: o emissor do token e o gateway leem daqui, entao um papel
        nunca recebe token com escopo que o endpoint depois recusa.
        """
        return ROLE_SCOPES.get(role, BASE_SCOPES)


def _require_async_driver(url: str) -> str:
    """Garante driver async.

    `postgresql://` é o formato que aparece em documentação e em variáveis de
    ambiente de Compose. SQLAlchemy async exige `postgresql+asyncpg://`, e a
    falha nativa só aparece na primeira query — tarde demais para diagnosticar.
    """
    if url.startswith("postgresql+"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    raise ValueError(
        "DATABASE_URL deve usar o esquema postgresql:// ou postgresql+asyncpg://"
    )


def _model_providers() -> tuple[str, ...]:
    """Provedores a registrar.

    O provedor padrao entra sempre: uma lista que nao contem o provedor
    selecionado so produziria falha na primeira chamada real.
    """
    raw = os.getenv("MODEL_PROVIDERS", "")
    names = {item.strip().lower() for item in raw.split(",") if item.strip()}
    names.add(os.getenv("MODEL_PROVIDER", "echo").lower())
    names.add("echo")
    return tuple(sorted(names))


def _model_routes() -> dict:
    raw = os.getenv("MODEL_ROUTES", "").strip()
    if not raw:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("MODEL_ROUTES deve ser um objeto JSON indexado por papel")
    return parsed


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL não definida. O control-api é o único serviço com acesso "
            "ao PostgreSQL; containers de agente nunca recebem esta variável."
        )

    fake_worker_image = os.getenv("FAKE_WORKER_IMAGE", DEFAULT_FAKE_WORKER_IMAGE)
    # A allowlist sempre contém a imagem configurada: uma allowlist que exclui a
    # única imagem em uso só produziria falha na primeira execução real.
    allowed = {
        item.strip()
        for item in os.getenv("RUNTIME_IMAGE_ALLOWLIST", "").split(",")
        if item.strip()
    }
    allowed.add(fake_worker_image)

    model_provider = os.getenv("MODEL_PROVIDER", "echo").lower()
    initial_task_role = os.getenv(
        "INITIAL_TASK_ROLE", "fake" if model_provider == "echo" else "po"
    ).lower()
    if initial_task_role not in ROLE_SCOPES:
        raise ValueError(
            f"INITIAL_TASK_ROLE desconhecido: {initial_task_role}; "
            f"use um de {', '.join(sorted(ROLE_SCOPES))}"
        )

    return Settings(
        database_url=_require_async_driver(database_url),
        contracts_dir=_find_contracts_dir(),
        public_base_url=os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/"),
        task_timeout_seconds=int(
            os.getenv("TASK_TIMEOUT_SECONDS", DEFAULT_TASK_TIMEOUT_SECONDS)
        ),
        task_max_attempts=int(
            os.getenv("TASK_MAX_ATTEMPTS", DEFAULT_TASK_MAX_ATTEMPTS)
        ),
        initial_task_role=initial_task_role,
        sql_echo=os.getenv("SQL_ECHO", "").lower() in {"1", "true", "yes"},
        runtime_backend=os.getenv("RUNTIME_BACKEND", "docker").lower(),
        fake_worker_image=fake_worker_image,
        allowed_images=frozenset(allowed),
        agent_network=os.getenv("AGENT_NETWORK", DEFAULT_AGENT_NETWORK),
        # O worker fala com a API pelo nome do serviço na agent_net, nunca pelo
        # endereço público publicado no host.
        internal_base_url=os.getenv(
            "INTERNAL_BASE_URL", "http://control-api:8000"
        ).rstrip("/"),
        scheduler_id=os.getenv("SCHEDULER_ID", f"control-api-{os.getpid()}"),
        scheduler_enabled=os.getenv("SCHEDULER_ENABLED", "").lower()
        in {"1", "true", "yes"},
        scheduler_idle_seconds=float(os.getenv("SCHEDULER_IDLE_SECONDS", "1.0")),
        worker_memory_limit=os.getenv("WORKER_MEMORY_LIMIT", "128m"),
        worker_cpu_limit=float(os.getenv("WORKER_CPU_LIMIT", "0.5")),
        worker_pids_limit=int(os.getenv("WORKER_PIDS_LIMIT", "64")),
        model_provider=model_provider,
        model_providers=_model_providers(),
        model_routes=_model_routes(),
        anthropic_default_model=os.getenv(
            "ANTHROPIC_DEFAULT_MODEL", "claude-opus-5"
        ),
        codex_binary=os.getenv("CODEX_BINARY", "codex"),
        codex_default_model=os.getenv("CODEX_DEFAULT_MODEL", "gpt-5.6-terra"),
        anthropic_profile=os.getenv("ANTHROPIC_PROFILE") or None,
        codex_home=os.getenv("CODEX_HOME") or None,
    )
