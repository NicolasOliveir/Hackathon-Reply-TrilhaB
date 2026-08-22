from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import runs
from app.contracts.models import CONTRACT_VERSION
from app.persistence.database import dispose_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Rivexx Squad Control API",
        version=CONTRACT_VERSION,
        description="API minima da primeira iteracao distribuida.",
        lifespan=lifespan,
    )
    app.include_router(runs.router)

    @app.get("/health", tags=["operacional"], include_in_schema=False)
    async def health() -> dict[str, str]:
        """Sonda do Compose. Nao faz parte do contrato OpenAPI v1 de proposito:
        e endpoint operacional, nao superficie de agente."""
        return {"status": "ok", "contract_version": CONTRACT_VERSION}

    return app


app = create_app()
