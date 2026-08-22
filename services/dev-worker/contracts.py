from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


CONTRACT_VERSION = "1.0.0"
REQUIRED_SCOPES = {
    "context:read",
    "model:invoke",
    "heartbeat:write",
    "output:write",
    "artifact:write",
}


class ContractError(ValueError):
    """Documento válido em JSON, mas incompatível com o handoff congelado."""


def canonical_hash(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def text_hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


class Schemas:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._documents = {
            name: json.loads((directory / name).read_text(encoding="utf-8"))
            for name in (
                "common.schema.json",
                "agent-task-context.schema.json",
                "po-output.schema.json",
                "po-dev-handoff.schema.json",
                "dev-delivery.schema.json",
                "dev-plan.schema.json",
            )
        }
        registry = Registry()
        for document in self._documents.values():
            identifier = document.get("$id")
            if identifier:
                registry = registry.with_resource(identifier, Resource.from_contents(document))
        self._registry = registry

    def document(self, name: str) -> dict[str, Any]:
        return self._documents[name]

    def errors(self, name: str, value: Any) -> list[str]:
        validator = Draft202012Validator(
            self._documents[name],
            registry=self._registry,
            format_checker=FormatChecker(),
        )
        errors = sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path))
        return [
            "/" + "/".join(str(part) for part in error.absolute_path) + f": {error.message}"
            for error in errors
        ]

    def require(self, name: str, value: Any) -> None:
        errors = self.errors(name, value)
        if errors:
            raise ContractError(f"{name} inválido: " + "; ".join(errors))


def _contains_key(value: Any, forbidden: str) -> bool:
    if isinstance(value, Mapping):
        return forbidden in value or any(_contains_key(item, forbidden) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, forbidden) for item in value)
    return False


def validate_context(
    context: dict[str, Any],
    *,
    run_id: str,
    task_id: str,
    schemas: Schemas,
) -> dict[str, Any]:
    schemas.require("agent-task-context.schema.json", context)
    if context["role"] != "dev":
        raise ContractError("contexto não pertence ao papel dev")
    if context["run_id"] != run_id or context["task_id"] != task_id:
        raise ContractError("contexto pertence a outra run ou tarefa")
    if not REQUIRED_SCOPES.issubset(context["scopes"]):
        raise ContractError("contexto dev não contém os escopos mínimos")
    manifest = context["context_manifest"]
    if any(item["source_type"] == "briefing" for item in manifest):
        raise ContractError("Dev não pode receber briefing bruto")
    handoff = context["input"]
    if _contains_key(handoff, "briefing"):
        raise ContractError("input do Dev contém briefing bruto")
    schemas.require("po-dev-handoff.schema.json", handoff)
    if handoff["run_id"] != run_id:
        raise ContractError("PoDevHandoff pertence a outra run")
    if not handoff["story"]["ready"]:
        raise ContractError("story não está pronta/congelada para desenvolvimento")
    if canonical_hash(handoff["story"]) != handoff["story_hash"]:
        raise ContractError("story_hash não confere com a story congelada")
    manifested = {(item["source_type"], item["hash"]) for item in manifest}
    expected = {
        ("story", handoff["story_hash"]),
        ("contract", handoff["backlog_hash"]),
        ("contract", handoff["po_instructions_hash"]),
    }
    if not expected.issubset(manifested):
        raise ContractError("manifesto do contexto não cobre os hashes do PoDevHandoff")
    return handoff


