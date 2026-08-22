from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID


CONTRACT_VERSION = "1.0.0"


class ApiError(RuntimeError):
    """Falha sanitizada ao conversar com o plano de controle."""


@dataclass(frozen=True)
class Settings:
    run_id: str
    task_id: str
    api_url: str
    token: str
    workspace: Path
    schema_dir: Path
    revision: int = 1

    @classmethod
    def from_env(cls) -> "Settings":
        forbidden = [key for key in ("DATABASE_URL", "DOCKER_HOST") if os.getenv(key)]
        if forbidden:
            raise ValueError("Dev worker recebeu variável proibida: " + ", ".join(forbidden))
        required = ("RUN_ID", "TASK_ID", "CONTROL_API_URL", "TASK_TOKEN")
        missing = [key for key in required if not os.getenv(key)]
        if missing:
            raise ValueError("variáveis ausentes: " + ", ".join(missing))
        revision = int(os.getenv("REVISION", "1"))
        if revision < 1:
            raise ValueError("REVISION deve ser maior ou igual a 1")
        workspace = Path(os.getenv("WORKSPACE_ROOT", "/workspace"))
        if not workspace.is_absolute():
            raise ValueError("WORKSPACE_ROOT deve ser absoluto")
        return cls(
            run_id=str(UUID(os.environ["RUN_ID"])),
            task_id=str(UUID(os.environ["TASK_ID"])),
            api_url=os.environ["CONTROL_API_URL"].rstrip("/"),
            token=os.environ["TASK_TOKEN"],
            workspace=workspace,
            schema_dir=Path(os.getenv("CONTRACTS_DIR", "/app/contracts")),
            revision=revision,
        )


class Api:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def call(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        **headers: str,
    ) -> dict[str, Any]:
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
        try:
            with urlopen(request, timeout=300) as response:  # noqa: S310 - URL vem do runtime
                raw = response.read()
        except HTTPError as exc:
            raise ApiError(f"control-api respondeu HTTP {exc.code} em {path}") from exc
        except URLError as exc:
            raise ApiError(f"control-api indisponível em {path}: {exc.reason}") from exc
        value = json.loads(raw) if raw else {}
        if not isinstance(value, dict):
            raise ApiError(f"control-api retornou corpo não-objeto em {path}")
        return value

    def context(self) -> dict[str, Any]:
        return self.call("GET", f"/internal/v1/tasks/{self.settings.task_id}/context")

    def heartbeat(self) -> None:
        self.call("POST", f"/internal/v1/tasks/{self.settings.task_id}/heartbeat", {})

    def invoke(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.call(
            "POST", f"/internal/v1/tasks/{self.settings.task_id}/model-invocations", request
        )

    def upload_artifact(
        self,
        *,
        path: str,
        kind: str,
        media_type: str,
        content: bytes,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.call(
            "POST",
            f"/internal/v1/tasks/{self.settings.task_id}/artifacts",
            {
                "contract_version": CONTRACT_VERSION,
                "path": path,
                "kind": kind,
                "media_type": media_type,
                "content_base64": base64.b64encode(content).decode("ascii"),
                "attributes": attributes or {},
            },
        )

    def submit(self, delivery: dict[str, Any]) -> dict[str, Any]:
        digest = hashlib.sha256(
            json.dumps(delivery, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return self.call(
            "POST",
            f"/internal/v1/tasks/{self.settings.task_id}/dev-delivery",
            delivery,
            **{"Idempotency-Key": f"dev-{self.settings.task_id}-{digest}"},
        )

    def report_failure(
        self,
        *,
        category: str,
        message: str,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.call(
            "POST",
            f"/internal/v1/tasks/{self.settings.task_id}/failure",
            {
                "category": category[:80],
                "message": message[:4000],
                "retryable": retryable,
                "details": details or {},
            },
        )
