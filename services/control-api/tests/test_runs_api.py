from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.models import EventType, RunResponse, RunState
from app.persistence.tables import AgentTask, Event, Run
from tests.conftest import load_example, requires_postgres

pytestmark = requires_postgres

BRIEFING = load_example("valid/create-run-request.json")


def _headers(key: str) -> dict[str, str]:
    return {"Idempotency-Key": key}


async def test_criar_run_retorna_202_e_contrato_valido(client: AsyncClient) -> None:
    response = await client.post("/api/v1/runs", json=BRIEFING, headers=_headers("chave-0001"))

    assert response.status_code == 202
    body = RunResponse.model_validate(response.json())
    assert body.state is RunState.WORKER_QUEUED
    assert body.current_task_id is not None
    assert str(body.run_id) in body.links.events


async def test_criar_run_grava_cadeia_de_causalidade(
    client: AsyncClient, session: AsyncSession
) -> None:
    response = await client.post("/api/v1/runs", json=BRIEFING, headers=_headers("chave-0002"))
    run_id = uuid.UUID(response.json()["run_id"])

    eventos = (
        await session.execute(
            select(Event).where(Event.run_id == run_id).order_by(Event.sequence)
        )
    ).scalars().all()

    assert [evento.type for evento in eventos] == [
        EventType.RUN_CREATED.value,
        EventType.BRIEFING_RECEIVED.value,
        EventType.TASK_QUEUED.value,
    ]
    assert [evento.sequence for evento in eventos] == [1, 2, 3]

    # Causalidade encadeada: cada evento aponta para quem o disparou.
    assert eventos[0].causation_id is None
    assert eventos[1].causation_id == eventos[0].id
    assert eventos[2].causation_id == eventos[1].id
    assert all(evento.correlation_id == str(run_id) for evento in eventos)


async def test_briefing_nao_e_gravado_em_claro_no_evento(
    client: AsyncClient, session: AsyncSession
) -> None:
    """O event log e exibido ao avaliador; o briefing bruto fica so na tabela `runs`."""
    response = await client.post("/api/v1/runs", json=BRIEFING, headers=_headers("chave-0003"))
    run_id = uuid.UUID(response.json()["run_id"])

    evento = (
        await session.execute(
            select(Event).where(
                Event.run_id == run_id, Event.type == EventType.BRIEFING_RECEIVED.value
            )
        )
    ).scalar_one()

    assert "briefing" not in evento.payload
    assert evento.payload["briefing_hash"].startswith("sha256:")
    assert evento.payload["briefing_length"] == len(BRIEFING["briefing"])


async def test_primeira_task_fica_pendente_para_o_scheduler(
    client: AsyncClient, session: AsyncSession
) -> None:
    response = await client.post("/api/v1/runs", json=BRIEFING, headers=_headers("chave-0004"))
    run_id = uuid.UUID(response.json()["run_id"])

    task = (
        await session.execute(select(AgentTask).where(AgentTask.run_id == run_id))
    ).scalar_one()

    assert task.state == "PENDING"
    assert task.role == "fake"
    assert task.attempt == 1
    assert task.token_hash is None  # o token so e emitido no despacho (I1-005)


async def test_mesma_chave_e_mesmo_payload_nao_duplica(
    client: AsyncClient, session: AsyncSession
) -> None:
    primeira = await client.post("/api/v1/runs", json=BRIEFING, headers=_headers("chave-0005"))
    segunda = await client.post("/api/v1/runs", json=BRIEFING, headers=_headers("chave-0005"))

    assert segunda.status_code == 202
    assert segunda.json()["run_id"] == primeira.json()["run_id"]
    assert segunda.headers.get("Idempotency-Replayed") == "true"

    total_runs = await session.scalar(select(func.count()).select_from(Run))
    total_eventos = await session.scalar(select(func.count()).select_from(Event))
    assert total_runs == 1
    assert total_eventos == 3


async def test_mesma_chave_com_payload_diferente_e_conflito(client: AsyncClient) -> None:
    await client.post("/api/v1/runs", json=BRIEFING, headers=_headers("chave-0006"))

    outro = BRIEFING | {"briefing": "Outro briefing completamente diferente do primeiro."}
    conflito = await client.post("/api/v1/runs", json=outro, headers=_headers("chave-0006"))

    assert conflito.status_code == 409


async def test_idempotency_key_e_obrigatoria(client: AsyncClient) -> None:
    response = await client.post("/api/v1/runs", json=BRIEFING)
    assert response.status_code == 422


async def test_briefing_curto_e_recusado(client: AsyncClient) -> None:
    curto = BRIEFING | {"briefing": "curto"}
    response = await client.post("/api/v1/runs", json=curto, headers=_headers("chave-0007"))
    assert response.status_code == 422


async def test_consultar_run_existente(client: AsyncClient) -> None:
    criada = await client.post("/api/v1/runs", json=BRIEFING, headers=_headers("chave-0008"))
    run_id = criada.json()["run_id"]

    consulta = await client.get(f"/api/v1/runs/{run_id}")
    assert consulta.status_code == 200
    assert RunResponse.model_validate(consulta.json()).run_id == uuid.UUID(run_id)


async def test_consultar_run_inexistente(client: AsyncClient) -> None:
    resposta = await client.get(f"/api/v1/runs/{uuid.uuid4()}")
    assert resposta.status_code == 404
