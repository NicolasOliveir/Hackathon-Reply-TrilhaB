from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


CONTEXT_PATH = re.compile(r"^/internal/v1/tasks/([^/]+)/context$")
OUTPUT_PATH = re.compile(r"^/internal/v1/tasks/([^/]+)/outputs$")


def utc_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class StubHandler(BaseHTTPRequestHandler):
    server_version = "RivexxControlApiStub/1.0"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path == "/health":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return

        match = CONTEXT_PATH.fullmatch(self.path)
        if match is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"detail": "not found"})
            return
        if not self._is_authorized():
            self._send_json(HTTPStatus.FORBIDDEN, {"detail": "invalid task token"})
            return

        now = datetime.now(UTC)
        context = {
            "contract_version": "1.0.0",
            "task_id": match.group(1),
            "run_id": os.environ.get(
                "STUB_RUN_ID", "11111111-1111-4111-8111-111111111111"
            ),
            "role": "fake",
            "issued_at": utc_timestamp(now),
            "expires_at": utc_timestamp(now + timedelta(minutes=5)),
            "scopes": ["context:read", "output:write"],
            "context_manifest": [],
            "input": {"echo": "first-distributed-slice"},
        }
        self._send_json(HTTPStatus.OK, context)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        match = OUTPUT_PATH.fullmatch(self.path)
        if match is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"detail": "not found"})
            return
        if not self._is_authorized():
            self._send_json(HTTPStatus.FORBIDDEN, {"detail": "invalid task token"})
            return

        idempotency_key = self.headers.get("Idempotency-Key", "")
        if len(idempotency_key) < 8:
            self._send_json(
                HTTPStatus.BAD_REQUEST, {"detail": "missing idempotency key"}
            )
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(content_length))
        except (ValueError, json.JSONDecodeError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"detail": "invalid JSON"})
            return

        if payload.get("task_id") != match.group(1):
            self._send_json(HTTPStatus.CONFLICT, {"detail": "task mismatch"})
            return

        print(
            json.dumps(
                {"event": "fake_worker_output_received", "payload": payload},
                sort_keys=True,
            ),
            flush=True,
        )
        self._send_json(HTTPStatus.ACCEPTED, {"accepted": True})

    def log_message(self, format: str, *args: Any) -> None:
        print(
            json.dumps(
                {
                    "event": "http_access",
                    "client": self.client_address[0],
                    "message": format % args,
                },
                sort_keys=True,
            ),
            flush=True,
        )

    def _is_authorized(self) -> bool:
        expected = os.environ.get("STUB_TASK_TOKEN", "local-demo-task-token")
        return self.headers.get("Authorization") == f"Bearer {expected}"

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 8000), StubHandler)
    print('{"event":"control_api_stub_started","port":8000}', flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
