"""Aplicação FastAPI do control-api.

Esqueleto mínimo da iteração 1: expõe apenas os endpoints de run entregues por
`I1-004`. O runtime de containers (`I1-005`) e o SSE (`I1-006`) registram seus
próprios routers aqui sem alterar este arquivo além da linha de inclusão.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.runs.router import router as runs_router
from .config import CONTRACT_VERSION, get_settings
from .db import dispose_engine, init_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    init_engine(settings)
    try:
        yield
    finally:
        await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Rivexx Squad Control API",
        version=CONTRACT_VERSION,
        lifespan=lifespan,
    )
    app.include_router(runs_router)

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "contract_version": CONTRACT_VERSION}

    return app


app = create_app()
