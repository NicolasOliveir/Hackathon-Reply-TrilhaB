"""Testes do contrato de runtime. Não tocam banco nem Docker."""

from __future__ import annotations

import pytest

from app.runtime.base import (
    ContainerSpec,
    ForbiddenEnvironment,
    ImageNotAllowed,
    ResourceLimits,
)
from app.runtime.fake_runtime import FakeContainerRuntime

IMAGE = "rivexx/fake-worker:local"


def _spec(**overrides) -> ContainerSpec:
    base = {
        "image": IMAGE,
        "environment": {
            "RUN_ID": "11111111-1111-4111-8111-111111111111",
            "TASK_ID": "22222222-2222-4222-8222-222222222222",
            "CONTROL_API_URL": "http://control-api:8000",
            "TASK_TOKEN": "token",
        },
        "network": "rivexx-squad_agent_net",
    }
    base.update(overrides)
    return ContainerSpec(**base)


@pytest.mark.parametrize(
    "leaked", ["DATABASE_URL", "DOCKER_HOST", "POSTGRES_PASSWORD"]
)
def test_spec_refuses_control_plane_credentials(leaked: str):
    """O vazamento vira exceção na montagem, não achado de revisão."""
    environment = dict(_spec().environment)
    environment[leaked] = "qualquer-valor"

    with pytest.raises(ForbiddenEnvironment) as error:
        _spec(environment=environment)

    assert leaked in str(error.value)


def test_spec_accepts_only_the_four_worker_variables():
    spec = _spec()
    assert set(spec.environment) == {
        "RUN_ID",
        "TASK_ID",
        "CONTROL_API_URL",
        "TASK_TOKEN",
    }


def test_spec_is_read_only_and_limited_by_default():
    spec = _spec()
    assert spec.read_only is True
    assert spec.limits == ResourceLimits(memory="128m", cpus=0.5, pids=64)


async def test_fake_runtime_refuses_image_outside_allowlist():
    runtime = FakeContainerRuntime(allowed_images=frozenset({"outra:tag"}))
    with pytest.raises(ImageNotAllowed):
        await runtime.create(_spec())


async def test_fake_runtime_lifecycle_records_every_step():
    runtime = FakeContainerRuntime(allowed_images=frozenset({IMAGE}))

    handle = await runtime.create(_spec())
    assert runtime.created_count == 1
    assert runtime.started_count == 0

    await runtime.start(handle)
    assert runtime.started_count == 1

    result = await runtime.wait(handle, timeout_seconds=5)
    assert result.succeeded
    assert result.exit_code == 0

    await runtime.remove(handle)
    assert runtime.removed_count == 1


async def test_container_id_exists_before_start():
    """`AGENT_STARTED` é gravado entre create e start; sem id não há evento."""
    runtime = FakeContainerRuntime(allowed_images=frozenset({IMAGE}))
    handle = await runtime.create(_spec())
    assert handle.container_id
    assert runtime.started_count == 0


async def test_non_zero_exit_is_not_success():
    runtime = FakeContainerRuntime(allowed_images=frozenset({IMAGE}), exit_code=2)
    handle = await runtime.create(_spec())
    result = await runtime.wait(handle, timeout_seconds=5)
    assert not result.succeeded
    assert result.exit_code == 2


async def test_timeout_is_not_success_even_without_exit_code():
    runtime = FakeContainerRuntime(allowed_images=frozenset({IMAGE}), timed_out=True)
    handle = await runtime.create(_spec())
    result = await runtime.wait(handle, timeout_seconds=1)
    assert result.timed_out
    assert result.exit_code is None
    assert not result.succeeded


def test_token_hash_never_matches_a_wrong_token():
    from app.orchestration import tokens

    issued = tokens.issue()
    assert tokens.matches(issued.plaintext, issued.hashed)
    assert not tokens.matches("outro-token", issued.hashed)
    assert not tokens.matches("", issued.hashed)
    assert not tokens.matches(issued.plaintext, None)


def test_token_hash_does_not_contain_the_plaintext():
    from app.orchestration import tokens

    issued = tokens.issue()
    assert issued.plaintext not in issued.hashed
    assert issued.hashed.startswith("sha256:")


def test_fake_worker_scopes_exclude_model_invocation():
    """O fake worker não fala com LLM; escopo não usado é superfície gratuita."""
    from app.orchestration import tokens

    assert "model:invoke" not in tokens.FAKE_WORKER_SCOPES
    assert {"context:read", "output:write"}.issubset(tokens.FAKE_WORKER_SCOPES)
