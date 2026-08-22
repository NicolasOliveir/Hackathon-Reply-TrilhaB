from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from uuid import UUID

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


CONTRACT_VERSION = "1.0.0"
MAX_REPAIRS = 2
REQUIRED_SCOPES = {"context:read", "model:invoke", "heartbeat:write", "output:write"}


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def text_hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Settings:
    run_id: str
    task_id: str
    api_url: str
    token: str
    schema_path: Path

    @classmethod
    def from_env(cls) -> "Settings":
        if os.getenv("DATABASE_URL") or os.getenv("DOCKER_HOST"):
            raise ValueError("PO worker recebeu variável de ambiente proibida")
        required = ("RUN_ID", "TASK_ID", "CONTROL_API_URL", "TASK_TOKEN")
        missing = [key for key in required if not os.getenv(key)]
        if missing:
            raise ValueError("variáveis ausentes: " + ", ".join(missing))
        return cls(
            run_id=str(UUID(os.environ["RUN_ID"])),
            task_id=str(UUID(os.environ["TASK_ID"])),
            api_url=os.environ["CONTROL_API_URL"].rstrip("/"),
            token=os.environ["TASK_TOKEN"],
            schema_path=Path(os.getenv("PO_OUTPUT_SCHEMA", "/app/contracts/po-output.schema.json")),
        )


class Api:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def call(self, method: str, path: str, body: dict | None = None, **headers: str) -> dict:
        data = None if body is None else json.dumps(body, separators=(",", ":")).encode()
        request = Request(
            self.settings.api_url + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.settings.token}",
                "Accept": "application/json",
                **({"Content-Type": "application/json"} if data else {}),
                **headers,
            },
        )
        with urlopen(request, timeout=300) as response:  # noqa: S310 - URL is injected by runtime
            raw = response.read()
        return json.loads(raw) if raw else {}

    def context(self) -> dict:
        return self.call("GET", f"/internal/v1/tasks/{self.settings.task_id}/context")

    def heartbeat(self) -> None:
        self.call("POST", f"/internal/v1/tasks/{self.settings.task_id}/heartbeat", {})

    def invoke(self, request: dict) -> dict:
        return self.call("POST", f"/internal/v1/tasks/{self.settings.task_id}/model-invocations", request)

    def submit(self, output: dict) -> dict:
        key = hashlib.sha256(
            f"po:{self.settings.task_id}:{canonical_hash(output)}".encode()
        ).hexdigest()
        return self.call(
            "POST",
            f"/internal/v1/tasks/{self.settings.task_id}/po-output",
            output,
            **{"Idempotency-Key": key},
        )


def build_prompt(briefing: str, run_id: str, briefing_hash: str) -> tuple[str, str]:
    system = (
        "Você é o Product Owner de uma fábrica genérica de aplicações. Decomponha somente "
        "o briefing fornecido. Não escolha stack, não escreva testes e não declare aceite. "
        "Responda estritamente no JSON Schema. Critérios devem ser binários e observáveis."
    )
    prompt = (
        f"run_id: {run_id}\nbriefing_hash: {briefing_hash}\n\n"
        "Produza backlog priorizado. IDs de stories devem ser STORY-001 em diante e critérios "
        "AC-001 em diante por story. Cada item do briefing deve aparecer em coverage; dependências "
        "devem ser acíclicas. Marque ready=false se houver bloqueio humano.\n\nBRIEFING:\n"
        + briefing
    )
    return system, prompt


