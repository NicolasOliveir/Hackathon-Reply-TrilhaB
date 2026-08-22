"""Fixtures dos testes.

Os testes de integração exigem PostgreSQL real, conforme o critério de conclusão
de `I1-004`. Sem `DATABASE_URL` alcançável eles são pulados com motivo explícito
— nunca aprovados silenciosamente por ausência de banco. Testes unitários que
não tocam o banco continuam rodando.

    docker compose -f services/control-api/docker-compose.test.yml up -d
    export DATABASE_URL=postgresql+asyncpg://control:control@localhost:55432/control_test
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVICE_ROOT.parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

CONTRACTS_DIR = REPO_ROOT / "packages" / "contracts"
SCHEMAS_DIR = CONTRACTS_DIR / "schemas" / "v1"

DEFAULT_TEST_URL = "postgresql+asyncpg://control:control@localhost:55432/control_test"


@pytest.fixture(scope="session", autouse=True)
def _environment() -> None:
    """Configura o ambiente. Não pula nada: testes unitários independem de banco."""
    os.environ.setdefault("DATABASE_URL", DEFAULT_TEST_URL)
    os.environ.setdefault("CONTRACTS_DIR", str(CONTRACTS_DIR))
    os.environ.setdefault("PUBLIC_BASE_URL", "http://localhost:8000")

    from app.config import get_settings

    get_settings.cache_clear()


async def _probe(url: str) -> str | None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return None
    except Exception as exc:  # noqa: BLE001 - a mensagem vira o motivo do skip
        return f"{type(exc).__name__}: {exc}"
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def database(_environment: None) -> str:
    url = os.environ["DATABASE_URL"]
    reason = asyncio.run(_probe(url))
    if reason is not None:
        pytest.skip(
            f"PostgreSQL indisponível em {url}: {reason}. "
            "Suba services/control-api/docker-compose.test.yml antes de rodar."
        )
    return url


@pytest.fixture(scope="session")
def migrated(database: str) -> None:
    """Aplica as migrations reais, não `metadata.create_all`.

    O trigger de append-only só existe na migration; criar as tabelas pelo
    metadata deixaria o teste de imutabilidade passando por ausência de trigger.
    """
    from alembic import command
    from alembic.config import Config

    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_ROOT / "migrations"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.fixture
async def clean_database(migrated: None):
    from sqlalchemy import text

    from app.config import get_settings
    from app.db import dispose_engine, init_engine

    engine = init_engine(get_settings())
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE control.events, control.agent_tasks, "
                "control.idempotency_keys, control.runs RESTART IDENTITY CASCADE"
            )
        )
    yield
    await dispose_engine()


@pytest.fixture
async def client(clean_database: None):
    import httpx

    from app.main import create_app

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as async_client:
        # O lifespan não roda sob ASGITransport; a engine já foi inicializada
        # por `clean_database`, com as mesmas settings.
        yield async_client


@pytest.fixture(scope="session")
def schema_validator():
    """Valida payloads contra os JSON Schemas versionados.

    Os testes checam o contrato real de `packages/contracts`, não uma cópia das
    regras reescrita aqui.
    """
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    resources = []
    for path in sorted(SCHEMAS_DIR.glob("*.schema.json")):
        document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        resources.append((document["$id"], Resource.from_contents(document)))
    registry = Registry().with_resources(resources)

    def _validate(schema_file: str, instance: Any) -> None:
        document = json.loads((SCHEMAS_DIR / schema_file).read_text(encoding="utf-8"))
        Draft202012Validator(document, registry=registry).validate(instance)

    return _validate