def validate_relative_path(raw: str) -> str:
    if not isinstance(raw, str) or not raw or "\x00" in raw or "\\" in raw:
        raise ContractError(f"caminho de alteração inválido: {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ContractError(f"caminho fora do workspace: {raw!r}")
    if path.parts[0] == ".git":
        raise ContractError("alterações em .git são proibidas")
    return path.as_posix()


def validate_plan(plan: dict[str, Any], handoff: dict[str, Any], schemas: Schemas) -> list[str]:
    errors = schemas.errors("dev-plan.schema.json", plan)
    if errors:
        return errors
    story = handoff["story"]
    if plan["story_id"] != story["story_id"]:
        errors.append("/story_id: deve corresponder à story congelada")
    expected = {item["criterion_id"] for item in story["acceptance_criteria"]}
    task_ids = [task["task_id"] for task in plan["tasks"]]
    known_tasks = set(task_ids)
    if len(task_ids) != len(known_tasks):
        errors.append("/tasks: task_id duplicado")
    covered_by_tasks: set[str] = set()
    for index, task in enumerate(plan["tasks"]):
        criteria = set(task["criterion_ids"])
        unknown = criteria - expected
        if unknown:
            errors.append(f"/tasks/{index}/criterion_ids: critérios desconhecidos {sorted(unknown)}")
        covered_by_tasks.update(criteria)
    missing_tasks = expected - covered_by_tasks
    if missing_tasks:
        errors.append(f"/tasks: critérios sem tarefa {sorted(missing_tasks)}")

    paths: list[str] = []
    for index, change in enumerate(plan["file_changes"]):
        try:
            paths.append(validate_relative_path(change["path"]))
        except ContractError as exc:
            errors.append(f"/file_changes/{index}/path: {exc}")
        unknown_tasks = set(change["task_ids"]) - known_tasks
        if unknown_tasks:
            errors.append(f"/file_changes/{index}/task_ids: tarefas desconhecidas {sorted(unknown_tasks)}")
        if change["operation"] == "write" and "content" not in change:
            errors.append(f"/file_changes/{index}/content: obrigatório para write")
        if change["operation"] == "delete" and "content" in change:
            errors.append(f"/file_changes/{index}/content: proibido para delete")
    if len(paths) != len(set(paths)):
        errors.append("/file_changes: path duplicado")

    covered_by_verification: set[str] = set()
    allowed_commands = {
        "python": {"python", "python3", "pytest", "ruff", "mypy"},
        "node": {"node", "npm", "npx", "pnpm", "yarn"},
        "api": {"curl"},
        "browser": {"playwright"},
        "generic": {"git"},
    }
    for index, verification in enumerate(plan["verifications"]):
        criteria = set(verification["criterion_ids"])
        unknown = criteria - expected
        if unknown:
            errors.append(
                f"/verifications/{index}/criterion_ids: critérios desconhecidos {sorted(unknown)}"
            )
        covered_by_verification.update(criteria)
        execution = verification["execution"]
        cwd = PurePosixPath(execution["cwd"])
        if ".." in cwd.parts or not (
            execution["cwd"] == "/workspace" or execution["cwd"].startswith("/workspace/")
        ):
            errors.append(f"/verifications/{index}/execution/cwd: deve ficar em /workspace")
        profile = execution["profile"]
        if execution["argv"][0] not in allowed_commands[profile]:
            errors.append(
                f"/verifications/{index}/execution/argv/0: comando não permitido para {profile}"
            )
    missing_verifications = expected - covered_by_verification
    if missing_verifications:
        errors.append(f"/verifications: critérios sem verificação {sorted(missing_verifications)}")
    return errors


def validate_delivery(
    delivery: dict[str, Any],
    *,
    expected_criteria: Iterable[str],
    schemas: Schemas,
) -> None:
    schemas.require("dev-delivery.schema.json", delivery)
    expected = set(expected_criteria)
    tasks = delivery["tasks"]
    task_ids = [task["task_id"] for task in tasks]
    if len(task_ids) != len(set(task_ids)):
        raise ContractError("DevDelivery contém task_id duplicado")
    covered = {criterion for task in tasks for criterion in task["criterion_ids"]}
    if not expected.issubset(covered):
        raise ContractError("DevDelivery não cobre todos os critérios")
    known_tasks = set(task_ids)
    if any(set(change["task_ids"]) - known_tasks for change in delivery["changes"]):
        raise ContractError("DevDelivery referencia tarefa desconhecida em changes")
    evidence = {item["criterion_id"]: item["status"] for item in delivery["acceptance_evidence"]}
    if set(evidence) - expected:
        raise ContractError("DevDelivery contém evidência de critério desconhecido")
    if delivery["status"] == "READY_FOR_QA":
        if any(task["state"] != "DONE" for task in tasks):
            raise ContractError("READY_FOR_QA contém tarefa bloqueada")
        if any(item["status"] != "PASS" for item in delivery["verification_runs"]):
            raise ContractError("READY_FOR_QA contém verificação sem PASS")
        if any(evidence.get(item) != "PASS" for item in expected):
            raise ContractError("READY_FOR_QA não contém PASS para todo critério")
