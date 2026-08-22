"""Testes de contrato que não dependem de banco.

Garantem que a serialização da API e a rota exposta batem com
`packages/contracts`, mesmo quando não há PostgreSQL no ambiente.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.api.runs.router import _serialize, _to_response
from app.config import Settings, get_settings
from app.persistence.models import Run

RUN_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
TASK_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")


@pytest.fixture(scope="module")
def settings(_environment: None) -> Settings:
    """Usa as settings reais do ambiente de teste.

    Construir `Settings` campo a campo aqui obrigaria a atualizar este teste a
    cada configuração nova — e a quebra apareceria como erro de fixture, não
    como falha de contrato.
    """
    return get_settings()


def _run(state: str = "WORKER_QUEUED", task_id: uuid.UUID | None = TASK_ID) -> Run:
    moment = datetime(2026, 8, 22, 16, 0, tzinfo=timezone.utc)
    return Run(
        run_id=RUN_ID,
        state=state,
        briefing="Centralizar não conformidades e rastrear lotes.",
        briefing_hash="sha256:" + "0" * 64,
        client_reference="rivexx-demo-001",
        current_task_id=task_id,
        last_sequence=3,
        created_at=moment,
        updated_at=moment,
    )


def test_run_response_matches_the_versioned_schema(settings, schema_validator):
    body = _serialize(_to_response(_run(), settings))
    schema_validator("run-response.schema.json", body)


def test_run_response_without_task_is_valid(settings, schema_validator):
    body = _serialize(_to_response(_run(state="RECEIVED", task_id=None), settings))
    schema_validator("run-response.schema.json", body)
    assert body["current_task_id"] is None


def test_links_point_to_the_contracted_routes(settings):
    body = _serialize(_to_response(_run(), settings))
    assert body["links"]["self"] == f"http://localhost:8000/api/v1/runs/{RUN_ID}"
    assert body["links"]["events"] == (
        f"http://localhost:8000/api/v1/runs/{RUN_ID}/events"
    )


def test_exposed_routes_and_status_codes_match_the_openapi_contract(settings):
    from app.main import create_app

    spec = create_app().openapi()

    assert set(spec["paths"]["/api/v1/runs"]["post"]["responses"]) >= {"202", "409"}
    assert set(spec["paths"]["/api/v1/runs/{run_id}"]["get"]["responses"]) >= {
        "200",
        "404",
    }


def test_generated_models_accept_the_contract_examples():
    """Detecta modelos gerados desatualizados em relação aos schemas.

    Se alguém alterar um schema em `packages/contracts` sem rodar
    `make contracts-codegen`, os exemplos válidos deixam de casar com os
    modelos e este teste falha — em vez de a divergência aparecer só em runtime.
    """
    import json
    from pathlib import Path

    from app.contracts.v1.create_run_request_schema import CreateRunRequest
    from app.contracts.v1.event_envelope_schema import EventEnvelope
    from app.contracts.v1.run_response_schema import RunResponse

    examples = (
        Path(__file__).resolve().parents[3]
        / "packages"
        / "contracts"
        / "examples"
        / "v1"
    )
    cases = {
        "create-run-request.json": CreateRunRequest,
        "run-response.json": RunResponse,
        "event-envelope.json": EventEnvelope,
    }

    for filename, model in cases.items():
        payload = json.loads((examples / "valid" / filename).read_text("utf-8"))
        parsed = model.model_validate(payload)
        assert parsed.model_dump(mode="json", exclude_none=False) == payload


def test_generated_models_reject_the_invalid_examples():
    import json
    from pathlib import Path

    from pydantic import ValidationError

    from app.contracts.v1.create_run_request_schema import CreateRunRequest
    from app.contracts.v1.event_envelope_schema import EventEnvelope
    from app.contracts.v1.run_response_schema import RunResponse

    examples = (
        Path(__file__).resolve().parents[3]
        / "packages"
        / "contracts"
        / "examples"
        / "v1"
    )
    cases = {
        "create-run-request-short.json": CreateRunRequest,
        "run-response-state.json": RunResponse,
        "event-envelope-sequence.json": EventEnvelope,
    }

    for filename, model in cases.items():
        payload = json.loads((examples / "invalid" / filename).read_text("utf-8"))
        with pytest.raises(ValidationError):
            model.model_validate(payload)


def test_idempotency_hash_ignores_key_order():
    from app.persistence.idempotency import hash_request

    first = hash_request({"contract_version": "1.0.0", "briefing": "abc"})
    second = hash_request({"briefing": "abc", "contract_version": "1.0.0"})
    assert first == second


def test_idempotency_hash_changes_with_content():
    from app.persistence.idempotency import hash_request

    assert hash_request({"briefing": "a"}) != hash_request({"briefing": "b"})
