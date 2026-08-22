from __future__ import annotations

import importlib.util
import io
import os
import sys
import threading
import unittest
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
STUB_PATH = REPOSITORY_ROOT / "infra" / "stubs" / "control-api" / "server.py"
WORKER_PATH = REPOSITORY_ROOT / "services" / "agent-worker" / "worker.py"
RUN_ID = "11111111-1111-4111-8111-111111111111"
TASK_ID = "22222222-2222-4222-8222-222222222222"
TOKEN = "stub-flow-task-token"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


stub_api = load_module("control_api_stub", STUB_PATH)
worker = load_module("stub_flow_worker", WORKER_PATH)


class StubFlowTestCase(unittest.TestCase):
    def test_worker_calls_real_stub_context_and_output_endpoints(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), stub_api.StubHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        settings = worker.Settings(
            run_id=RUN_ID,
            task_id=TASK_ID,
            api_url=f"http://{host}:{port}",
            task_token=TOKEN,
        )
        logs = io.StringIO()

        try:
            with patch.dict(
                os.environ,
                {"STUB_RUN_ID": RUN_ID, "STUB_TASK_TOKEN": TOKEN},
            ):
                with redirect_stdout(logs):
                    result = worker.execute(settings)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertIn('"event": "fake_worker_output_received"', logs.getvalue())


if __name__ == "__main__":
    unittest.main()
