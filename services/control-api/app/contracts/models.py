"""Modelos Pydantic espelhando os JSON Schemas versionados em `packages/contracts`.

Estes modelos nao redefinem regra: a suite em `tests/test_contract_models.py` exige que
cada exemplo valido do contrato seja aceito e cada exemplo invalido seja rejeitado. Uma
divergencia entre este arquivo e o schema falha no CI.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = "1.0.0"

SHA256_PATTERN = r"^sha256:[a-f0-9]{64}$"


class RunState(str, Enum):
    RECEIVED = "RECEIVED"
    WORKER_QUEUED = "WORKER_QUEUED"
    WORKER_RUNNING = "WORKER_RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class TaskState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELED = "CANCELED"


class AgentRole(str, Enum):
    FAKE = "fake"
    PO = "po"
    DEV = "dev"
    QA = "qa"
    RUNNER = "runner"


class EventActor(str, Enum):
    SYSTEM = "system"
    FAKE_WORKER = "fake_worker"
    PO = "po"
    DEV = "dev"
    QA = "qa"
    RUNNER = "runner"


class EventType(str, Enum):
    RUN_CREATED = "RUN_CREATED"
    BRIEFING_RECEIVED = "BRIEFING_RECEIVED"
    TASK_QUEUED = "TASK_QUEUED"
    AGENT_STARTED = "AGENT_STARTED"
    FAKE_WORKER_COMPLETED = "FAKE_WORKER_COMPLETED"
    AGENT_FAILED = "AGENT_FAILED"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_FAILED = "RUN_FAILED"
    RUN_CANCELED = "RUN_CANCELED"


class Scope(str, Enum):
    CONTEXT_READ = "context:read"
    MODEL_INVOKE = "model:invoke"
    OUTPUT_WRITE = "output:write"
    HEARTBEAT_WRITE = "heartbeat:write"
    ARTIFACT_WRITE = "artifact:write"


class ContractModel(BaseModel):
    """Base fechada: `additionalProperties: false` em todos os schemas do contrato."""

    model_config = ConfigDict(extra="forbid", use_enum_values=False)


class CreateRunRequest(ContractModel):
    contract_version: Literal["1.0.0"]
    briefing: str = Field(min_length=20, max_length=100_000)
    client_reference: str | None = Field(default=None, min_length=1, max_length=120)


class RunLinks(ContractModel):
    self: str
    events: str


class RunResponse(ContractModel):
    contract_version: Literal["1.0.0"]
    run_id: UUID
    state: RunState
    created_at: datetime
    updated_at: datetime
    current_task_id: UUID | None
    links: RunLinks


class EventMeta(ContractModel):
    model: str | None
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    container_id: str | None


class EventEnvelope(ContractModel):
    contract_version: Literal["1.0.0"]
    event_id: UUID
    sequence: int = Field(ge=1)
    run_id: UUID
    ts: datetime
    actor: EventActor
    type: EventType
    correlation_id: str = Field(min_length=1, max_length=120)
    causation_id: UUID | None
    task_id: UUID | None
    payload: dict[str, Any]
    meta: EventMeta


class ContextManifestEntry(ContractModel):
    source_id: str = Field(min_length=1, max_length=120)
    source_type: Literal["briefing", "story", "delivery", "finding", "contract"]
    hash: str = Field(pattern=SHA256_PATTERN)


class AgentTaskContext(ContractModel):
    contract_version: Literal["1.0.0"]
    task_id: UUID
    run_id: UUID
    role: AgentRole
    issued_at: datetime
    expires_at: datetime
    scopes: list[Scope] = Field(min_length=1)
    context_manifest: list[ContextManifestEntry]
    input: dict[str, Any]


class FakeWorkerOutput(ContractModel):
    contract_version: Literal["1.0.0"]
    task_id: UUID
    run_id: UUID
    status: Literal["SUCCEEDED", "FAILED"]
    message: str = Field(min_length=1, max_length=2000)
    received_context_hash: str = Field(pattern=SHA256_PATTERN)
    emitted_at: datetime


#: Mapeia o `$id` de cada schema ao modelo correspondente. Usado pelo teste de contrato
#: para percorrer o manifesto de exemplos sem lista duplicada.
SCHEMA_ID_TO_MODEL: dict[str, type[ContractModel]] = {
    "https://reply.local/contracts/v1/create-run-request.schema.json": CreateRunRequest,
    "https://reply.local/contracts/v1/run-response.schema.json": RunResponse,
    "https://reply.local/contracts/v1/event-envelope.schema.json": EventEnvelope,
    "https://reply.local/contracts/v1/agent-task-context.schema.json": AgentTaskContext,
    "https://reply.local/contracts/v1/fake-worker-output.schema.json": FakeWorkerOutput,
}
