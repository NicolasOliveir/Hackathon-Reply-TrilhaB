"""Criação idempotente de snapshots imutáveis e workspaces por revisão."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from ..runtime.base import ContainerMount as Mount


class WorkspaceError(Exception):
    """Erro base do gerenciador de workspaces."""


class UnsafeWorkspacePath(WorkspaceError, ValueError):
    """Um identificador, caminho ou link não é seguro para montar."""


class SnapshotIntegrityError(WorkspaceError):
    """O snapshot imutável foi alterado ou está incompleto."""


class WorkspaceConflict(WorkspaceError):
    """A chave run/task/revision já pertence a outro snapshot."""


class InvalidWorkspaceRole(WorkspaceError, ValueError):
    """Papel não possui uma política de mounts definida."""


WorkerRole = Literal["dev", "qa", "runner"]
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
DEFAULT_WORKER_UID = 10001
DEFAULT_WORKER_GID = 10001


@dataclass(frozen=True)
class WorkspaceSnapshot:
    snapshot_id: str
    sha256: str
    path: Path


@dataclass(frozen=True)
class Workspace:
    run_id: str
    task_id: str
    revision: int
    snapshot: WorkspaceSnapshot
    path: Path
    code_path: Path
    tests_path: Path

    def mounts_for(self, role: WorkerRole | str) -> tuple[Mount, ...]:
        if role == "dev":
            return (Mount(self.code_path, "/workspace", read_only=False),)
        if role == "qa":
            return (
                Mount(self.code_path, "/workspace", read_only=True),
                Mount(self.tests_path, "/tests", read_only=False),
            )
        if role == "runner":
            return (
                Mount(self.code_path, "/workspace", read_only=True),
                Mount(self.tests_path, "/tests", read_only=True),
            )
        raise InvalidWorkspaceRole(f"papel sem política de mounts: {role!r}")

    @property
    def dev_mounts(self) -> tuple[Mount, ...]:
        return self.mounts_for("dev")

    @property
    def qa_mounts(self) -> tuple[Mount, ...]:
        return self.mounts_for("qa")

    @property
    def runner_mounts(self) -> tuple[Mount, ...]:
        return self.mounts_for("runner")

    def resolve_code_path(
        self, relative_path: str | PurePosixPath, *, must_exist: bool = False
    ) -> Path:
        return _resolve_confined(self.code_path, relative_path, must_exist=must_exist)

    def resolve_tests_path(
        self, relative_path: str | PurePosixPath, *, must_exist: bool = False
    ) -> Path:
        return _resolve_confined(self.tests_path, relative_path, must_exist=must_exist)


def _safe_component(value: str, field: str) -> str:
    if value in {".", ".."} or not _SAFE_COMPONENT.fullmatch(value):
        raise UnsafeWorkspacePath(f"{field} inválido para path: {value!r}")
    return value


def _normalise_relative(value: str | PurePosixPath) -> PurePosixPath:
    raw = str(value)
    if not raw or "\x00" in raw or "\\" in raw:
        raise UnsafeWorkspacePath(f"caminho relativo inválido: {raw!r}")
    path = PurePosixPath(raw)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise UnsafeWorkspacePath(f"caminho fora do workspace: {raw!r}")
    return path


def _reject_symlink_components(base: Path, candidate: Path) -> None:
    try:
        relative = candidate.relative_to(base)
    except ValueError as exc:
        raise UnsafeWorkspacePath(f"caminho fora da raiz permitida: {candidate}") from exc
    current = base
    if current.is_symlink():
        raise UnsafeWorkspacePath(f"raiz não pode ser link simbólico: {current}")
    for component in relative.parts:
        current /= component
        if current.is_symlink():
            raise UnsafeWorkspacePath(f"link simbólico não permitido: {current}")


def _resolve_confined(
    base: Path,
    relative_path: str | PurePosixPath,
    *,
    must_exist: bool,
) -> Path:
    logical = _normalise_relative(relative_path)
    target = base.joinpath(*logical.parts)
    _reject_symlink_components(base, target)
    if must_exist and not target.exists():
        raise FileNotFoundError(target)
    return target


def _tree_entries(root: Path) -> list[tuple[Path, os.stat_result]]:
    """Lista a árvore sem seguir links e rejeita devices, sockets e FIFOs."""

    if root.is_symlink():
        raise UnsafeWorkspacePath(f"fonte não pode ser link simbólico: {root}")
    if not root.is_dir():
        raise UnsafeWorkspacePath(f"fonte de snapshot deve ser diretório: {root}")

    entries: list[tuple[Path, os.stat_result]] = []
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in sorted(directory_names + file_names):
            path = current_path / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise UnsafeWorkspacePath(f"snapshot contém link simbólico: {path}")
            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise UnsafeWorkspacePath(f"snapshot contém arquivo especial: {path}")
            entries.append((path.relative_to(root), info))
    return sorted(entries, key=lambda item: item[0].as_posix())


def _hash_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for relative, info in _tree_entries(root):
        encoded = relative.as_posix().encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        if stat.S_ISDIR(info.st_mode):
            digest.update(b"D")
            continue
        digest.update(b"F")
        digest.update(b"X" if info.st_mode & 0o111 else b"-")
        with (root / relative).open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _make_read_only(root: Path) -> None:
    for path, info in reversed(_tree_entries(root)):
        absolute = root / path
        if stat.S_ISDIR(info.st_mode):
            absolute.chmod(info.st_mode & ~0o222)
        else:
            absolute.chmod(info.st_mode & ~0o222)
    root.chmod(root.stat().st_mode & ~0o222)


def _make_writable(root: Path) -> None:
    root.chmod(root.stat().st_mode | stat.S_IWUSR | stat.S_IXUSR)
    for relative, info in _tree_entries(root):
        path = root / relative
        if stat.S_ISDIR(info.st_mode):
            path.chmod(info.st_mode | stat.S_IWUSR | stat.S_IXUSR)
        else:
            path.chmod(info.st_mode | stat.S_IWUSR)


def _assign_owner(root: Path, uid: int, gid: int) -> None:
    """Entrega a árvore ao UID do worker quando o control-api roda como root.

    Em desenvolvimento local, o processo pode não ter permissão para chown;
    nesse caso ele já é o proprietário e os testes/ferramentas rodam sob o
    mesmo usuário. No container oficial o control-api é root e a troca para
    ``10001:10001`` é obrigatória antes do bind mount.
    """
    if not hasattr(os, "chown") or os.geteuid() != 0:
        return
    for relative, _ in _tree_entries(root):
        os.chown(root / relative, uid, gid)
    os.chown(root, uid, gid)


class WorkspaceManager:
    """Gerencia snapshots de scaffold e cópias mutáveis por revisão."""

    def __init__(
        self,
        root: str | Path,
        *,
        worker_uid: int = DEFAULT_WORKER_UID,
        worker_gid: int = DEFAULT_WORKER_GID,
    ) -> None:
        requested_root = Path(root).absolute()
        if requested_root.is_symlink():
            raise UnsafeWorkspacePath(
                f"raiz de workspaces não pode ser link: {requested_root}"
            )
        requested_root.mkdir(parents=True, exist_ok=True)
        self.root = requested_root.resolve(strict=True)
        self.worker_uid = worker_uid
        self.worker_gid = worker_gid
        self.snapshots_root = self.root / "snapshots"
        self.runs_root = self.root / "runs"
        for directory in (self.snapshots_root, self.runs_root):
            if directory.is_symlink():
                raise UnsafeWorkspacePath(f"diretório gerenciado é link: {directory}")
            directory.mkdir(exist_ok=True)

    def create_snapshot(self, source: str | Path) -> WorkspaceSnapshot:
        source_path = Path(source).absolute()
        tree_hash = _hash_tree(source_path)
        snapshot_id = tree_hash.removeprefix("sha256:")
        destination = self.snapshots_root / snapshot_id
        _reject_symlink_components(self.snapshots_root, destination)

        if destination.exists():
            return self._load_snapshot(snapshot_id)

        temporary = Path(tempfile.mkdtemp(prefix=".snapshot-", dir=self.snapshots_root))
        try:
            files_path = temporary / "files"
            shutil.copytree(source_path, files_path, symlinks=True)
            copied_hash = _hash_tree(files_path)
            if copied_hash != tree_hash:
                raise SnapshotIntegrityError("fonte mudou durante a criação do snapshot")
            (temporary / "snapshot.json").write_text(
                json.dumps(
                    {"version": 1, "snapshot_id": snapshot_id, "sha256": tree_hash},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            try:
                temporary.rename(destination)
            except FileExistsError:  # outro criador venceu a corrida idempotente
                shutil.rmtree(temporary)
                return self._load_snapshot(snapshot_id)
            _make_read_only(destination / "files")
            (destination / "snapshot.json").chmod(0o444)
            destination.chmod(destination.stat().st_mode & ~0o222)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary, ignore_errors=True)
        return self._load_snapshot(snapshot_id)

    def get_snapshot(self, snapshot_id: str) -> WorkspaceSnapshot:
        return self._load_snapshot(snapshot_id)

    def create_workspace(
        self,
        snapshot: WorkspaceSnapshot | str,
        *,
        run_id: str,
        task_id: str,
        revision: int,
    ) -> Workspace:
        run_component = _safe_component(str(run_id), "run_id")
        task_component = _safe_component(str(task_id), "task_id")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise UnsafeWorkspacePath("revision deve ser inteiro maior ou igual a 1")
        loaded_snapshot = self._coerce_snapshot(snapshot)

        task_root = self.runs_root / run_component / task_component
        destination = task_root / f"r{revision}"
        _reject_symlink_components(self.runs_root, destination)
        if destination.exists():
            return self._load_workspace(
                destination,
                run_id=run_component,
                task_id=task_component,
                revision=revision,
                expected_snapshot=loaded_snapshot,
            )

        task_root.mkdir(parents=True, exist_ok=True)
        _reject_symlink_components(self.runs_root, destination)
        temporary = Path(tempfile.mkdtemp(prefix=".workspace-", dir=task_root))
        try:
            code_path = temporary / "workspace"
            shutil.copytree(loaded_snapshot.path, code_path, symlinks=True)
            _make_writable(code_path)
            (temporary / "tests").mkdir(mode=0o700)
            _assign_owner(code_path, self.worker_uid, self.worker_gid)
            _assign_owner(
                temporary / "tests", self.worker_uid, self.worker_gid
            )
            (temporary / "workspace.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "run_id": run_component,
                        "task_id": task_component,
                        "revision": revision,
                        "snapshot_id": loaded_snapshot.snapshot_id,
                        "snapshot_sha256": loaded_snapshot.sha256,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            try:
                temporary.rename(destination)
            except FileExistsError:  # retry concorrente
                shutil.rmtree(temporary)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary, ignore_errors=True)
        return self._load_workspace(
            destination,
            run_id=run_component,
            task_id=task_component,
            revision=revision,
            expected_snapshot=loaded_snapshot,
        )

    def _coerce_snapshot(self, snapshot: WorkspaceSnapshot | str) -> WorkspaceSnapshot:
        if isinstance(snapshot, WorkspaceSnapshot):
            loaded = self._load_snapshot(snapshot.snapshot_id)
            if loaded.path != snapshot.path or loaded.sha256 != snapshot.sha256:
                raise SnapshotIntegrityError("snapshot não pertence a este manager")
            return loaded
        return self._load_snapshot(snapshot)

    def _load_snapshot(self, snapshot_id: str) -> WorkspaceSnapshot:
        component = _safe_component(str(snapshot_id), "snapshot_id")
        if not re.fullmatch(r"[a-f0-9]{64}", component):
            raise UnsafeWorkspacePath("snapshot_id deve ser um SHA-256 hexadecimal")
        directory = self.snapshots_root / component
        _reject_symlink_components(self.snapshots_root, directory / "files")
        marker = directory / "snapshot.json"
        _reject_symlink_components(self.snapshots_root, marker)
        if not marker.is_file() or not (directory / "files").is_dir():
            raise SnapshotIntegrityError(f"snapshot ausente ou incompleto: {component}")
        try:
            metadata = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SnapshotIntegrityError(f"manifesto inválido: {component}") from exc
        expected_hash = "sha256:" + component
        if (
            metadata.get("snapshot_id") != component
            or metadata.get("sha256") != expected_hash
        ):
            raise SnapshotIntegrityError(f"manifesto divergente: {component}")
        actual_hash = _hash_tree(directory / "files")
        if actual_hash != expected_hash:
            raise SnapshotIntegrityError(f"snapshot alterado: {component}")
        return WorkspaceSnapshot(
            snapshot_id=component,
            sha256=expected_hash,
            path=directory / "files",
        )

    def _load_workspace(
        self,
        directory: Path,
        *,
        run_id: str,
        task_id: str,
        revision: int,
        expected_snapshot: WorkspaceSnapshot,
    ) -> Workspace:
        _reject_symlink_components(self.runs_root, directory / "workspace")
        _reject_symlink_components(self.runs_root, directory / "tests")
        marker = directory / "workspace.json"
        _reject_symlink_components(self.runs_root, marker)
        if not marker.is_file():
            raise WorkspaceConflict(f"workspace incompleto: {directory}")
        try:
            metadata = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkspaceConflict(f"manifesto de workspace inválido: {directory}") from exc
        expected = {
            "run_id": run_id,
            "task_id": task_id,
            "revision": revision,
            "snapshot_id": expected_snapshot.snapshot_id,
            "snapshot_sha256": expected_snapshot.sha256,
        }
        if any(metadata.get(key) != value for key, value in expected.items()):
            raise WorkspaceConflict(
                f"run/task/revision já associado a outro snapshot: {directory}"
            )
        code_path = directory / "workspace"
        tests_path = directory / "tests"
        if not code_path.is_dir() or not tests_path.is_dir():
            raise WorkspaceConflict(f"estrutura de workspace incompleta: {directory}")
        # Não deixa um worker transformar um mount futuro em ponte para o host.
        _tree_entries(code_path)
        _tree_entries(tests_path)
        # Também corrige workspaces criados antes da introdução do UID
        # explícito; a operação é idempotente.
        _assign_owner(code_path, self.worker_uid, self.worker_gid)
        _assign_owner(tests_path, self.worker_uid, self.worker_gid)
        return Workspace(
            run_id=run_id,
            task_id=task_id,
            revision=revision,
            snapshot=expected_snapshot,
            path=directory,
            code_path=code_path,
            tests_path=tests_path,
        )
