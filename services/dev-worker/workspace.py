from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path, PurePosixPath
from typing import Any

from contracts import ContractError, validate_relative_path


class WorkspaceError(ValueError):
    """Uma alteração tentaria escapar ou corromper o workspace."""


class WorkspaceGuard:
    def __init__(self, root: Path) -> None:
        requested = root.absolute()
        if requested.is_symlink() or not requested.is_dir():
            raise WorkspaceError(f"workspace ausente ou simbólico: {requested}")
        self.root = requested.resolve(strict=True)

    def resolve(self, raw: str, *, must_exist: bool = False) -> Path:
        try:
            logical = PurePosixPath(validate_relative_path(raw))
        except ContractError as exc:
            raise WorkspaceError(str(exc)) from exc
        current = self.root
        for component in logical.parts:
            current /= component
            if current.is_symlink():
                raise WorkspaceError(f"link simbólico não permitido: {raw}")
        try:
            current.relative_to(self.root)
        except ValueError as exc:  # defesa adicional contra mudanças concorrentes
            raise WorkspaceError(f"caminho fora do workspace: {raw}") from exc
        if must_exist and not current.exists():
            raise WorkspaceError(f"arquivo para remoção não existe: {raw}")
        return current

    def validate_changes(self, changes: list[dict[str, Any]]) -> None:
        for change in changes:
            target = self.resolve(change["path"], must_exist=change["operation"] == "delete")
            if change["operation"] == "delete" and not target.is_file():
                raise WorkspaceError(f"remoção aceita somente arquivo regular: {change['path']}")
            if change["operation"] == "write" and target.exists() and not target.is_file():
                raise WorkspaceError(f"escrita aceita somente arquivo regular: {change['path']}")

    def apply(self, changes: list[dict[str, Any]]) -> list[str]:
        self.validate_changes(changes)
        changed: list[str] = []
        for change in changes:
            logical = validate_relative_path(change["path"])
            target = self.resolve(logical, must_exist=change["operation"] == "delete")
            if change["operation"] == "delete":
                target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                # Revalida após mkdir para reduzir a janela de troca por symlink.
                target = self.resolve(logical)
                target.write_text(change["content"], encoding="utf-8")
            changed.append(logical)
        return changed

    def manifest(self, paths: list[str]) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for logical in sorted(set(paths)):
            target = self.resolve(logical)
            if not target.exists():
                entries.append({"path": logical, "state": "deleted"})
                continue
            info = target.stat()
            if not stat.S_ISREG(info.st_mode):
                raise WorkspaceError(f"manifesto aceita somente arquivo regular: {logical}")
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            entries.append(
                {
                    "path": logical,
                    "state": "present",
                    "size_bytes": info.st_size,
                    "sha256": f"sha256:{digest}",
                    "executable": bool(info.st_mode & os.X_OK),
                }
            )
        return entries


_EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "vendor",
}
_SECRET_NAMES = {".env", ".env.local", "credentials.json", "secrets.json"}


def repository_excerpt(
    guard: WorkspaceGuard,
    *,
    max_files: int = 100,
    max_file_bytes: int = 50_000,
    max_total_bytes: int = 300_000,
) -> dict[str, Any]:
    """Contexto de código limitado, textual e sem arquivos tipicamente secretos."""

    inventory: list[str] = []
    files: list[dict[str, str]] = []
    used = 0
    candidates: list[Path] = []
    for current, directories, names in os.walk(guard.root, followlinks=False):
        directories[:] = sorted(name for name in directories if name not in _EXCLUDED_PARTS)
        for name in sorted(names):
            path = Path(current) / name
            relative = path.relative_to(guard.root).as_posix()
            if name in _SECRET_NAMES or name.endswith((".pem", ".key", ".p12")):
                continue
            if path.is_symlink() or not path.is_file():
                continue
            inventory.append(relative)
            if path.stat().st_size <= max_file_bytes:
                candidates.append(path)
    for path in candidates[:max_files]:
        raw = path.read_bytes()
        if b"\x00" in raw:
            continue
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        size = len(raw)
        if used + size > max_total_bytes:
            break
        files.append({"path": path.relative_to(guard.root).as_posix(), "content": content})
        used += size
    return {"inventory": inventory[:1000], "files": files, "truncated": len(candidates) > len(files)}
