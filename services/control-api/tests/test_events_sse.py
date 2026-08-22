"""Testes do SSE: contrato, cursor, paginação e retomada."""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio

BRIEFING = (
    "Centralizar não conformidades da Rivexx e rastrear lotes do insumo "
    "recebido ao produto expedido."
)


async def _create_run(client, key: str) -> dict:
    response = await client.post(
        "/api/v1/runs",
        json={"contract_version": "1.0.0", "briefing": BRIEFING},
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 202, response.text
    return response.json()


def _decode(chunk: str) -> tuple[int, dict]:
    fields = dict(line.split(": ", 1) for line in chunk.strip().splitlines())
    return int(fields["id"]), json.loads(fields["data"])


async def test_stream_emits_ordered_contract_events(client, schema_validator):
    from app.api.events.router import stream_run_events

    run = await _create_run(client, "sse-key-0001")
    response = await stream_run_events(uuid.UUID(run["run_id"]), None)
    iterator = response.body_iterator

    try:
        chunks = [await anext(iterator) for _ in range(3)]
    finally:
        await iterator.aclose()

    decoded = [_decode(chunk) for chunk in chunks]
    assert [event_id for event_id, _ in decoded] == [1, 2, 3]
    assert [body["sequence"] for _, body in decoded] == [1, 2, 3]
    assert all(body["run_id"] == run["run_id"] for _, body in decoded)
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"

    for _, body in decoded:
        schema_validator("event-envelope.schema.json", body)


async def test_last_event_id_resumes_exclusively(client):
    from app.api.events.router import stream_run_events

    run = await _create_run(client, "sse-key-0002")
    response = await stream_run_events(uuid.UUID(run["run_id"]), 1)
    iterator = response.body_iterator

    try:
        second = _decode(await anext(iterator))
        third = _decode(await anext(iterator))
    finally:
        await iterator.aclose()

    assert [second[0], third[0]] == [2, 3]
    assert [second[1]["sequence"], third[1]["sequence"]] == [2, 3]


async def test_paginated_stream_does_not_duplicate_and_follows_new_event(client):
    from app.api.events.stream import iter_run_events
    from app.config import get_settings
    from app.db import transaction
    from app.persistence.event_store import EventDraft, EventStore
    from app.persistence.state_machine import load_state_machine

    run_response = await _create_run(client, "sse-key-0003")
    run_id = uuid.UUID(run_response["run_id"])
    settings = get_settings()
    iterator = iter_run_events(
        run_id,
        settings,
        batch_size=2,
        heartbeat_seconds=60,
        poll_interval_seconds=0,
    )

    try:
        initial = [_decode(await anext(iterator))[0] for _ in range(3)]

        async with transaction() as session:
            store = EventStore(
                session,
                load_state_machine(settings.state_machine_path),
            )
            run = await store.lock_run(run_id)
            assert run is not None
            await store.append(
                run,
                [
                    EventDraft(
                        type="AGENT_STARTED",
                        actor="fake_worker",
                        task_id=run.current_task_id,
                        payload={"role": "fake", "attempt": 1},
                        drives_transition=True,
                    )
                ],
            )

        following = _decode(await anext(iterator))
    finally:
        await iterator.aclose()

    assert initial == [1, 2, 3]
    assert following[0] == 4
    assert following[1]["sequence"] == 4
    assert following[1]["type"] == "AGENT_STARTED"


async def test_idle_stream_emits_heartbeat_without_replaying_events(client):
    from app.api.events.stream import iter_run_events
    from app.config import get_settings

    run = await _create_run(client, "sse-key-0004")
    iterator = iter_run_events(
        uuid.UUID(run["run_id"]),
        get_settings(),
        heartbeat_seconds=0,
        poll_interval_seconds=0,
    )

    try:
        emitted = [_decode(await anext(iterator))[0] for _ in range(3)]
        heartbeat = await anext(iterator)
    finally:
        await iterator.aclose()

    assert emitted == [1, 2, 3]
    assert heartbeat == ": keep-alive\n\n"


async def test_unknown_run_returns_404_before_stream_starts(client):
    from app.api.events.router import stream_run_events

    missing = uuid.uuid4()
    with pytest.raises(HTTPException) as caught:
        await stream_run_events(missing, None)

    assert caught.value.status_code == 404
    assert str(missing) in caught.value.detail


async def test_negative_last_event_id_is_rejected_by_http_contract(client):
    run = await _create_run(client, "sse-key-0005")

    response = await client.get(
        f"/api/v1/runs/{run['run_id']}/events",
        headers={"Last-Event-ID": "-1"},
    )

    assert response.status_code == 422


async def test_openapi_exposes_sse_resume_header():
    from app.main import create_app

    operation = create_app().openapi()["paths"]["/api/v1/runs/{run_id}/events"]["get"]
    resume = next(
        parameter
        for parameter in operation["parameters"]
        if parameter["name"] == "Last-Event-ID"
    )

    assert resume["in"] == "header"
    assert resume["required"] is False
    integer_schema = next(
        option
        for option in resume["schema"]["anyOf"]
        if option.get("type") == "integer"
    )
    assert integer_schema["minimum"] == 0
    assert "text/event-stream" in operation["responses"]["200"]["content"]
