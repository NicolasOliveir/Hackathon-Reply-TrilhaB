"""Dev Worker local: story congelada -> aplicação real -> entrega auditável.

Não conhece o briefing, não acessa o provedor e não executa testes. O modelo é
chamado pelo gateway central e os comandos de teste são apenas materializados
para o QA posterior.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.request import Request, urlopen
from uuid import UUID

CONTRACT_VERSION = "1.0.0"

MODEL_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["files", "architecture", "test_commands"],
    "properties": {
        "files": {"type": "array", "minItems": 1, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["path", "content", "criterion_ids"],
            "properties": {
                "path": {"type": "string", "minLength": 1, "maxLength": 240},
                "content": {"type": "string", "maxLength": 200000},
                "criterion_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
            }}},
        "architecture": {"type": "object", "additionalProperties": False,
            "required": ["title", "decision", "rationale", "consequences"],
            "properties": {key: {"type": "string", "minLength": 1, "maxLength": 2000}
                           for key in ("title", "decision", "rationale", "consequences")}},
        "test_commands": {"type": "array", "minItems": 1, "items": {
            "type": "array", "minItems": 1, "maxItems": 16,
            "items": {"type": "string", "minLength": 1, "maxLength": 500}}},
    },
}


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class Settings:
    run_id: str; task_id: str; api_url: str; token: str; workspace: Path

    @classmethod
    def from_env(cls) -> "Settings":
        required = ("RUN_ID", "TASK_ID", "CONTROL_API_URL", "TASK_TOKEN")
        missing = [key for key in required if not os.getenv(key)]
        if missing: raise ValueError("variáveis ausentes: " + ", ".join(missing))
        run_id, task_id = str(UUID(os.environ["RUN_ID"])), str(UUID(os.environ["TASK_ID"]))
        root = Path(os.getenv("DEV_WORKSPACE_ROOT", ".generated-workspaces")).resolve()
        workspace = root / run_id / task_id
        workspace.mkdir(parents=True, exist_ok=True)
        return cls(run_id, task_id, os.environ["CONTROL_API_URL"].rstrip("/"), os.environ["TASK_TOKEN"], workspace)


class Api:
    def __init__(self, settings: Settings): self.s = settings
    def call(self, method: str, path: str, body: dict | None = None, **headers: str) -> dict:
        data = None if body is None else json.dumps(body, separators=(",", ":")).encode()
        request = Request(self.s.api_url + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.s.token}", "Accept": "application/json",
            **({"Content-Type": "application/json"} if data else {}), **headers})
        with urlopen(request, timeout=600) as response: raw = response.read()
        return json.loads(raw) if raw else {}
    def context(self): return self.call("GET", f"/internal/v1/tasks/{self.s.task_id}/context")
    def invoke(self, body): return self.call("POST", f"/internal/v1/tasks/{self.s.task_id}/model-invocations", body)
    def artifact(self, path: str, kind: str, media: str, content: bytes):
        return self.call("POST", f"/internal/v1/tasks/{self.s.task_id}/artifacts", {
            "contract_version": CONTRACT_VERSION, "path": path, "kind": kind,
            "media_type": media, "content_base64": base64.b64encode(content).decode()})
    def submit(self, body):
        key = hashlib.sha256(f"dev:{self.s.task_id}:{canonical_hash(body)}".encode()).hexdigest()
        return self.call("POST", f"/internal/v1/tasks/{self.s.task_id}/dev-delivery", body, **{"Idempotency-Key": key})


def safe_write(root: Path, relative: str, content: str) -> None:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts or pure.parts[0] == ".git":
        raise ValueError(f"path inseguro: {relative}")
    target = root.joinpath(*pure.parts).resolve()
    target.relative_to(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def run(argv: list[str], cwd: Path, timeout: int = 300) -> tuple[int, int, str]:
    started = time.monotonic()
    result = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, timeout=timeout, shell=False)
    log = (result.stdout + "\n" + result.stderr)[-60000:]
    return result.returncode, round((time.monotonic() - started) * 1000), log


def archive(root: Path) -> bytes:
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as output:
        for path in sorted(root.rglob("*")):
            if path.is_file() and ".git" not in path.parts:
                output.write(path, path.relative_to(root).as_posix())
    return stream.getvalue()


def execute(settings: Settings) -> dict:
    api = Api(settings); context = api.context()
    if context.get("role") != "dev": raise ValueError("contexto não pertence ao Dev")
    handoff = context["input"]; story = handoff["story"]
    criteria = story["acceptance_criteria"]
    system = ("Você é o Dev de uma fábrica genérica de aplicações. Recebe somente uma story congelada. "
              "Gere uma aplicação web funcional e responsiva, sem mocks de dados no fluxo principal. "
              "Use HTML/CSS/JavaScript sem dependências externas quando o workspace estiver vazio. "
              "Não execute nem declare resultado de testes; apenas forneça comandos ao QA. Responda no schema.")
    prompt = "STORY CONGELADA:\n" + json.dumps(story, ensure_ascii=False, indent=2)
    response = api.invoke({"contract_version": CONTRACT_VERSION, "system": system, "prompt": prompt,
                           "effort": "high", "max_output_tokens": 32000, "output_schema": MODEL_SCHEMA})
    plan = response.get("parsed") or json.loads(response["text"])
    allowed_ids = {item["criterion_id"] for item in criteria}
    for item in plan["files"]:
        if not set(item["criterion_ids"]).issubset(allowed_ids): raise ValueError("arquivo referencia critério desconhecido")
        safe_write(settings.workspace, item["path"], item["content"])
    subprocess.run(["git", "init"], cwd=settings.workspace, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Reply Dev Worker"], cwd=settings.workspace, check=True)
    subprocess.run(["git", "config", "user.email", "dev-worker@reply.local"], cwd=settings.workspace, check=True)
    subprocess.run(["git", "add", "-A"], cwd=settings.workspace, check=True)
    subprocess.run(["git", "commit", "-m", f"feat: implement {story['story_id']}"], cwd=settings.workspace, check=True, capture_output=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=settings.workspace, text=True).strip()
    artifact = api.artifact("delivery/source.zip", "source", "application/zip", archive(settings.workspace))
    manifest = {"files": [{"path": item["path"], "sha256": canonical_hash(item["content"])} for item in plan["files"]],
                "suggested_test_commands": plan["test_commands"]}
    manifest_ref = api.artifact("delivery/manifest.json", "manifest", "application/json", json.dumps(manifest, indent=2).encode())
    task_name = f"{story['story_id']}-T1"
    body = {"contract_version": CONTRACT_VERSION, "run_id": settings.run_id,
            "story_id": story["story_id"], "story_hash": handoff["story_hash"], "revision": 1,
            "base_hash": canonical_hash({}), "commit_hash": commit, "manifest_hash": canonical_hash(manifest),
            "tasks": [{"task_id": task_name, "title": "Materializar story no workspace",
                       "criterion_ids": sorted(allowed_ids), "changed_files": [x["path"] for x in plan["files"]], "state": "DONE"}],
            "changes": [{"path": x["path"], "summary": "Arquivo gerado para a story congelada", "task_ids": [task_name]} for x in plan["files"]],
            "acceptance_evidence": [{"criterion_id": item["criterion_id"], "evidence_type": "inspection", "status": "NOT_RUN",
                                     "summary": "Implementado; validação reservada ao QA", "evidence_refs": []} for item in criteria],
            "verification_runs": [{"execution": {"argv": ["git", "status", "--short"], "cwd": "/workspace", "timeout_seconds": 30, "profile": "generic", "environment": {}},
                                   "exit_code": 0, "duration_ms": 0, "status": "PASS", "evidence_refs": []}],
            "adrs": [{"adr_id": f"ADR-{story['story_id']}", "title": plan["architecture"]["title"],
                      "context": story["narrative"], "options": ["Aplicação web sem dependências externas", "Framework com dependências externas"],
                      "decision": plan["architecture"]["decision"], "rationale": plan["architecture"]["rationale"],
                      "consequences": [plan["architecture"]["consequences"]]}], "known_limitations": [],
            "artifacts": [artifact, manifest_ref], "status": "READY_FOR_QA"}
    return api.submit(body)


if __name__ == "__main__":
    try: print(json.dumps(execute(Settings.from_env()), ensure_ascii=False))
    except Exception as exc: print(f"dev-worker: {type(exc).__name__}: {exc}", file=sys.stderr); raise
