"""Configuração do control-api.

Lê apenas variáveis de ambiente. Nenhum segredo é embutido no código e nenhum
valor de banco é exposto a containers de agente.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CONTRACT_VERSION = "1.0.0"
CONTROL_SCHEMA = "control"

DEFAULT_TASK_TIMEOUT_SECONDS = 300
DEFAULT_TASK_MAX_ATTEMPTS = 3


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
    sql_echo: bool

    @property
    def state_machine_path(self) -> Path:
        return self.contracts_dir / "state-machine" / "v1.json"


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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL não definida. O control-api é o único serviço com acesso "
            "ao PostgreSQL; containers de agente nunca recebem esta variável."
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
        sql_echo=os.getenv("SQL_ECHO", "").lower() in {"1", "true", "yes"},
    )