def semantic_errors(output: dict, *, run_id: str, briefing_hash: str) -> list[str]:
    errors: list[str] = []
    if output.get("run_id") != run_id:
        errors.append("/run_id: deve corresponder ao contexto")
    if output.get("briefing_hash") != briefing_hash:
        errors.append("/briefing_hash: deve corresponder ao manifesto")
    stories = output.get("stories")
    if not isinstance(stories, list) or not stories:
        return errors + ["/stories: deve conter ao menos uma story"]
    ids = [story.get("story_id") for story in stories if isinstance(story, dict)]
    if len(ids) != len(set(ids)):
        errors.append("/stories: story_id duplicado")
    known = set(ids)
    graph: dict[str, list[str]] = {}
    criterion_descriptions: set[str] = set()
    for index, story in enumerate(stories):
        sid = story.get("story_id")
        deps = story.get("depends_on", [])
        graph[str(sid)] = list(deps) if isinstance(deps, list) else []
        for dep in graph[str(sid)]:
            if dep not in known:
                errors.append(f"/stories/{index}/depends_on: referência inexistente {dep}")
            if dep == sid:
                errors.append(f"/stories/{index}/depends_on: auto-dependência")
        criteria = story.get("acceptance_criteria", [])
        orders = [item.get("order") for item in criteria if isinstance(item, dict)]
        if orders != list(range(1, len(orders) + 1)):
            errors.append(f"/stories/{index}/acceptance_criteria: order deve ser contínua")
        for criterion in criteria:
            text = str(criterion.get("description", "")).strip()
            if text in criterion_descriptions:
                errors.append(f"/stories/{index}/acceptance_criteria: descrição duplicada")
            criterion_descriptions.add(text)
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        cyclic = any(visit(dep) for dep in graph.get(node, []) if dep in graph)
        visiting.remove(node)
        visited.add(node)
        return cyclic
    if any(visit(node) for node in graph):
        errors.append("/stories: dependências devem formar grafo acíclico")
    covered = {
        sid
        for item in output.get("coverage", [])
        if isinstance(item, dict)
        for sid in item.get("story_ids", [])
    }
    for index, sid in enumerate(ids):
        if sid not in covered:
            errors.append(f"/stories/{index}: story não coberta por /coverage")
    if output.get("needs_human") and all(story.get("ready") for story in stories):
        errors.append("/stories: saída com needs_human deve manter ao menos uma story não pronta")
    return errors


def schema_errors(output: dict, schema: dict, schema_dir: Path) -> list[str]:
    registry = Registry()
    common_path = schema_dir / "common.schema.json"
    if common_path.exists():
        common = json.loads(common_path.read_text(encoding="utf-8"))
        registry = registry.with_resource(common["$id"], Resource.from_contents(common))
    errors = sorted(Draft202012Validator(schema, registry=registry).iter_errors(output), key=lambda item: list(item.absolute_path))
    return ["/" + "/".join(str(part) for part in error.absolute_path) + f": {error.message}" for error in errors]


def parse_model_output(response: dict) -> dict:
    parsed = response.get("parsed")
    if isinstance(parsed, dict):
        return parsed
    text = response.get("text")
    if not isinstance(text, str):
        raise ValueError("gateway não retornou JSON")
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("saída do PO deve ser objeto JSON")
    return value


def execute(settings: Settings, api: Api | None = None) -> dict:
    api = api or Api(settings)
    context = api.context()
    if context.get("role") != "po" or context.get("run_id") != settings.run_id:
        raise ValueError("contexto não pertence ao PO/run esperado")
    scopes = set(context.get("scopes", []))
    if not REQUIRED_SCOPES.issubset(scopes):
        raise ValueError("contexto do PO não contém os escopos mínimos")
    manifest = context.get("context_manifest", [])
    if len(manifest) != 1 or manifest[0].get("source_type") != "briefing":
        raise ValueError("PO deve receber exclusivamente o briefing")
    briefing = context.get("input", {}).get("briefing")
    briefing_hash = manifest[0].get("hash")
    if not isinstance(briefing, str) or text_hash(briefing) != briefing_hash:
        raise ValueError("briefing não confere com o manifesto")
    schema = json.loads(settings.schema_path.read_text(encoding="utf-8"))
    system, prompt = build_prompt(briefing, settings.run_id, briefing_hash)
    errors: list[str] = []
    for attempt in range(MAX_REPAIRS + 1):
        api.heartbeat()
        request = {
            "contract_version": CONTRACT_VERSION,
            "system": system,
            "prompt": prompt if not errors else (
                "Repare o JSON anterior e devolva o documento completo. Erros por JSON Pointer:\n"
                + "\n".join(errors)
            ),
            "output_schema": schema,
            "max_output_tokens": 16000,
        }
        try:
            output = parse_model_output(api.invoke(request))
            errors = schema_errors(output, schema, settings.schema_path.parent)
            if not errors:
                errors = semantic_errors(output, run_id=settings.run_id, briefing_hash=briefing_hash)
        except (ValueError, json.JSONDecodeError) as exc:
            errors = [f"/: JSON inválido: {exc}"]
        if not errors:
            api.submit(output)
            return output
        if attempt == MAX_REPAIRS:
            raise ValueError("saída do PO inválida após reparos: " + "; ".join(errors))
    raise AssertionError("unreachable")


def main() -> int:
    try:
        output = execute(Settings.from_env())
        print(json.dumps({"event": "po_completed", "backlog_hash": canonical_hash(output)}))
        return 0
    except Exception as exc:  # noqa: BLE001 - boundary sanitizes environment
        print(f"po-worker failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
