"""Deterministic semantics shared by the control plane and worker implementations."""
from __future__ import annotations
import hashlib
import json
from collections.abc import Mapping
from typing import Any

class ContractInvariantError(ValueError):
    """A schema-valid document violates a cross-field worker invariant."""

def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

def validate_po_output(document: Mapping[str, Any]) -> None:
    stories = document["stories"]
    story_ids = [story["story_id"] for story in stories]
    if len(story_ids) != len(set(story_ids)):
        raise ContractInvariantError("duplicate story_id")
    known = set(story_ids)
    criterion_ids: set[str] = set()
    graph: dict[str, list[str]] = {}
    for story in stories:
        story_id = story["story_id"]
        dependencies = story["depends_on"]
        if story_id in dependencies:
            raise ContractInvariantError(f"{story_id} depends on itself")
        unknown = set(dependencies) - known
        if unknown:
            raise ContractInvariantError(f"{story_id} has unknown dependencies: {sorted(unknown)}")
        graph[story_id] = dependencies
        criteria = story["acceptance_criteria"]
        if [item["order"] for item in criteria] != list(range(1, len(criteria) + 1)):
            raise ContractInvariantError(f"{story_id} criteria order must be contiguous from 1")
        for criterion in criteria:
            criterion_id = criterion["criterion_id"]
            if criterion_id in criterion_ids:
                raise ContractInvariantError(f"duplicate criterion_id: {criterion_id}")
            criterion_ids.add(criterion_id)
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(story_id: str) -> None:
        if story_id in visiting:
            raise ContractInvariantError("story dependency graph contains a cycle")
        if story_id in visited:
            return
        visiting.add(story_id)
        for dependency in graph[story_id]:
            visit(dependency)
        visiting.remove(story_id)
        visited.add(story_id)
    for story_id in story_ids:
        visit(story_id)
    covered: set[str] = set()
    for mapping in document["coverage"]:
        referenced = set(mapping["story_ids"])
        unknown = referenced - known
        if unknown:
            raise ContractInvariantError(f"coverage references unknown stories: {sorted(unknown)}")
        covered.update(referenced)
    ready = {story["story_id"] for story in stories if story["ready"]}
    if not ready.issubset(covered):
        raise ContractInvariantError(f"ready stories without briefing coverage: {sorted(ready - covered)}")

def freeze_po_handoffs(document: Mapping[str, Any], instructions: Mapping[str, Any]) -> list[dict[str, Any]]:
    validate_po_output(document)
    backlog_hash = canonical_sha256(document)
    instructions_hash = canonical_sha256(instructions)
    return [{"contract_version": document["contract_version"], "run_id": document["run_id"], "story": story, "backlog_hash": backlog_hash, "story_hash": canonical_sha256(story), "po_instructions_hash": instructions_hash} for story in document["stories"] if story["ready"]]
