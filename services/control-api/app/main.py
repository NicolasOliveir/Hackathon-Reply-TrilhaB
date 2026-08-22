"""Aplicação FastAPI do control-api.

Iteração 1: endpoints de run (`I1-004`), endpoints internos de tarefa e laço do
scheduler (`I1-005`). O SSE (`I1-006`) registra seu router aqui sem alterar
mais nada.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.internal.tasks import router as internal_tasks_router
from .api.events.router import router as events_router
from .api.runs.router import router as runs_router
from .config import CONTRACT_VERSION, get_settings
from .cors import install_panel_cors
from .db import dispose_engine, init_engine
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
    app.include_router(events_router)

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "contract_version": CONTRACT_VERSION}

    return app


app = create_app()
