from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.request import Request, urlopen
from uuid import UUID

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


CONTRACT_VERSION = "1.0.0"
REQUIRED_SCOPES = {"context:read", "model:invoke", "heartbeat:write", "output:write", "artifact:write"}
MAX_REPAIRS = 2
ALLOWED_COMMANDS = {"pytest", "pytest.exe", "python", "python.exe", "python3", "node", "node.exe", "npm", "npm.cmd", "npx", "npx.cmd", "pnpm", "pnpm.cmd"}


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class Settings:
    run_id: str
    task_id: str
    api_url: str
    token: str
    tests_dir: Path
    schema_path: Path

    @classmethod
    def from_env(cls) -> "Settings":
        if os.getenv("DATABASE_URL") or os.getenv("DOCKER_HOST"):
            raise ValueError("QA worker recebeu variável de ambiente proibida")
        required = ("RUN_ID", "TASK_ID", "CONTROL_API_URL", "TASK_TOKEN")
        missing = [name for name in required if not os.getenv(name)]
        if missing:
            raise ValueError("variáveis ausentes: " + ", ".join(missing))
        return cls(
            str(UUID(os.environ["RUN_ID"])), str(UUID(os.environ["TASK_ID"])),
            os.environ["CONTROL_API_URL"].rstrip("/"), os.environ["TASK_TOKEN"],
            Path(os.getenv("TESTS_DIR", "/tests")).resolve(),
            Path(os.getenv("QA_SCHEMA", "/app/contracts/qa-test-plan.schema.json")),
        )


class Api:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def call(self, method: str, path: str, body: dict | None = None, **headers: str) -> dict:
        data = None if body is None else json.dumps(body, separators=(",", ":")).encode()
        request = Request(self.settings.api_url + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.settings.token}", "Accept": "application/json",
            **({"Content-Type": "application/json"} if data else {}), **headers,
        })
        with urlopen(request, timeout=300) as response:  # noqa: S310 - runtime injects API URL
            raw = response.read()
        return json.loads(raw) if raw else {}

    def context(self) -> dict:
        return self.call("GET", f"/internal/v1/tasks/{self.settings.task_id}/context")

    def heartbeat(self) -> None:
        self.call("POST", f"/internal/v1/tasks/{self.settings.task_id}/heartbeat", {})

    def invoke(self, body: dict) -> dict:
        return self.call("POST", f"/internal/v1/tasks/{self.settings.task_id}/model-invocations", body)

    def upload(self, path: str, kind: str, media_type: str, content: bytes) -> dict:
        return self.call("POST", f"/internal/v1/tasks/{self.settings.task_id}/artifacts", {
            "contract_version": CONTRACT_VERSION, "path": path, "kind": kind,
            "media_type": media_type, "content_base64": base64.b64encode(content).decode(),
        })

    def submit(self, plan: dict) -> dict:
        key = hashlib.sha256(f"qa:{self.settings.task_id}:{canonical_hash(plan)}".encode()).hexdigest()
        return self.call("POST", f"/internal/v1/tasks/{self.settings.task_id}/qa-output", plan,
                         **{"Idempotency-Key": key})


def _story_and_delivery(context: dict) -> tuple[dict, dict]:
    payload = context.get("input")
    if not isinstance(payload, dict):
        raise ValueError("contexto QA sem input")
    story = payload.get("story") or payload.get("frozen_story")
    delivery = payload.get("code_delivery") or payload.get("delivery")
    if not isinstance(story, dict) or not isinstance(delivery, dict):
        raise ValueError("QA requer story congelada e dev-delivery")
    if delivery.get("status") not in {None, "READY_FOR_QA"} and not delivery.get("ready_for_qa"):
        raise ValueError("dev-delivery não está pronta para QA")
    return story, delivery


def _criteria(story: dict) -> list[dict]:
    items = story.get("acceptance_criteria") or story.get("criterios_aceite")
    if not isinstance(items, list) or not items:
        raise ValueError("story sem critérios de aceite")
    normalized = []
    for position, item in enumerate(items, 1):
        normalized.append({"criterion_id": item.get("criterion_id") or item.get("id"),
                           "order": item.get("order", position),
                           "description": item.get("description") or item.get("texto")})
    if any(not item["criterion_id"] or not item["description"] for item in normalized):
        raise ValueError("critério de aceite incompleto")
    return normalized


