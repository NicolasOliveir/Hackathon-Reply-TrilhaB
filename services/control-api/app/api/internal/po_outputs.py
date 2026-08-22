from __future__ import annotations

import hashlib
import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select

from ...config import CONTRACT_VERSION, Settings, get_settings
from ...contracts.v1.po_output_schema import PoOutput
from ...db import transaction
from ...model_gateway.gateway import usage_for_task
from ...persistence import idempotency
from ...persistence.event_store import EventDraft, EventStore, utc_now
from ...persistence.models import (
    AcceptanceCriterion, AgentTask, Backlog, BacklogCoverage, PoDecision, Run, Story,
)
from ...persistence.state_machine import load_state_machine
from .tasks import _authenticate

router = APIRouter(prefix="/internal/v1/tasks", tags=["internal"])
SCOPE = "po_output"


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def invariant_errors(body: dict) -> list[str]:
    errors: list[str] = []
    stories = body["stories"]
    ids = [story["story_id"] for story in stories]
    if len(ids) != len(set(ids)):
        errors.append("/stories: story_id duplicado")
    known = set(ids)
    graph = {story["story_id"]: story["depends_on"] for story in stories}
    descriptions: set[str] = set()
    for index, story in enumerate(stories):
        if any(dep not in known for dep in story["depends_on"]):
            errors.append(f"/stories/{index}/depends_on: referência inexistente")
        orders = [criterion["order"] for criterion in story["acceptance_criteria"]]
        if orders != list(range(1, len(orders) + 1)):
            errors.append(f"/stories/{index}/acceptance_criteria: ordem não contínua")
        for criterion in story["acceptance_criteria"]:
            if criterion["description"] in descriptions:
                errors.append(f"/stories/{index}/acceptance_criteria: descrição duplicada")
            descriptions.add(criterion["description"])
    visiting: set[str] = set(); visited: set[str] = set()
    def visit(node: str) -> bool:
        if node in visiting: return True
        if node in visited: return False
        visiting.add(node)
        cycle = any(visit(dep) for dep in graph[node] if dep in graph)
        visiting.remove(node); visited.add(node)
        return cycle
    if any(visit(node) for node in graph): errors.append("/stories: dependências cíclicas")
    covered = {sid for item in body["coverage"] for sid in item["story_ids"]}
    for index, sid in enumerate(ids):
        if sid not in covered: errors.append(f"/stories/{index}: story sem cobertura")
    if body["needs_human"] and all(story["ready"] for story in stories):
        errors.append("/stories: needs_human exige story não pronta")
    return errors


@router.post("/{task_id}/po-output", status_code=status.HTTP_202_ACCEPTED, response_model=None)
async def submit_po_output(
    task_id: uuid.UUID,
    payload: PoOutput,
    settings: Annotated[Settings, Depends(get_settings)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=255)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    async with transaction() as session:
        task = await _authenticate(session, task_id, authorization, allow_terminal_replay=True)
        if task.role != "po":
            raise HTTPException(status_code=403, detail="somente tarefa PO submete po-output")
        body = payload.model_dump(mode="json")
        if body["run_id"] != str(task.run_id):
            raise HTTPException(status_code=409, detail="run_id não corresponde à tarefa")
        replay = None
        try:
            replay = await idempotency.claim(session, scope=SCOPE, key=idempotency_key, request_hash=idempotency.hash_request(body))
        except idempotency.IdempotencyConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if replay is not None: return replay.body
        run = (await session.execute(select(Run).where(Run.run_id == task.run_id).with_for_update())).scalar_one()
        if body["briefing_hash"] != run.briefing_hash:
            raise HTTPException(status_code=409, detail="briefing_hash não corresponde ao run")
        errors = invariant_errors(body)
        if errors:
            raise HTTPException(status_code=422, detail={"errors": errors})
        backlog_hash = canonical_hash(body)
        session.add(Backlog(
            backlog_id=uuid.uuid4(), run_id=run.run_id, backlog_hash=backlog_hash,
            briefing_hash=run.briefing_hash, product_goal=body["product_goal"],
            constraints=body["constraints"], assumptions=body["assumptions"],
            out_of_scope=body["out_of_scope"], needs_human=body["needs_human"],
        ))
        drafts: list[EventDraft] = []
        dev_tasks: list[AgentTask] = []
        instructions_hash = canonical_hash({"contract_version": CONTRACT_VERSION, "role": "dev"})
        for story in body["stories"]:
            story_hash = canonical_hash(story)
            session.add(Story(id=uuid.uuid4(), run_id=run.run_id, story_id=story["story_id"], title=story["title"], narrative=story["narrative"], priority=story["priority"], depends_on=story["depends_on"], ready=story["ready"], story_hash=story_hash))
            for criterion in story["acceptance_criteria"]:
                session.add(AcceptanceCriterion(id=uuid.uuid4(), run_id=run.run_id, story_id=story["story_id"], criterion_id=criterion["criterion_id"], position=criterion["order"], description=criterion["description"], verification=criterion["verification"]))
            if story["ready"]:
                handoff = {"contract_version": CONTRACT_VERSION, "run_id": str(run.run_id), "story": story, "backlog_hash": backlog_hash, "story_hash": story_hash, "po_instructions_hash": instructions_hash}
                dev_task = AgentTask(task_id=uuid.uuid4(), run_id=run.run_id, role="dev", state="WAITING", attempt=1, max_attempts=settings.task_max_attempts, timeout_seconds=settings.task_timeout_seconds, token_hash=None, input_payload=handoff, available_at=utc_now(), created_at=utc_now(), updated_at=utc_now())
                session.add(dev_task); dev_tasks.append(dev_task)
                drafts.append(EventDraft(type="STORY_FROZEN", actor="po", task_id=task.task_id, payload={"story_id": story["story_id"], "story_hash": story_hash, "backlog_hash": backlog_hash, "dev_task_id": str(dev_task.task_id)}))
        for position, decision in enumerate(body["decisions"], 1): session.add(PoDecision(id=uuid.uuid4(), run_id=run.run_id, position=position, text=decision))
        for position, coverage in enumerate(body["coverage"], 1): session.add(BacklogCoverage(id=uuid.uuid4(), run_id=run.run_id, position=position, briefing_item=coverage["briefing_item"], story_ids=coverage["story_ids"]))
        usage = await usage_for_task(session, task.task_id)
        drafts.append(EventDraft(type="PO_COMPLETED", actor="po", task_id=task.task_id, meta=usage.as_event_meta(), payload={"backlog_hash": backlog_hash, "stories": len(body["stories"]), "ready_stories": len(dev_tasks), "needs_human": len(body["needs_human"])}))
        await EventStore(session, load_state_machine(settings.state_machine_path)).append(run, drafts)
        task.state = "SUCCEEDED"; task.updated_at = utc_now(); run.current_task_id = dev_tasks[0].task_id if dev_tasks else None
        accepted = {"accepted": True, "backlog_hash": backlog_hash, "dev_task_ids": [str(item.task_id) for item in dev_tasks]}
        await idempotency.record_response(session, scope=SCOPE, key=idempotency_key, status=202, body=accepted, run_id=run.run_id)
        return accepted
