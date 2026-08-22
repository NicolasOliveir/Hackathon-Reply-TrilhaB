from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import UUID


CONTRACT_VERSION = "1.0.0"
REQUIRED_ENV = ("RUN_ID", "TASK_ID", "CONTROL_API_URL", "TASK_TOKEN")
FORBIDDEN_ENV = ("DATABASE_URL", "DOCKER_HOST")


@dataclass(frozen=True)
class Settings:
    run_id: str
    task_id: str
    api_url: str
    task_token: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Settings:
        forbidden = [name for name in FORBIDDEN_ENV if environ.get(name)]
        if forbidden:
            raise ValueError(f"forbidden worker environment: {', '.join(forbidden)}")

        missing = [name for name in REQUIRED_ENV if not environ.get(name)]
        if missing:
            raise ValueError(f"missing worker environment: {', '.join(missing)}")

        run_id = str(UUID(environ["RUN_ID"]))
        task_id = str(UUID(environ["TASK_ID"]))
        api_url = environ["CONTROL_API_URL"].rstrip("/")
        parsed_url = urlparse(api_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("CONTROL_API_URL must be an absolute HTTP(S) URL")

        return cls(
            run_id=run_id,
            task_id=task_id,
            api_url=api_url,
            task_token=environ["TASK_TOKEN"],
        )


class ControlApiClient:
    def __init__(self, settings: Settings, timeout: float = 10.0) -> None:
        self.settings = settings
        self.timeout = timeout

    def get_context(self) -> dict[str, Any]:
        request = Request(
            f"{self.settings.api_url}/internal/v1/tasks/"
            f"{self.settings.task_id}/context",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.settings.task_token}",
            },
            method="GET",
        )
        return self._json_response(request)

    def submit_output(
        self, payload: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        request = Request(
            f"{self.settings.api_url}/internal/v1/tasks/"
            f"{self.settings.task_id}/outputs",
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.settings.task_token}",
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency_key,
            },
            method="POST",
        )
        return self._json_response(request)

    def _json_response(self, request: Request) -> dict[str, Any]:
        with urlopen(request, timeout=self.timeout) as response:  # noqa: S310
            body = response.read()
        if not body:
            return {}
        parsed = json.loads(body)
        if not isinstance(parsed, dict):
            raise ValueError("central API returned a non-object JSON document")
        return parsed


def canonical_hash(document: dict[str, Any]) -> str:
    encoded = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def validate_context(context: dict[str, Any], settings: Settings) -> None:
    if context.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("unsupported context contract_version")
    if context.get("run_id") != settings.run_id:
        raise ValueError("context run_id does not match worker RUN_ID")
    if context.get("task_id") != settings.task_id:
        raise ValueError("context task_id does not match worker TASK_ID")
    if context.get("role") != "fake":
        raise ValueError("context role is not fake")

    scopes = context.get("scopes")
    if not isinstance(scopes, list) or not {"context:read", "output:write"}.issubset(
        scopes
    ):
        raise ValueError("context is missing required scopes")


def execute(settings: Settings, now: datetime | None = None) -> dict[str, Any]:
    client = ControlApiClient(settings)
    context = client.get_context()
    validate_context(context, settings)
    context_hash = canonical_hash(context)
    emitted_at = (now or datetime.now(UTC)).astimezone(UTC)
    payload = {
        "contract_version": CONTRACT_VERSION,
        "task_id": settings.task_id,
        "run_id": settings.run_id,
        "status": "SUCCEEDED",
        "message": "Context received and callback submitted through the central API.",
        "received_context_hash": context_hash,
        "emitted_at": emitted_at.isoformat().replace("+00:00", "Z"),
    }
    idempotency_key = hashlib.sha256(
        f"{settings.task_id}:{context_hash}".encode("utf-8")
    ).hexdigest()
    client.submit_output(payload, idempotency_key)
    return payload


def main() -> int:
    try:
        settings = Settings.from_env(os.environ)
        payload = execute(settings)
    except Exception as error:  # worker boundary reports a non-zero exit without secrets
        print(f"fake-worker failed: {error}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "event": "fake_worker_completed",
                "run_id": payload["run_id"],
                "task_id": payload["task_id"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
