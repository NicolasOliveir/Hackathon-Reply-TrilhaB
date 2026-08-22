"""Callback de domínio do Dev Worker; o worker nunca escreve eventos diretamente."""
from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select

from ...config import Settings, get_settings
from ...contracts.v1.dev_delivery_schema import DevDelivery
from ...db import transaction
from ...model_gateway.gateway import usage_for_task
from ...persistence import idempotency
from ...persistence.event_store import EventDraft, EventStore, utc_now
from ...persistence.models import AgentTask, Run
from ...persistence.state_machine import load_state_machine
from .tasks import _authenticate

router = APIRouter(prefix="/internal/v1/tasks", tags=["internal"])
SCOPE = "dev_delivery"


@router.post("/{task_id}/dev-delivery", status_code=status.HTTP_202_ACCEPTED, response_model=None)
async def submit_dev_delivery(
    task_id: uuid.UUID,
    payload: DevDelivery,
    settings: Annotated[Settings, Depends(get_settings)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=255)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    async with transaction() as session:
        task = await _authenticate(session, task_id, authorization, allow_terminal_replay=True)
        if task.role != "dev":
            raise HTTPException(status_code=403, detail="somente tarefa Dev submete dev-delivery")
        body = payload.model_dump(mode="json")
        handoff = task.input_payload or {}
        if body["run_id"] != str(task.run_id):
            raise HTTPException(status_code=409, detail="run_id não corresponde à tarefa")
        if body["story_id"] != handoff.get("story", {}).get("story_id") or body["story_hash"] != handoff.get("story_hash"):
            raise HTTPException(status_code=409, detail="story/hash não correspondem ao handoff congelado")
        criterion_ids = {item["criterion_id"] for item in handoff.get("story", {}).get("acceptance_criteria", [])}
        evidenced = {item["criterion_id"] for item in body["acceptance_evidence"]}
        if not criterion_ids.issubset(evidenced):
            raise HTTPException(status_code=422, detail="todos os critérios precisam de evidência")
        # O Dev pode comprovar somente materialização/build. Evidência de
        # critério permanece NOT_RUN: PASS/FAIL pertence exclusivamente ao QA.
        if any(item["status"] == "PASS" for item in body["acceptance_evidence"]):
            raise HTTPException(status_code=422, detail="Dev não pode aprovar critério de aceite")
        replay = await idempotency.claim(session, scope=SCOPE, key=idempotency_key, request_hash=idempotency.hash_request(body))
        if replay is not None:
            return replay.body
        run = (await session.execute(select(Run).where(Run.run_id == task.run_id).with_for_update())).scalar_one()
        usage = await usage_for_task(session, task.task_id)
        drafts = [EventDraft(type="DEV_TASK_PLAN_CREATED", actor="dev", task_id=task.task_id, payload={"story_id": body["story_id"], "tasks": body["tasks"]})]
        drafts.extend(EventDraft(type="ADR_RECORDED", actor="dev", task_id=task.task_id, payload=adr) for adr in body["adrs"])
        drafts.extend(EventDraft(type="TOOL_EXECUTED", actor="dev", task_id=task.task_id, payload={"execution": item["execution"], "exit_code": item["exit_code"], "duration_ms": item["duration_ms"], "status": item["status"], "evidence_refs": item["evidence_refs"]}) for item in body["verification_runs"])
        event_type = "CODE_DELIVERED" if body["status"] == "READY_FOR_QA" else "AGENT_FAILED"
        drafts.append(EventDraft(type=event_type, actor="dev", task_id=task.task_id, meta=usage.as_event_meta(), payload={"story_id": body["story_id"], "story_hash": body["story_hash"], "commit_hash": body["commit_hash"], "manifest_hash": body["manifest_hash"], "status": body["status"], "artifacts": body["artifacts"]}))
        await EventStore(session, load_state_machine(settings.state_machine_path)).append(run, drafts)
        task.state = "SUCCEEDED" if body["status"] == "READY_FOR_QA" else "FAILED"
        task.updated_at = utc_now()
        accepted = {"accepted": True, "status": body["status"], "commit_hash": body["commit_hash"]}
        await idempotency.record_response(session, scope=SCOPE, key=idempotency_key, status=202, body=accepted, run_id=run.run_id)
        return accepted
