"""Snapshots e workspaces isolados dos workers Dev, QA e runner."""

from .manager import (
    InvalidWorkspaceRole,
    Mount,
    SnapshotIntegrityError,
    UnsafeWorkspacePath,
    Workspace,
    WorkspaceConflict,
    WorkspaceError,
    WorkspaceManager,
    WorkspaceSnapshot,
)

__all__ = [
    "InvalidWorkspaceRole",
    "Mount",
    "SnapshotIntegrityError",
    "UnsafeWorkspacePath",
    "Workspace",
    "WorkspaceConflict",
    "WorkspaceError",
    "WorkspaceManager",
    "WorkspaceSnapshot",
]
