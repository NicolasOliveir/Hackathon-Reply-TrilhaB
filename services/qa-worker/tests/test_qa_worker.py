from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from uuid import uuid4

MODULE = Path(__file__).parents[1] / "qa_worker.py"
spec = importlib.util.spec_from_file_location("qa_worker", MODULE)
qa = importlib.util.module_from_spec(spec); assert spec.loader
sys.modules[spec.name] = qa; spec.loader.exec_module(qa)

SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64


def plan(run_id: str) -> dict:
    return {"contract_version": "1.0.0", "run_id": run_id, "story_id": "STORY-001",
        "story_hash": SHA_A, "revision": 1, "delivery_manifest_hash": SHA_B,
        "criteria": [{"criterion_id": "AC-001", "order": 1,
                      "description": "A página principal responde."}],
        "cases": [{"case_id": "CASE-001", "criterion_id": "AC-001", "gate": "G2",
            "title": "Valida comportamento entregue", "test_type": "unit",
            "execution": {"argv": ["pytest", "/tests/test_generated.py", "-q"],
                          "cwd": "/tests", "timeout_seconds": 60, "profile": "python"},
            "expected": "Teste executável passa", "evidence_types": ["stdout"], "required": True}],
        "test_artifacts": [], "environment": {"rebuild_on_manifest_change": False,
            "manifest_paths": ["pyproject.toml"], "runner_profile": "python"}}


class FakeApi:
    def __init__(self, run_id: str, generated: dict):
        self.run_id = run_id; self.generated = generated; self.uploads = []; self.submitted = None

    def context(self):
        return {"role": "qa", "run_id": self.run_id, "scopes": list(qa.REQUIRED_SCOPES),
            "context_manifest": [{"source_type": "story", "hash": SHA_A},
                                 {"source_type": "delivery", "hash": SHA_B}],
            "input": {"story_hash": SHA_A, "delivery_manifest_hash": SHA_B,
                "story": {"story_id": "STORY-001", "title": "Página inicial",
                    "acceptance_criteria": [{"criterion_id": "AC-001", "order": 1,
                                              "description": "A página principal responde."}]},
                "code_delivery": {"status": "READY_FOR_QA", "manifest_hash": SHA_B,
                                  "changes": [{"path": "index.html", "summary": "Página"}]}}}

    def heartbeat(self): pass
    def invoke(self, request): return {"parsed": self.generated}
    def upload(self, path, kind, media_type, content):
        self.uploads.append((path, kind, content))
        return {"artifact_id": str(uuid4()), "kind": kind, "uri": "artifact://" + str(uuid4()),
                "media_type": media_type, "size_bytes": len(content),
                "sha256": "sha256:" + __import__("hashlib").sha256(content).hexdigest()}
    def submit(self, value): self.submitted = value; return {"accepted": True}


def test_real_generation_materializes_and_executes_test(tmp_path: Path):
    run_id = str(uuid4()); generated = {"plan": plan(run_id),
        "files": [{"path": "test_generated.py", "content": "def test_real_output():\n    assert 2 + 2 == 4\n"}]}
    api = FakeApi(run_id, generated)
    schema = Path(__file__).parents[3] / "packages/contracts/schemas/v1/qa-test-plan.schema.json"
    result_plan, report = qa.execute(qa.Settings(run_id, str(uuid4()), "http://api", "token", tmp_path, schema), api)
    assert report["status"] == "PASS"
    assert report["results"][0]["exit_code"] == 0
    assert (tmp_path / "test_generated.py").exists()
    assert api.submitted == result_plan
    assert any(kind == "qa-execution-report" for _, kind, _ in api.uploads)


def test_rejects_briefing_and_path_escape(tmp_path: Path):
    context = FakeApi(str(uuid4()), {}).context()
    context["context_manifest"].append({"source_type": "briefing", "hash": SHA_A})
    assert any(item["source_type"] == "briefing" for item in context["context_manifest"])
    try:
        qa._safe_target(tmp_path, "../secret")
    except ValueError as exc:
        assert "inseguro" in str(exc)
    else:
        raise AssertionError("path traversal deveria ser recusado")


def test_execution_reports_real_failure(tmp_path: Path):
    (tmp_path / "test_generated.py").write_text("def test_failure():\n    assert False\n", encoding="utf-8")
    report = qa.execute_cases(plan(str(uuid4())), tests_dir=tmp_path, workspace_dir=tmp_path)
    assert report["status"] == "FAIL"
    assert report["results"][0]["exit_code"] != 0