def generation_schema(plan_schema: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "required": ["plan", "files"],
            "properties": {"plan": plan_schema, "files": {"type": "array", "minItems": 1,
            "items": {"type": "object", "additionalProperties": False, "required": ["path", "content"],
            "properties": {"path": {"type": "string", "pattern": "^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$"},
                           "content": {"type": "string", "minLength": 1, "maxLength": 100000}}}}}}


def semantic_errors(generated: dict, context: dict, criteria: list[dict]) -> list[str]:
    plan = generated.get("plan", {})
    errors: list[str] = []
    expected = [(c["criterion_id"], c["order"], c["description"]) for c in criteria]
    actual = [(c.get("criterion_id"), c.get("order"), c.get("description")) for c in plan.get("criteria", [])]
    if actual != expected:
        errors.append("/plan/criteria: deve preservar IDs, ordem e texto canônico")
    covered = {case.get("criterion_id") for case in plan.get("cases", []) if case.get("required")}
    missing = [criterion[0] for criterion in expected if criterion[0] not in covered]
    if missing:
        errors.append("/plan/cases: critérios sem caso obrigatório: " + ", ".join(missing))
    if plan.get("run_id") != context.get("run_id"):
        errors.append("/plan/run_id: não corresponde ao contexto")
    story = context["input"].get("story") or context["input"].get("frozen_story")
    story_id = story.get("story_id") or story.get("id")
    story_hash = context["input"].get("story_hash") or story.get("story_hash") or story.get("frozen_hash")
    if plan.get("story_id") != story_id or plan.get("story_hash") != story_hash:
        errors.append("/plan: story_id/story_hash não correspondem ao contexto")
    file_paths = {item.get("path") for item in generated.get("files", [])}
    for case in plan.get("cases", []):
        for argument in case.get("execution", {}).get("argv", []):
            if argument.startswith("/tests/") and argument.removeprefix("/tests/") not in file_paths:
                errors.append(f"/files: comando referencia arquivo ausente {argument}")
    return errors


def _safe_target(root: Path, relative: str) -> Path:
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts:
        raise ValueError(f"path de teste inseguro: {relative}")
    target = (root / Path(*posix.parts)).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"path escapa de /tests: {relative}")
    return target


def execute_cases(plan: dict, *, tests_dir: Path, workspace_dir: Path) -> dict:
    """Executa argv sem shell e produz evidência; não deriva aceite da story."""
    results = []
    for case in plan["cases"]:
        spec = case["execution"]
        argv = list(spec["argv"])
        command = PurePosixPath(argv[0]).name
        if command not in ALLOWED_COMMANDS:
            raise ValueError(f"comando QA fora da allowlist: {command}")
        cwd_raw = spec["cwd"]
        if cwd_raw == "/tests" or cwd_raw.startswith("/tests/"):
            cwd = _safe_target(tests_dir, cwd_raw.removeprefix("/tests").lstrip("/") or ".")
        elif cwd_raw == "/workspace" or cwd_raw.startswith("/workspace/"):
            cwd = _safe_target(workspace_dir, cwd_raw.removeprefix("/workspace").lstrip("/") or ".")
        else:
            raise ValueError(f"cwd QA fora dos mounts: {cwd_raw}")
        translated = [str(_safe_target(tests_dir, item.removeprefix("/tests/")))
                      if item.startswith("/tests/") else item for item in argv]
        if command in {"pytest", "pytest.exe"}:
            # Usa o mesmo ambiente Python do worker, sem depender de um script
            # console no PATH (comportamento idêntico em Windows e Linux).
            translated = [sys.executable, "-m", "pytest", *translated[1:]]
        environment = {**os.environ, **spec.get("environment", {})}
        started = time.monotonic()
        try:
            completed = subprocess.run(translated, cwd=cwd, env=environment, capture_output=True,
                text=True, timeout=spec["timeout_seconds"], shell=False, check=False)  # noqa: S603
            exit_code = completed.returncode; stdout = completed.stdout[-20000:]; stderr = completed.stderr[-20000:]
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            exit_code = None; stdout = (exc.stdout or "")[-20000:]; stderr = (exc.stderr or "")[-20000:]
            timed_out = True
        except FileNotFoundError as exc:
            exit_code = None; stdout = ""; stderr = f"ferramenta indisponível: {exc}"
            timed_out = False
        results.append({"case_id": case["case_id"], "criterion_id": case["criterion_id"],
            "required": case["required"], "exit_code": exit_code, "timed_out": timed_out,
            "duration_ms": int((time.monotonic() - started) * 1000), "stdout": stdout, "stderr": stderr,
            "status": "PASS" if exit_code == 0 and not timed_out else "FAIL"})
    passed = all(item["status"] == "PASS" for item in results if item["required"])
    return {"kind": "QA_EXECUTION_REPORT", "story_id": plan["story_id"], "revision": plan["revision"],
            "status": "PASS" if passed else "FAIL", "results": results}


