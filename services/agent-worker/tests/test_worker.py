from __future__ import annotations

import importlib.util
import json
import sys
import threading
import unittest
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


WORKER_PATH = Path(__file__).resolve().parents[1] / "worker.py"
SCHEMAS_PATH = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "schemas" / "v1"
SPEC = importlib.util.spec_from_file_location("agent_worker", WORKER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("unable to load worker module")
worker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = worker
SPEC.loader.exec_module(worker)

RUN_ID = "11111111-1111-4111-8111-111111111111"
TASK_ID = "22222222-2222-4222-8222-222222222222"
TOKEN = "test-task-token"


class FakeCentralApiHandler(BaseHTTPRequestHandler):
    output: dict[str, Any] | None = None
    idempotency_key: str | None = None
    role = "fake"

    def do_GET(self) -> None:  # noqa: N802
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        self._send_json(
            HTTPStatus.OK,
            {
                "contract_version": "1.0.0",
                "task_id": TASK_ID,
                "run_id": RUN_ID,
                "role": type(self).role,
                "issued_at": "2026-08-22T16:00:02Z",
                "expires_at": "2026-08-22T16:05:02Z",
                "scopes": ["context:read", "output:write"]
                + (["model:invoke"] if type(self).role != "fake" else []),
                "context_manifest": [],
                "input": (
                    {"echo": "test"}
                    if type(self).role == "fake"
                    else {"briefing": "Criar uma aplicação de gestão genérica."}
                ),
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        if self.path.endswith("/model-invocations"):
            self._send_json(
                HTTPStatus.OK,
                {
                    "contract_version": "1.0.0",
                    "provider": "test-provider",
                    "model": "test-model",
                    "text": "Backlog inicial gerado pelo modelo real.",
                    "parsed": None,
                    "usage": {"input_tokens": 10, "output_tokens": 8},
                },
            )
            return
        type(self).idempotency_key = self.headers.get("Idempotency-Key")
        content_length = int(self.headers["Content-Length"])
        type(self).output = json.loads(self.rfile.read(content_length))
        self._send_json(HTTPStatus.ACCEPTED, {"accepted": True})

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class WorkerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        FakeCentralApiHandler.output = None
        FakeCentralApiHandler.idempotency_key = None
        FakeCentralApiHandler.role = "fake"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeCentralApiHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.settings = worker.Settings(
            run_id=RUN_ID,
            task_id=TASK_ID,
            api_url=f"http://{host}:{port}",
            task_token=TOKEN,
        )

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_fetches_context_and_submits_contract_output(self) -> None:
        result = worker.execute(
            self.settings, now=datetime(2026, 8, 22, 16, 0, 3, tzinfo=UTC)
        )

        self.assertEqual(FakeCentralApiHandler.output, result)
        self.assertEqual(result["contract_version"], "1.0.0")
        self.assertEqual(result["task_id"], TASK_ID)
        self.assertEqual(result["run_id"], RUN_ID)
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertRegex(result["received_context_hash"], r"^sha256:[a-f0-9]{64}$")
        self.assertRegex(
            FakeCentralApiHandler.idempotency_key or "", r"^[a-f0-9]{64}$"
        )
        schemas = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(SCHEMAS_PATH.glob("*.json"))
        ]
        registry = Registry().with_resources(
            (schema["$id"], Resource.from_contents(schema)) for schema in schemas
        )
        output_schema = next(
            schema for schema in schemas if schema["title"] == "FakeWorkerOutput"
        )
        errors = list(
            Draft202012Validator(
                output_schema,
                registry=registry,
                format_checker=FormatChecker(),
            ).iter_errors(result)
        )
        self.assertEqual(errors, [], [error.message for error in errors])

    def test_rejects_database_or_docker_credentials(self) -> None:
        base_environment = {
            "RUN_ID": RUN_ID,
            "TASK_ID": TASK_ID,
            "CONTROL_API_URL": self.settings.api_url,
            "TASK_TOKEN": TOKEN,
        }
        for forbidden_name in worker.FORBIDDEN_ENV:
            with self.subTest(variable=forbidden_name):
                with self.assertRaisesRegex(ValueError, "forbidden worker environment"):
                    worker.Settings.from_env(
                        {**base_environment, forbidden_name: "must-not-be-present"}
                    )

    def test_llm_role_invokes_gateway_and_submits_model_response(self) -> None:
        FakeCentralApiHandler.role = "po"

        result = worker.execute(
            self.settings, now=datetime(2026, 8, 22, 16, 0, 3, tzinfo=UTC)
        )

        self.assertEqual(result["message"], "Backlog inicial gerado pelo modelo real.")
        self.assertEqual(FakeCentralApiHandler.output, result)

    def test_rejects_context_from_another_run(self) -> None:
        context = {
            "contract_version": "1.0.0",
            "task_id": TASK_ID,
            "run_id": "33333333-3333-4333-8333-333333333333",
            "role": "fake",
            "scopes": ["context:read", "output:write"],
        }
        with self.assertRaisesRegex(ValueError, "run_id"):
            worker.validate_context(context, self.settings)


if __name__ == "__main__":
    unittest.main()
