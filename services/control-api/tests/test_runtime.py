"""Testes do contrato de runtime. Não tocam banco nem Docker."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.runtime.base import (
    ContainerMount,
    ContainerSpec,
    ForbiddenEnvironment,
    ImageNotAllowed,
    InvalidMount,
    ResourceLimits,
    validate_worker_mounts,
    worker_mounts,
)
from app.runtime.docker_runtime import DockerContainerRuntime
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


def test_dev_mount_policy_exposes_only_writable_workspace(tmp_path):
    mounts = worker_mounts("dev", workspace=tmp_path / "workspace")

    assert mounts == (
        ContainerMount(
            source=str(tmp_path / "workspace"),
            target="/workspace",
            read_only=False,
        ),
    )


def test_qa_mount_policy_keeps_code_read_only_and_tests_writable(tmp_path):
    mounts = worker_mounts(
        "qa", workspace=tmp_path / "workspace", tests=tmp_path / "tests"
    )

    assert [(mount.target, mount.read_only) for mount in mounts] == [
        ("/workspace", True),
        ("/tests", False),
    ]


def test_worker_mount_policy_rejects_permission_inversion(tmp_path):
    mounts = (
        ContainerMount(str(tmp_path / "workspace"), "/workspace", False),
        ContainerMount(str(tmp_path / "tests"), "/tests", False),
    )

    with pytest.raises(InvalidMount, match="QA requer"):
        validate_worker_mounts("qa", mounts)


def test_container_spec_rejects_duplicate_mount_targets(tmp_path):
    mounts = (
        ContainerMount(str(tmp_path / "a" / "workspace"), "/workspace", True),
        ContainerMount(str(tmp_path / "b" / "workspace"), "/workspace", False),
    )

    with pytest.raises(InvalidMount, match="destinos"):
        _spec(mounts=mounts)


def test_container_spec_confines_working_dir_to_declared_mount(tmp_path):
    mount = ContainerMount(str(tmp_path / "workspace"), "/workspace", False)

    spec = _spec(mounts=(mount,), working_dir="/workspace/app")
    assert spec.working_dir == "/workspace/app"

    with pytest.raises(InvalidMount, match="mount declarado"):
        _spec(mounts=(mount,), working_dir="/tests")


def test_mount_refuses_host_root_and_mismatched_source_name(tmp_path):
    with pytest.raises(InvalidMount, match="raiz do host"):
        ContainerMount("/", "/workspace", False)
    with pytest.raises(InvalidMount, match="precisa terminar"):
        ContainerMount(str(tmp_path / "other"), "/workspace", False)


class _CreatedContainer:
    id = "docker-container-id"


class _Containers:
    def __init__(self) -> None:
        self.create_kwargs = None

    def create(self, **kwargs):
        self.create_kwargs = kwargs
        return _CreatedContainer()


class _DockerClient:
    def __init__(self) -> None:
        self.containers = _Containers()


async def test_docker_runtime_translates_mounts_user_and_workdir(tmp_path):
    client = _DockerClient()
    runtime = DockerContainerRuntime(client, frozenset({IMAGE}))
    mounts = worker_mounts(
        "qa", workspace=tmp_path / "workspace", tests=tmp_path / "tests"
    )

    await runtime.create(
        _spec(mounts=mounts, user="12000:12000", working_dir="/tests")
    )

    assert client.containers.create_kwargs["volumes"] == {
        str(tmp_path / "workspace"): {"bind": "/workspace", "mode": "ro"},
        str(tmp_path / "tests"): {"bind": "/tests", "mode": "rw"},
    }
    assert client.containers.create_kwargs["user"] == "12000:12000"
    assert client.containers.create_kwargs["working_dir"] == "/tests"


async def test_docker_runtime_translates_control_api_volume_path_for_daemon(tmp_path):
    client = _DockerClient()
    container_root = Path("/var/lib/rivexx/workspaces")
    daemon_root = Path("/var/lib/docker/volumes/rivexx-squad_run_workspaces/_data")
    runtime = DockerContainerRuntime(
        client,
        frozenset({IMAGE}),
        mount_translations={container_root: daemon_root},
    )
    workspace = container_root / "runs/run-1/task-1/r1/workspace"

    await runtime.create(
        _spec(mounts=worker_mounts("dev", workspace=workspace))
    )

    assert client.containers.create_kwargs["volumes"] == {
        str(daemon_root / "runs/run-1/task-1/r1/workspace"): {
            "bind": "/workspace",
            "mode": "rw",
        }
    }


async def test_containerized_runtime_refuses_source_outside_its_volumes(tmp_path):
    client = _DockerClient()
    runtime = DockerContainerRuntime(
        client,
        frozenset({IMAGE}),
        mount_translations={
            "/var/lib/rivexx/workspaces": "/var/lib/docker/volumes/workspaces/_data"
        },
        require_translated_mounts=True,
    )

    with pytest.raises(InvalidMount, match="não pertence"):
        await runtime.create(
            _spec(
                mounts=worker_mounts(
                    "dev", workspace=tmp_path / "unmanaged" / "workspace"
                )
            )
        )


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