def parse_output(response: dict) -> dict:
    value = response.get("parsed")
    if not isinstance(value, dict):
        value = json.loads(response.get("text", ""))
    if not isinstance(value, dict):
        raise ValueError("saída QA não é objeto JSON")
    return value


def execute(settings: Settings, api: Api | None = None) -> tuple[dict, dict]:
    api = api or Api(settings)
    context = api.context()
    if context.get("role") != "qa" or context.get("run_id") != settings.run_id:
        raise ValueError("contexto não pertence ao QA/run esperado")
    if not REQUIRED_SCOPES.issubset(set(context.get("scopes", []))):
        raise ValueError("contexto QA sem escopos mínimos")
    if any(item.get("source_type") == "briefing" for item in context.get("context_manifest", [])):
        raise ValueError("QA não pode receber briefing")
    story, delivery = _story_and_delivery(context)
    criteria = _criteria(story)
    plan_schema = json.loads(settings.schema_path.read_text(encoding="utf-8"))
    schema = generation_schema(plan_schema)
    common = json.loads((settings.schema_path.parent / "common.schema.json").read_text(encoding="utf-8"))
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    system = ("Você é QA independente. Gere casos reais e arquivos de teste executáveis para a stack entregue. "
              "Preserve literalmente critérios e hashes. Não declare PASS, aceite ou reprovação; somente planeje. "
              "Todo argv deve ser allowlisted e referenciar arquivos em /tests. Responda somente no schema.")
    source = {"run_id": settings.run_id, "story": story, "dev_delivery": delivery,
              "delivery_manifest_hash": context["input"].get("delivery_manifest_hash") or delivery.get("manifest_hash"),
              "criteria": criteria}
    errors: list[str] = []
    generated: dict = {}
    for attempt in range(MAX_REPAIRS + 1):
        api.heartbeat()
        prompt = "Crie o plano QA e materialize testes genéricos para esta entrega:\n" + json.dumps(source, ensure_ascii=False)
        if errors:
            prompt += "\nRepare a saída anterior. Erros:\n" + "\n".join(errors) + "\nAnterior:\n" + json.dumps(generated, ensure_ascii=False)
        generated = parse_output(api.invoke({"contract_version": CONTRACT_VERSION, "system": system,
            "prompt": prompt, "output_schema": schema, "max_output_tokens": 16000}))
        errors = ["/" + "/".join(map(str, error.absolute_path)) + ": " + error.message
                  for error in Draft202012Validator(schema, registry=registry).iter_errors(generated)]
        errors += semantic_errors(generated, context, criteria) if not errors else []
        if not errors:
            break
        if attempt == MAX_REPAIRS:
            raise ValueError("saída QA inválida após reparos: " + "; ".join(errors))
    settings.tests_dir.mkdir(parents=True, exist_ok=True)
    refs = []
    for file in generated["files"]:
        target = _safe_target(settings.tests_dir, file["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(file["content"], encoding="utf-8")
        refs.append(api.upload("tests/" + file["path"], "qa-test", "text/plain; charset=utf-8", file["content"].encode()))
    plan = generated["plan"]
    plan["test_artifacts"] = refs
    config_path = f"config/{plan['story_id']}.r{plan['revision']}.json"
    config = json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2).encode()
    target = _safe_target(settings.tests_dir, config_path)
    target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(config)
    api.upload("tests/" + config_path, "qa-test-plan", "application/json", config)
    api.submit(plan)
    workspace = Path(os.getenv("WORKSPACE_DIR", "/workspace")).resolve()
    report = execute_cases(plan, tests_dir=settings.tests_dir, workspace_dir=workspace)
    report_bytes = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2).encode()
    api.upload(f"evidence/{plan['story_id']}.r{plan['revision']}.json", "qa-execution-report",
               "application/json", report_bytes)
    return plan, report


def main() -> int:
    try:
        plan, report = execute(Settings.from_env())
        print(json.dumps({"event": "qa_completed", "plan_hash": canonical_hash(plan),
                          "result": report["status"]}))
        return 0 if report["status"] == "PASS" else 2
    except Exception as exc:  # noqa: BLE001 - sanitized process boundary
        print(f"qa-worker failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
