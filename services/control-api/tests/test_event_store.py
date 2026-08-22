from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import delete, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.models import EventActor, EventType, RunState
from app.persistence import event_store
from app.persistence.tables import Event, Run
from tests.conftest import requires_postgres

pytestmark = requires_postgres


async def _nova_run(session: AsyncSession) -> Run:
    run = Run(
        id=uuid.uuid4(),
        briefing="Briefing de teste com tamanho suficiente para o contrato.",
        client_reference=None,
        state=RunState.RECEIVED.value,
        last_sequence=0,
    )
    session.add(run)
    await session.flush()
    return run


async def test_sequencia_comeca_em_um_e_nao_tem_buraco(session: AsyncSession) -> None:
    run = await _nova_run(session)

    envelopes = [
        await event_store.append(
            session,
            run_id=run.id,
            actor=EventActor.SYSTEM,
            event_type=EventType.RUN_CREATED,
        )
        for _ in range(5)
    ]

    assert [envelope.sequence for envelope in envelopes] == [1, 2, 3, 4, 5]


async def test_append_concorrente_nao_repete_sequencia(session: AsyncSession) -> None:
    """Dois appends simultaneos na mesma run precisam serializar na linha da run."""
    run = await _nova_run(session)
    await session.commit()

    engine = session.get_bind()
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def append_em_sessao_propria() -> int:
        async with maker() as outra:
            envelope = await event_store.append(
                outra,
                run_id=run.id,
                actor=EventActor.SYSTEM,
                event_type=EventType.RUN_CREATED,
            )
            await outra.commit()
            return envelope.sequence

    sequencias = await asyncio.gather(
        append_em_sessao_propria(), append_em_sessao_propria()
    )
    assert sorted(sequencias) == [1, 2]


async def test_evento_nao_pode_ser_alterado(session: AsyncSession) -> None:
    run = await _nova_run(session)
    envelope = await event_store.append(
        session,
        run_id=run.id,
        actor=EventActor.SYSTEM,
        event_type=EventType.RUN_CREATED,
    )
    await session.commit()

    with pytest.raises(DBAPIError, match="append-only"):
        await session.execute(
            update(Event).where(Event.id == envelope.event_id).values(type="RUN_FAILED")
        )
    await session.rollback()


async def test_evento_nao_pode_ser_removido(session: AsyncSession) -> None:
    run = await _nova_run(session)
    envelope = await event_store.append(
        session,
        run_id=run.id,
        actor=EventActor.SYSTEM,
        event_type=EventType.RUN_CREATED,
    )
    await session.commit()

    with pytest.raises(DBAPIError, match="append-only"):
        await session.execute(delete(Event).where(Event.id == envelope.event_id))
    await session.rollback()


async def test_transicao_invalida_nao_altera_estado(session: AsyncSession) -> None:
    run = await _nova_run(session)
    run.state = RunState.COMPLETED.value
    await session.flush()

    from app.contracts.state_machine import InvalidTransition

    with pytest.raises(InvalidTransition):
        await event_store.apply_transition(
            session, run=run, event_type=EventType.TASK_QUEUED
        )
    assert run.state == RunState.COMPLETED.value


async def test_listagem_retoma_a_partir_de_sequence(session: AsyncSession) -> None:
    run = await _nova_run(session)
    for _ in range(4):
        await event_store.append(
            session,
            run_id=run.id,
            actor=EventActor.SYSTEM,
            event_type=EventType.RUN_CREATED,
        )

    restantes = await event_store.list_events(session, run_id=run.id, after_sequence=2)
    assert [envelope.sequence for envelope in restantes] == [3, 4]


async def test_append_em_run_inexistente_falha(session: AsyncSession) -> None:
    with pytest.raises(event_store.RunNotFound):
        await event_store.append(
            session,
            run_id=uuid.uuid4(),
            actor=EventActor.SYSTEM,
            event_type=EventType.RUN_CREATED,
        )
