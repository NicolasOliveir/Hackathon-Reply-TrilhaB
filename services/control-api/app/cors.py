"""CORS mínimo para o painel web do MVP."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def install_panel_cors(app: FastAPI) -> None:
    """Permite ao painel acessar a API em outro porto ou dispositivo.

    O MVP não possui cookies nem autenticação de usuário. Por isso `*` é um
    default seguro para a demonstração local e permite abrir o painel pelo IP
    da máquina em um celular. Ambientes posteriores podem definir uma lista de
    origens separada por vírgulas em `CONTROL_PANEL_ORIGINS`.
    """
    configured = os.getenv("CONTROL_PANEL_ORIGINS", "*")
    origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
    if not origins:
        origins = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Content-Type",
            "Idempotency-Key",
            "Last-Event-ID",
        ],
    )
