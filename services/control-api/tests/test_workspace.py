"""Testes unitários dos snapshots, workspaces e políticas de mount."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from app.workspace import (
    SnapshotIntegrityError,
    UnsafeWorkspacePath,
    WorkspaceConflict,
    WorkspaceManager,
)
from app.runtime.base import ContainerMount, validate_worker_mounts


def _scaffold(root: Path, content: str = "clean scaffold") -> Path:
    source = root / f"source-{content.replace(' ', '-')}"
    (source / "src").mkdir(parents=True)
    (source / "src" / "app.py").write_text(content, encoding="utf-8")
    (source / "README.md").write_text("Rivexx", encoding="utf-8")
    return source


def test_snapshot_is_content_addressed_immutable_and_idempotent(tmp_path: Path):
    manager = WorkspaceManager(tmp_path / "managed")
    source = _scaffold(tmp_path)

    first = manager.create_snapshot(source)
    second = manager.create_snapshot(source)

    assert second == first
    assert first.sha256 == f"sha256:{first.snapshot_id}"
    assert len(first.snapshot_id) == 64
    assert (first.path / "src" / "app.py").read_text() == "clean scaffold"
    assert not ((first.path / "src" / "app.py").stat().st_mode & stat.S_IWUSR)


def test_workspace_is_scoped_by_run_task_revision_and_retry_preserves_changes(
    tmp_path: Path,
):
    manager = WorkspaceManager(tmp_path / "managed")
    snapshot = manager.create_snapshot(_scaffold(tmp_path))

    workspace = manager.create_workspace(
        snapshot, run_id="run-001", task_id="task-001", revision=1
    )
    (workspace.code_path / "src" / "app.py").write_text("dev change", encoding="utf-8")
    retried = manager.create_workspace(
        snapshot, run_id="run-001", task_id="task-001", revision=1
    )

    assert retried.path == workspace.path
    assert retried.path.relative_to(manager.runs_root).as_posix() == "run-001/task-001/r1"
    assert (retried.code_path / "src" / "app.py").read_text() == "dev change"
    assert (snapshot.path / "src" / "app.py").read_text() == "clean scaffold"


def test_mounts_separate_dev_qa_and_runner_permissions(tmp_path: Path):
    manager = WorkspaceManager(tmp_path / "managed")
    snapshot = manager.create_snapshot(_scaffold(tmp_path))
    workspace = manager.create_workspace(
        snapshot, run_id="run-001", task_id="task-001", revision=2
    )

    assert [(mount.target, mount.read_only) for mount in workspace.dev_mounts] == [
        ("/workspace", False)
    ]
    assert [(mount.target, mount.read_only) for mount in workspace.qa_mounts] == [
        ("/workspace", True),
        ("/tests", False),
    ]
    assert [(mount.target, mount.read_only) for mount in workspace.runner_mounts] == [
        ("/workspace", True),
        ("/tests", True),
    ]
    assert all(isinstance(mount, ContainerMount) for mount in workspace.qa_mounts)
    validate_worker_mounts("dev", workspace.dev_mounts)
    validate_worker_mounts("qa", workspace.qa_mounts)


def test_workspace_is_owned_by_the_non_root_worker_when_control_api_is_root(
    tmp_path: Path,
):
    manager = WorkspaceManager(tmp_path / "managed")
    snapshot = manager.create_snapshot(_scaffold(tmp_path))
    workspace = manager.create_workspace(
        snapshot, run_id="run-001", task_id="task-001", revision=1
    )

    expected_uid = 10001 if os.geteuid() == 0 else os.geteuid()
    expected_gid = 10001 if os.geteuid() == 0 else os.getegid()
    assert workspace.code_path.stat().st_uid == expected_uid
    assert workspace.code_path.stat().st_gid == expected_gid
    assert workspace.tests_path.stat().st_uid == expected_uid
    assert workspace.tests_path.stat().st_gid == expected_gid
    assert workspace.code_path.stat().st_mode & stat.S_IWUSR
    assert workspace.tests_path.stat().st_mode & stat.S_IWUSR


@pytest.mark.parametrize(
    ("run_id", "task_id"),
    [
        ("../run", "task"),
        ("run/child", "task"),
        ("run", "../../task"),
        ("run", "/absolute"),
    ],
)
def test_workspace_identity_rejects_traversal(
    tmp_path: Path, run_id: str, task_id: str
):
    manager = WorkspaceManager(tmp_path / "managed")
    snapshot = manager.create_snapshot(_scaffold(tmp_path))

    with pytest.raises(UnsafeWorkspacePath):
        manager.create_workspace(
            snapshot, run_id=run_id, task_id=task_id, revision=1
        )


def test_workspace_path_resolution_rejects_traversal_and_symlinks(tmp_path: Path):
    manager = WorkspaceManager(tmp_path / "managed")
    snapshot = manager.create_snapshot(_scaffold(tmp_path))
    workspace = manager.create_workspace(
        snapshot, run_id="run-001", task_id="task-001", revision=1
    )

    with pytest.raises(UnsafeWorkspacePath):
        workspace.resolve_code_path("../../outside")

    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace.code_path / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafeWorkspacePath):
        workspace.resolve_code_path("escape/file.txt")
    with pytest.raises(UnsafeWorkspacePath):
        manager.create_workspace(
            snapshot, run_id="run-001", task_id="task-001", revision=1
        )


def test_snapshot_rejects_symlinks_even_when_target_is_inside_source(tmp_path: Path):
    manager = WorkspaceManager(tmp_path / "managed")
    source = _scaffold(tmp_path)
    (source / "alias.py").symlink_to(source / "src" / "app.py")

    with pytest.raises(UnsafeWorkspacePath):
        manager.create_snapshot(source)


def test_workspace_key_cannot_be_reused_with_another_snapshot(tmp_path: Path):
    manager = WorkspaceManager(tmp_path / "managed")
    first = manager.create_snapshot(_scaffold(tmp_path, "first"))
    second = manager.create_snapshot(_scaffold(tmp_path, "second"))
    manager.create_workspace(first, run_id="run-001", task_id="task-001", revision=1)

    with pytest.raises(WorkspaceConflict):
        manager.create_workspace(
            second, run_id="run-001", task_id="task-001", revision=1
        )


def test_detects_snapshot_tampering_before_creating_workspace(tmp_path: Path):
    manager = WorkspaceManager(tmp_path / "managed")
    snapshot = manager.create_snapshot(_scaffold(tmp_path))
    changed = snapshot.path / "src" / "app.py"
    changed.chmod(0o600)
    changed.write_text("tampered", encoding="utf-8")

    with pytest.raises(SnapshotIntegrityError):
        manager.create_workspace(
            snapshot, run_id="run-001", task_id="task-001", revision=1
        )
