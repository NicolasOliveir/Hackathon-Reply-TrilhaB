"""Testes do event log: sequência, correlação, causalidade e transição."""

from __future__ import annotations

import pytest
from sqlalchemy import select

pytestmark = pytest.mark.asyncio

BRIEFING = (
    "Centralizar não conformidades da Rivexx e rastrear lotes do insumo "
    "recebido ao produto expedido."
)

EXPECTED_SEQUENCE = ["RUN_CREATED", "BRIEFING_RECEIVED", "TASK_QUEUED"]


async def _create_run(client, key: str) -> dict:
    response = await client.post(
        "/api/v1/runs",
        json={"contract_version": "1.0.0", "briefing": BRIEFING},
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 202, response.text
    return response.json()


async def _events(run_id: str):
    from app.db import get_session_factory
    from app.persistence.models import Event

    async with get_session_factory()() as session:
        result = await session.execute(
            select(Event).where(Event.run_id == run_id).order_by(Event.sequence)
        )
        return list(result.scalars().all())


async def test_creation_emits_the_contracted_event_chain(client):
    run = await _create_run(client, "evt-key-0001")
    events = await _events(run["run_id"])

    assert [event.type for event in events] == EXPECTED_SEQUENCE
    assert [event.sequence for event in events] == [1, 2, 3]


async def test_every_event_carries_correlation_and_causation(client):
    run = await _create_run(client, "evt-key-0002")
    events = await _events(run["run_id"])

    assert all(event.correlation_id == run["run_id"] for event in events)
    # O primeiro evento não tem causa; cada seguinte aponta para o anterior.
    assert events[0].causation_id is None
    assert events[1].causation_id == events[0].event_id
    assert events[2].causation_id == events[1].event_id


async def test_task_queued_carries_the_current_task(client):
    run = await _create_run(client, "evt-key-0003")
    events = await _events(run["run_id"])

    queued = events[-1]
    assert queued.type == "TASK_QUEUED"
    assert str(queued.task_id) == run["current_task_id"]
    assert queued.payload["role"] == "fake"
    assert queued.payload["attempt"] == 1


async def test_events_validate_against_the_versioned_contract(
    client, schema_validator
):
    run = await _create_run(client, "evt-key-0004")
    events = await _events(run["run_id"])

    for event in events:
        schema_validator(
            "event-envelope.schema.json",
            {
                "contract_version": "1.0.0",
                "event_id": str(event.event_id),
                "sequence": event.sequence,
                "run_id": str(event.run_id),
                "ts": event.ts.isoformat(),
                "actor": event.actor,
                "type": event.type,
                "correlation_id": event.correlation_id,
                "causation_id": (
                    str(event.causation_id) if event.causation_id else None
                ),
                "task_id": str(event.task_id) if event.task_id else None,
                "payload": event.payload,
                "meta": event.meta,
            },
        )


async def test_sequences_are_independent_per_run(client):
    first = await _create_run(client, "evt-key-0005")
    second = await _create_run(client, "evt-key-0006")

    assert [e.sequence for e in await _events(first["run_id"])] == [1, 2, 3]
    assert [e.sequence for e in await _events(second["run_id"])] == [1, 2, 3]


async def test_list_events_resumes_after_a_sequence(client):
    from app.config import get_settings
    from app.db import get_session_factory
    from app.persistence.event_store import EventStore
    from app.persistence.state_machine import load_state_machine

    run = await _create_run(client, "evt-key-0007")
    settings = get_settings()

    async with get_session_factory()() as session:
        store = EventStore(session, load_state_machine(settings.state_machine_path))
        resumed = await store.list_events(run["run_id"], after_sequence=1)

    assert [event.sequence for event in resumed] == [2, 3]
