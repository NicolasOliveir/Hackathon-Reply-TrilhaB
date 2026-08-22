from __future__ import annotations
import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ...db import session_dependency
from ...persistence.models import AcceptanceCriterion, Backlog, BacklogCoverage, PoDecision, Story

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])

@router.get("/{run_id}/backlog", response_model=None)
async def get_backlog(run_id: uuid.UUID, session: Annotated[AsyncSession, Depends(session_dependency)]) -> dict:
    backlog = (await session.execute(select(Backlog).where(Backlog.run_id == run_id))).scalar_one_or_none()
    if backlog is None: raise HTTPException(status_code=404, detail="Backlog ainda não produzido")
    stories = (await session.execute(select(Story).where(Story.run_id == run_id).order_by(Story.story_id))).scalars().all()
    criteria = (await session.execute(select(AcceptanceCriterion).where(AcceptanceCriterion.run_id == run_id).order_by(AcceptanceCriterion.story_id, AcceptanceCriterion.position))).scalars().all()
    by_story: dict[str, list[dict]] = {}
    for item in criteria: by_story.setdefault(item.story_id, []).append({"criterion_id": item.criterion_id, "order": item.position, "description": item.description, "verification": item.verification})
    decisions = (await session.execute(select(PoDecision).where(PoDecision.run_id == run_id).order_by(PoDecision.position))).scalars().all()
    coverage = (await session.execute(select(BacklogCoverage).where(BacklogCoverage.run_id == run_id).order_by(BacklogCoverage.position))).scalars().all()
    return {"run_id": str(run_id), "backlog_hash": backlog.backlog_hash, "briefing_hash": backlog.briefing_hash, "product_goal": backlog.product_goal, "constraints": backlog.constraints, "assumptions": backlog.assumptions, "out_of_scope": backlog.out_of_scope, "needs_human": backlog.needs_human, "stories": [{"story_id": item.story_id, "title": item.title, "narrative": item.narrative, "priority": item.priority, "depends_on": item.depends_on, "ready": item.ready, "story_hash": item.story_hash, "acceptance_criteria": by_story.get(item.story_id, [])} for item in stories], "decisions": [item.text for item in decisions], "coverage": [{"briefing_item": item.briefing_item, "story_ids": item.story_ids} for item in coverage]}
