"""Aplicação FastAPI do control-api.

Iteração 1: endpoints de run (`I1-004`), endpoints internos de tarefa e laço do
scheduler (`I1-005`) e gateway de modelo (`I1-008`). O SSE (`I1-006`) registra
seu router aqui sem alterar mais nada.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.internal.model_invocations import router as model_invocations_router
from .api.internal.tasks import router as internal_tasks_router
from .api.internal.po_outputs import router as po_outputs_router
from .api.runs.backlog import router as backlog_router
from .api.events.router import router as events_router
from .api.runs.router import router as runs_router
from .config import CONTRACT_VERSION, get_settings
from .cors import install_panel_cors
from .db import dispose_engine, init_engine
from .model_gateway.credentials import describe
from .orchestration.loop import scheduler_task


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    init_engine(settings)
    try:
        async with scheduler_task(settings):
            yield
    finally:
        await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Rivexx Squad Control API",
        version=CONTRACT_VERSION,
        lifespan=lifespan,
    )
    install_panel_cors(app)
    app.include_router(runs_router)
    app.include_router(internal_tasks_router)
    app.include_router(po_outputs_router)
    app.include_router(model_invocations_router)
    app.include_router(events_router)
    app.include_router(backlog_router)

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "contract_version": CONTRACT_VERSION}

    @app.get("/health/providers", tags=["ops"])
    async def provider_health() -> dict:
        """Diagnostico de credencial dos provedores.

        Com plano em vez de chave, a falha tipica nao e 401: e perfil nao
        montado, nao gravavel ou com permissao aberta demais. Descobrir isso no
        meio da demo e tarde. Nenhum valor de credencial e devolvido.
        """
        settings = get_settings()
        statuses = describe(
            list(settings.model_providers), codex_binary=settings.codex_binary
        )
        return {
            "selected": settings.model_provider,
            "providers": [status.as_dict() for status in statuses],
        }

    return app


app = create_app()
