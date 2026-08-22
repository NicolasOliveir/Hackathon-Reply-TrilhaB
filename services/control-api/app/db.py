"""Engine e sessão async.

O control-api é o único serviço com credencial de banco. Containers de agente
não entram na `control_net` e não recebem `DATABASE_URL`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import Settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(settings: Settings) -> AsyncEngine:
    global _engine, _session_factory
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.sql_echo,
            pool_pre_ping=True,
            # O MVP roda um processo único de API e scheduler; um pool enxuto
            # deixa espaço de conexão para o Alembic e para inspeção manual.
            pool_size=5,
            max_overflow=5,
        )
        _session_factory = async_sessionmaker(
            _engine, expire_on_commit=False, autoflush=False
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Engine não inicializada; chame init_engine no startup.")
    return _session_factory


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


@asynccontextmanager
async def transaction() -> AsyncIterator[AsyncSession]:
    """Uma transação por comando.

    Commit no sucesso, rollback em qualquer exceção. Nenhum caso de uso abre
    transação aninhada: o event log só é consistente se run, eventos e task
    forem gravados no mesmo escopo atômico.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def session_dependency() -> AsyncIterator[AsyncSession]:
    """Dependência FastAPI para leituras."""
    factory = get_session_factory()
    async with factory() as session:
        yield session
