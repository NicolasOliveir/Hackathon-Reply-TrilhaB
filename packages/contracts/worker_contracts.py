"""Cross-field invariants for the PO, Dev, QA and runner handoffs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any


class ContractInvariantError(ValueError):
    """A schema-valid document violates a worker handoff invariant."""


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _require_unique(values: Iterable[str], label: str) -> set[str]:
    collected = list(values)
    if len(collected) != len(set(collected)):
        raise ContractInvariantError(f"duplicate {label}")
    return set(collected)


def validate_po_output(document: Mapping[str, Any]) -> None:
    stories = document["stories"]
    story_ids = [story["story_id"] for story in stories]
    known = _require_unique(story_ids, "story_id")
    criterion_ids: set[str] = set()
    graph: dict[str, list[str]] = {}

    for story in stories:
        story_id = story["story_id"]
        dependencies = story["depends_on"]
        if story_id in dependencies:
            raise ContractInvariantError(f"{story_id} depends on itself")
        unknown = set(dependencies) - known
        if unknown:
            raise ContractInvariantError(
                f"{story_id} has unknown dependencies: {sorted(unknown)}"
            )
        graph[story_id] = dependencies

        criteria = story["acceptance_criteria"]
        if [item["order"] for item in criteria] != list(range(1, len(criteria) + 1)):
            raise ContractInvariantError(
                f"{story_id} criteria order must be contiguous from 1"
            )
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
            raise ContractInvariantError(
                f"coverage references unknown stories: {sorted(unknown)}"
            )
        covered.update(referenced)
    ready = {story["story_id"] for story in stories if story["ready"]}
    if not ready.issubset(covered):
        raise ContractInvariantError(
            f"ready stories without briefing coverage: {sorted(ready - covered)}"
        )


def freeze_po_handoffs(
    document: Mapping[str, Any], instructions: Mapping[str, Any]
) -> list[dict[str, Any]]:
    validate_po_output(document)
    backlog_hash = canonical_sha256(document)
    instructions_hash = canonical_sha256(instructions)
    return [
        {
            "contract_version": document["contract_version"],
            "run_id": document["run_id"],
            "story": story,
            "backlog_hash": backlog_hash,
            "story_hash": canonical_sha256(story),
            "po_instructions_hash": instructions_hash,
        }
        for story in document["stories"]
        if story["ready"]
    ]


def validate_dev_delivery(
    document: Mapping[str, Any], expected_criterion_ids: Iterable[str]
) -> None:
    expected = set(expected_criterion_ids)
    task_ids = _require_unique(
        (task["task_id"] for task in document["tasks"]), "Dev task_id"
    )
    covered = {
        criterion_id
        for task in document["tasks"]
        for criterion_id in task["criterion_ids"]
    }
    if not expected.issubset(covered):
        raise ContractInvariantError(
            f"Dev tasks do not cover criteria: {sorted(expected - covered)}"
        )
    for change in document["changes"]:
        unknown = set(change["task_ids"]) - task_ids
        if unknown:
            raise ContractInvariantError(
                f"change references unknown Dev tasks: {sorted(unknown)}"
            )

    evidence_by_criterion = {
        item["criterion_id"]: item["status"]
        for item in document["acceptance_evidence"]
    }
    unknown_evidence = set(evidence_by_criterion) - expected
    if unknown_evidence:
        raise ContractInvariantError(
            f"Dev evidence references unknown criteria: {sorted(unknown_evidence)}"
        )

    if document["status"] == "READY_FOR_QA":
        if any(task["state"] != "DONE" for task in document["tasks"]):
            raise ContractInvariantError("READY_FOR_QA contains a blocked Dev task")
        if any(run["status"] != "PASS" for run in document["verification_runs"]):
            raise ContractInvariantError("READY_FOR_QA contains a failed verification")
        if any(evidence_by_criterion.get(item) != "PASS" for item in expected):
            raise ContractInvariantError("READY_FOR_QA lacks PASS evidence for a criterion")


def validate_qa_test_plan(
    plan: Mapping[str, Any],
    story: Mapping[str, Any],
    delivery: Mapping[str, Any],
) -> None:
    identity_fields = ("run_id", "story_id", "story_hash")
    for field in identity_fields:
        source = story["story_id"] if field == "story_id" else delivery[field]
        if plan[field] != source:
            raise ContractInvariantError(f"QA plan {field} does not match delivery")
    if plan["revision"] != delivery["revision"]:
        raise ContractInvariantError("QA plan revision does not match delivery")
    if plan["delivery_manifest_hash"] != delivery["manifest_hash"]:
        raise ContractInvariantError("QA plan manifest hash does not match delivery")

    expected_criteria = [
        {
            "criterion_id": item["criterion_id"],
            "order": item["order"],
            "description": item["description"],
        }
        for item in story["acceptance_criteria"]
    ]
    if plan["criteria"] != expected_criteria:
        raise ContractInvariantError("QA changed criterion text, order or identity")

    case_ids = _require_unique((case["case_id"] for case in plan["cases"]), "case_id")
    if not case_ids:
        raise ContractInvariantError("QA plan has no cases")
    expected_ids = {item["criterion_id"] for item in expected_criteria}
    case_criteria = {case["criterion_id"] for case in plan["cases"]}
    if not expected_ids.issubset(case_criteria):
        raise ContractInvariantError(
            f"QA cases do not cover criteria: {sorted(expected_ids - case_criteria)}"
        )
    unknown = case_criteria - expected_ids
    if unknown:
        raise ContractInvariantError(
            f"QA cases reference unknown criteria: {sorted(unknown)}"
        )


def derive_runner_verdict(
    plan: Mapping[str, Any], result: Mapping[str, Any]
) -> str:
    """Derive the verdict in the control plane; the runner cannot submit one."""

    if result.get("verdict") is not None:
        raise ContractInvariantError("runner must not submit a verdict")
    if result["test_plan_hash"] != canonical_sha256(plan):
        raise ContractInvariantError("runner result references a different test plan")

    plan_cases = {case["case_id"]: case for case in plan["cases"]}
    result_cases = _require_unique(
        (item["case_id"] for item in result["results"]), "runner case_id"
    )
    required_cases = {
        case_id for case_id, case in plan_cases.items() if case["required"]
    }
    if result_cases != set(plan_cases):
        raise ContractInvariantError("runner results do not match the frozen test plan")
    if not required_cases.issubset(result_cases):
        raise ContractInvariantError("runner omitted a required case")
    for item in result["results"]:
        if item["criterion_id"] != plan_cases[item["case_id"]]["criterion_id"]:
            raise ContractInvariantError("runner changed the case-to-criterion mapping")

    if result["environment_status"] != "READY":
        return "NEEDS_HUMAN"
    statuses = {item["status"] for item in result["results"]}
    if statuses & {"ERROR", "TIMEOUT", "SKIPPED"}:
        return "NEEDS_HUMAN"
    if "FAIL" in statuses or result["overall_exit_code"] != 0:
        return "REJECTED"
    if statuses == {"PASS"}:
        return "ACCEPTED"
    return "NEEDS_HUMAN"
