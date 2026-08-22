from __future__ import annotations

import uuid
import pytest
from sqlalchemy import func, select

pytestmark = pytest.mark.asyncio
BRIEFING = "Organizar uma agenda pessoal responsiva com criação e consulta de eventos." 


async def _po_task(client, key: str):
    from app.db import get_session_factory
    from app.persistence.models import AgentTask
    from app.config import get_settings
    from app.orchestration.scheduler import Scheduler
    from app.persistence.state_machine import load_state_machine
    from app.runtime.fake_runtime import FakeContainerRuntime
    response = await client.post("/api/v1/runs", json={"contract_version": "1.0.0", "briefing": BRIEFING}, headers={"Idempotency-Key": key})
    run = response.json()
    async with get_session_factory()() as session:
        async with session.begin():
            task = await session.get(AgentTask, uuid.UUID(run["current_task_id"]))
            task.role = "po"
    settings = get_settings()
    runtime = FakeContainerRuntime(allowed_images=settings.allowed_images)
    await Scheduler(get_session_factory(), runtime, load_state_machine(settings.state_machine_path), settings).dispatch_next()
    spec = runtime.containers[0].spec
    context = (await client.get(f"/internal/v1/tasks/{spec.environment['TASK_ID']}/context", headers={"Authorization": f"Bearer {spec.environment['TASK_TOKEN']}"})).json()
    return run, spec.environment["TASK_ID"], spec.environment["TASK_TOKEN"], context


def _output(run_id: str, briefing_hash: str) -> dict:
    return {
        "contract_version": "1.0.0", "run_id": run_id, "briefing_hash": briefing_hash,
        "product_goal": "Organizar compromissos", "constraints": ["Interface responsiva"],
        "assumptions": [], "out_of_scope": ["Agenda compartilhada"], "decisions": ["Priorizar fluxo de criação"], "needs_human": [],
        "stories": [{"story_id": "STORY-001", "title": "Criar evento", "narrative": "Como usuário quero criar evento para organizar meu dia", "priority": "MUST", "depends_on": [], "ready": True,
          "acceptance_criteria": [{"criterion_id": "AC-001", "order": 1, "description": "O evento salvo aparece na agenda", "verification": "Salvar e consultar a agenda"}]}],
        "coverage": [{"briefing_item": "criação e consulta de eventos", "story_ids": ["STORY-001"]}],
    }


async def test_po_output_is_atomic_idempotent_and_creates_filtered_handoff(client):
    from app.db import get_session_factory
    from app.persistence.models import AgentTask, Backlog, Event
    run, task_id, token, context = await _po_task(client, "po-output-run-1")
    assert context["input"] == {"briefing": BRIEFING}
    payload = _output(run["run_id"], context["context_manifest"][0]["hash"])
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "po-callback-0001"}
    first = await client.post(f"/internal/v1/tasks/{task_id}/po-output", json=payload, headers=headers)
    second = await client.post(f"/internal/v1/tasks/{task_id}/po-output", json=payload, headers=headers)
    assert first.status_code == 202, first.text
    assert second.status_code == 202, second.text
    assert first.json() == second.json()
    backlog = await client.get(f"/api/v1/runs/{run['run_id']}/backlog")
    assert backlog.status_code == 200
    assert backlog.json()["stories"][0]["acceptance_criteria"][0]["criterion_id"] == "AC-001"
    async with get_session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(Backlog)) == 1
        event_types = list((await session.execute(select(Event.type).where(Event.run_id == uuid.UUID(run["run_id"])).order_by(Event.sequence))).scalars())
        dev = (await session.execute(select(AgentTask).where(AgentTask.run_id == uuid.UUID(run["run_id"]), AgentTask.role == "dev"))).scalar_one()
    assert event_types[-2:] == ["STORY_FROZEN", "PO_COMPLETED"]
    assert dev.state == "WAITING"
    assert BRIEFING not in str(dev.input_payload)
    assert dev.input_payload["story_hash"] == backlog.json()["stories"][0]["story_hash"]


async def test_po_rejects_semantic_error_without_partial_projection(client):
    from app.db import get_session_factory
    from app.persistence.models import Backlog
    run, task_id, token, context = await _po_task(client, "po-output-run-2")
    payload = _output(run["run_id"], context["context_manifest"][0]["hash"])
    payload["stories"][0]["depends_on"] = ["STORY-001"]
    response = await client.post(f"/internal/v1/tasks/{task_id}/po-output", json=payload, headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "po-callback-0002"})
    assert response.status_code == 422
    async with get_session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(Backlog)) == 0
