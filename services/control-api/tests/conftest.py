from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

#: `httpx` e `sqlalchemy` sao importados dentro das fixtures de propriedade. Assim os
#: testes de contrato e de maquina de estados rodam so com pydantic e pytest, sem exigir
#: a stack completa nem PostgreSQL.

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_DIR = REPO_ROOT / "packages" / "contracts"

#: `app.contracts.state_machine` resolve o contrato pelo caminho do pacote; em teste o
#: worktree pode estar em outro lugar, entao a variavel e fixada antes do import da app.
os.environ.setdefault("CONTRACTS_DIR", str(CONTRACTS_DIR))

#: Testes de integracao exigem PostgreSQL real, conforme o criterio de conclusao de
#: I1-004. Sem DSN, eles sao pulados com motivo explicito — nunca silenciosamente.
TEST_DATABASE_URL = os.getenv("CONTROL_API_TEST_DATABASE_URL")

requires_postgres = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason=(
        "defina CONTROL_API_TEST_DATABASE_URL apontando para um PostgreSQL real "
        "(ex.: postgresql+asyncpg://control:control@localhost:5432/control_test)"
    ),
)


def load_example(relative: str) -> dict:
    with (CONTRACTS_DIR / "examples" / "v1" / relative).open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="session")
def contract_manifest() -> dict:
    with (CONTRACTS_DIR / "examples" / "v1" / "manifest.json").open(
        encoding="utf-8"
    ) as handle:
        return json.load(handle)


@pytest_asyncio.fixture
async def session() -> AsyncIterator["AsyncSession"]:
    """Sessao contra o schema `control` recriado a cada teste, sem residuo entre eles."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.persistence.tables import Base

    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as connection:
        await connection.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS control")
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
        await connection.exec_driver_sql(
            """
            CREATE OR REPLACE FUNCTION control.reject_event_mutation()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'control.events e append-only: % nao e permitido', TG_OP;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        await connection.exec_driver_sql(
            "DROP TRIGGER IF EXISTS trg_events_append_only ON control.events"
        )
        await connection.exec_driver_sql(
            """
            CREATE TRIGGER trg_events_append_only
            BEFORE UPDATE OR DELETE ON control.events
            FOR EACH ROW EXECUTE FUNCTION control.reject_event_mutation();
            """
        )

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db_session:
        yield db_session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(session) -> AsyncIterator["AsyncClient"]:
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app
    from app.persistence.database import get_session

    app = create_app()
    app.dependency_overrides[get_session] = lambda: iter_session(session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def iter_session(session):
    yield session
