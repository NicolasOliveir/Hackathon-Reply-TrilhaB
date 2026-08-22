from __future__ import annotations

import hashlib
import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select

from ...config import Settings, get_settings
from ...contracts.v1.qa_test_plan_schema import QaTestPlan
from ...db import transaction
from ...model_gateway.gateway import usage_for_task
from ...persistence import idempotency
from ...persistence.event_store import EventDraft, EventStore, utc_now
from ...persistence.models import Run
from ...persistence.state_machine import load_state_machine
from .tasks import _authenticate

router = APIRouter(prefix="/internal/v1/tasks", tags=["internal"])
SCOPE = "qa_output"


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


@router.post("/{task_id}/qa-output", status_code=status.HTTP_202_ACCEPTED, response_model=None)
async def submit_qa_output(
    task_id: uuid.UUID,
    payload: QaTestPlan,
    settings: Annotated[Settings, Depends(get_settings)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=255)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    async with transaction() as session:
        task = await _authenticate(session, task_id, authorization, allow_terminal_replay=True)
        if task.role != "qa":
            raise HTTPException(status_code=403, detail="somente tarefa QA submete qa-output")
        body = payload.model_dump(mode="json")
        if body["run_id"] != str(task.run_id):
            raise HTTPException(status_code=409, detail="run_id não corresponde à tarefa")
        expected = task.input_payload or {}
        story = expected.get("story") or expected.get("frozen_story") or {}
        if body["story_id"] != (story.get("story_id") or story.get("id")):
            raise HTTPException(status_code=409, detail="story_id não corresponde à tarefa")
        expected_hash = expected.get("story_hash") or story.get("story_hash") or story.get("frozen_hash")
        if body["story_hash"] != expected_hash:
            raise HTTPException(status_code=409, detail="story_hash não corresponde à tarefa")
        try:
            replay = await idempotency.claim(session, scope=SCOPE, key=idempotency_key,
                request_hash=idempotency.hash_request(body))
        except idempotency.IdempotencyConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if replay is not None:
            return replay.body
        run = (await session.execute(select(Run).where(Run.run_id == task.run_id).with_for_update())).scalar_one()
        usage = await usage_for_task(session, task.task_id)
        plan_hash = canonical_hash(body)
        await EventStore(session, load_state_machine(settings.state_machine_path)).append(run, [EventDraft(
            type="TEST_PLAN_CREATED", actor="qa", task_id=task.task_id,
            meta=usage.as_event_meta(), payload={"story_id": body["story_id"], "story_hash": body["story_hash"],
                "revision": body["revision"], "test_plan_hash": plan_hash,
                "cases": len(body["cases"]), "artifacts": len(body["test_artifacts"])}
        )])
        task.state = "SUCCEEDED"; task.updated_at = utc_now()
        accepted = {"accepted": True, "test_plan_hash": plan_hash, "runner_verdict": None}
        await idempotency.record_response(session, scope=SCOPE, key=idempotency_key,
            status=202, body=accepted, run_id=run.run_id)
        return accepted
