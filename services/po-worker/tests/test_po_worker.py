from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from uuid import uuid4

MODULE = Path(__file__).parents[1] / "po_worker.py"
spec = importlib.util.spec_from_file_location("po_worker", MODULE)
po = importlib.util.module_from_spec(spec)
assert spec.loader
sys.modules[spec.name] = po
spec.loader.exec_module(po)


def valid_output(run_id: str, briefing_hash: str) -> dict:
    return {
        "contract_version": "1.0.0", "run_id": run_id,
        "briefing_hash": briefing_hash, "product_goal": "Gerenciar agenda",
        "stories": [{"story_id": "US-001", "title": "Criar evento",
          "narrative": "Como usuário quero criar um evento para organizar o dia",
          "priority": "MUST", "depends_on": [], "acceptance_criteria": [
            {"criterion_id": "AC-1", "order": 1, "description": "Evento aparece na agenda após salvar", "verification": "Consultar agenda"}], "ready": True}],
        "constraints": [], "assumptions": [], "out_of_scope": [],
        "coverage": [{"briefing_item": "Criar agenda", "story_ids": ["US-001"]}],
        "decisions": [], "needs_human": []}


def test_semantic_validation_rejects_cycle_and_orphan():
    run_id = str(uuid4()); output = valid_output(run_id, "sha256:" + "a" * 64)
    output["stories"][0]["depends_on"] = ["US-001"]
    output["coverage"] = [{"briefing_item": "x", "story_ids": ["US-999"]}]
    errors = po.semantic_errors(output, run_id=run_id, briefing_hash=output["briefing_hash"])
    assert any("auto-dependência" in error for error in errors)
    assert any("não coberta" in error for error in errors)


def test_execute_repairs_once_and_submits_without_extra_context(tmp_path):
    run_id = str(uuid4()); briefing = "Uma agenda pessoal simples e responsiva"
    briefing_hash = po.text_hash(briefing); output = valid_output(run_id, briefing_hash)
    schema = Path(__file__).parents[3] / "packages/contracts/schemas/v1/po-output.schema.json"
    settings = po.Settings(run_id, str(uuid4()), "http://api", "token", schema)
    class FakeApi:
        calls = 0; submitted = None
        def context(self):
            return {"role": "po", "run_id": run_id,
              "scopes": list(po.REQUIRED_SCOPES),
              "context_manifest": [{"source_type": "briefing", "hash": briefing_hash}],
              "input": {"briefing": briefing}}
        def heartbeat(self): pass
        def invoke(self, request):
            self.calls += 1
            return {"parsed": {"bad": True} if self.calls == 1 else output}
        def submit(self, value): self.submitted = value
    api = FakeApi()
    assert po.execute(settings, api) == output
    assert api.calls == 2 and api.submitted == output
    assert "agenda" not in json.dumps(po.build_prompt("outro domínio", run_id, briefing_hash))
