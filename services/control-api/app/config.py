from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CONTROL_API_", extra="ignore")

    #: DSN async do PostgreSQL. Somente o control-api recebe esta variavel; containers
    #: de agente nunca a recebem (ORQUESTRADOR.md secao 4.3).
    database_url: str = "postgresql+asyncpg://control:control@localhost:5432/control"

    #: Base usada para montar `links.self` e `links.events` da RunResponse.
    public_base_url: str = "http://localhost:8000"

    #: Timeout da tarefa enfileirada, propagado ao scheduler em I1-005.
    task_timeout_seconds: int = 300

    db_echo: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
