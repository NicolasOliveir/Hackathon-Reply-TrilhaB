"""Testes focados do executor sem shell e do confinamento de cwd."""

from __future__ import annotations

import os

import pytest

from app.runtime.tools import (
    CommandNotAllowed,
    ExecutionRequest,
    ToolExecutor,
    WorkingDirectoryNotAllowed,
)


def _executor(workspace, **overrides) -> ToolExecutor:
    options = {
        "workspace_root": workspace,
        "command_allowlist": {"python": {"python3"}},
        "base_environment": {"PATH": os.environ["PATH"]},
    }
    options.update(overrides)
    return ToolExecutor(**options)


async def test_executes_argv_without_shell_expansion(tmp_path):
    marker = tmp_path / "shell-expanded"
    executor = _executor(tmp_path)
    request = ExecutionRequest(
        argv=(
            "python3",
            "-c",
            "import sys; print(sys.argv[1])",
            f"$(touch {marker})",
        ),
        cwd="/workspace",
        timeout_seconds=5,
        profile="python",
    )

    result = await executor.execute(request)

    assert result.succeeded
    assert result.stdout.strip() == f"$(touch {marker})"
    assert not marker.exists()


async def test_rejects_command_outside_profile_allowlist(tmp_path):
    executor = _executor(tmp_path)
    request = ExecutionRequest(
        argv=("sh", "-c", "true"),
        cwd="/workspace",
        timeout_seconds=5,
        profile="python",
    )

    with pytest.raises(CommandNotAllowed, match="não permitido"):
        await executor.execute(request)


async def test_rejects_virtual_path_traversal(tmp_path):
    executor = _executor(tmp_path)
    request = ExecutionRequest(
        argv=("python3", "--version"),
        cwd="/workspace/../outside",
        timeout_seconds=5,
        profile="python",
    )

    with pytest.raises(WorkingDirectoryNotAllowed, match="traversal"):
        await executor.execute(request)


async def test_rejects_cwd_that_escapes_through_symlink(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / "escape").symlink_to(outside, target_is_directory=True)
    executor = _executor(tmp_path)
    request = ExecutionRequest(
        argv=("python3", "--version"),
        cwd="/workspace/escape",
        timeout_seconds=5,
        profile="python",
    )

    with pytest.raises(WorkingDirectoryNotAllowed, match="resolve fora"):
        await executor.execute(request)


async def test_enforces_combined_output_limit(tmp_path):
    executor = _executor(tmp_path, output_limit_bytes=32)
    request = ExecutionRequest(
        argv=(
            "python3",
            "-c",
            "import sys; sys.stdout.write('a'*80); sys.stderr.write('b'*80)",
        ),
        cwd="/workspace",
        timeout_seconds=5,
        profile="python",
    )

    result = await executor.execute(request)

    assert result.succeeded
    assert result.output_truncated
    assert len(result.stdout.encode()) + len(result.stderr.encode()) <= 32


async def test_kills_process_on_timeout(tmp_path):
    executor = _executor(tmp_path)
    request = ExecutionRequest(
        argv=("python3", "-c", "import time; time.sleep(5)"),
        cwd="/workspace",
        timeout_seconds=1,
        profile="python",
    )

    result = await executor.execute(request)

    assert result.timed_out
    assert result.exit_code is None
    assert not result.succeeded


async def test_maps_tests_virtual_root_independently(tmp_path):
    workspace = tmp_path / "workspace"
    tests = tmp_path / "tests"
    workspace.mkdir()
    tests.mkdir()
    executor = ToolExecutor(
        workspace_root=workspace,
        tests_root=tests,
        command_allowlist={"python": {"python3"}},
        base_environment={"PATH": os.environ["PATH"]},
    )
    request = ExecutionRequest(
        argv=("python3", "-c", "import pathlib; print(pathlib.Path.cwd().name)"),
        cwd="/tests",
        timeout_seconds=5,
        profile="python",
    )

    result = await executor.execute(request)

    assert result.succeeded
    assert result.stdout.strip() == "tests"
