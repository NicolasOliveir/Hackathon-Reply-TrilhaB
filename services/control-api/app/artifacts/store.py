"""Artifact store local com referências estáveis e verificação de integridade.

O caminho lógico informado por um worker nunca é usado sem validação. Os bytes
ficam em ``files/`` e os registros, índices por caminho e hashes ficam fora do
namespace gravável de artefatos. Essa separação também impede que um nome de
artefato possa sobrescrever seus próprios metadados.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from urllib.parse import urlparse
from uuid import UUID, NAMESPACE_URL, uuid5


class ArtifactError(Exception):
    """Erro base do armazenamento de artefatos."""


class UnsafeArtifactPath(ArtifactError, ValueError):
    """O caminho escaparia do store ou atravessaria um link simbólico."""


class ArtifactConflict(ArtifactError):
    """O mesmo caminho lógico já contém outro artefato."""


class ArtifactNotFound(ArtifactError, FileNotFoundError):
    """A referência não existe no store."""


class ArtifactIntegrityError(ArtifactError):
    """Os bytes persistidos não correspondem ao registro imutável."""


@dataclass(frozen=True)
class ArtifactMetadata:
    """Metadados fornecidos pelo produtor no registro do artefato."""

    kind: str
    media_type: str
    producer: str
    run_id: str | None = None
    task_id: str | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.kind or len(self.kind) > 80:
            raise ValueError("kind deve conter entre 1 e 80 caracteres")
        if len(self.media_type) < 3 or len(self.media_type) > 120:
            raise ValueError("media_type deve conter entre 3 e 120 caracteres")
        if not self.producer:
            raise ValueError("producer é obrigatório")
        # Garante serialização já na borda, antes de qualquer escrita parcial.
        try:
            json.dumps(self.attributes, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("attributes deve ser serializável como JSON") from exc


@dataclass(frozen=True)
class ArtifactRef:
    """Shape compatível com ``common.schema.json#/$defs/artifactRef``."""

    artifact_id: str
    kind: str
    uri: str
    media_type: str
    size_bytes: int
    sha256: str

    def as_dict(self) -> dict[str, str | int]:
        return asdict(self)


@dataclass(frozen=True)
class ArtifactRecord:
    ref: ArtifactRef
    relative_path: str
    producer: str
    run_id: str | None
    task_id: str | None
    attributes: Mapping[str, Any]
    created_at: datetime


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _normalise_relative_path(value: str | PurePosixPath | Path) -> PurePosixPath:
    raw = str(value)
    if not raw or "\x00" in raw or "\\" in raw:
        raise UnsafeArtifactPath(f"caminho de artefato inválido: {raw!r}")
    path = PurePosixPath(raw)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise UnsafeArtifactPath(f"caminho deve ser relativo e confinado: {raw!r}")
    return path


def _reject_symlinks(base: Path, candidate: Path) -> None:
    """Rejeita links em qualquer componente já existente sob ``base``."""

    try:
        relative = candidate.relative_to(base)
    except ValueError as exc:
        raise UnsafeArtifactPath(f"caminho fora do store: {candidate}") from exc

    current = base
    if current.is_symlink():
        raise UnsafeArtifactPath(f"raiz do store é link simbólico: {current}")
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            raise UnsafeArtifactPath(f"link simbólico não permitido: {current}")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class ArtifactStore:
    """Store local idempotente, endereçado por referência ``artifact://``."""

    def __init__(self, root: str | Path) -> None:
        requested_root = Path(root).absolute()
        if requested_root.is_symlink():
            raise UnsafeArtifactPath(
                f"raiz do store não pode ser link simbólico: {requested_root}"
            )
        requested_root.mkdir(parents=True, exist_ok=True)
        self.root = requested_root.resolve(strict=True)
        self.files_root = self.root / "files"
        self._records_root = self.root / "records"
        self._index_root = self.root / "path-index"
        for directory in (self.files_root, self._records_root, self._index_root):
            if directory.is_symlink():
                raise UnsafeArtifactPath(f"diretório do store é link: {directory}")
            directory.mkdir(exist_ok=True)
        self._lock = threading.RLock()

    def path_for(
        self,
        relative_path: str | PurePosixPath | Path,
        *,
        create_parents: bool = False,
    ) -> Path:
        """Retorna um destino confinado para produtores que escrevem por stream."""

        logical = _normalise_relative_path(relative_path)
        target = self.files_root.joinpath(*logical.parts)
        _reject_symlinks(self.files_root, target)
        if create_parents:
            target.parent.mkdir(parents=True, exist_ok=True)
            _reject_symlinks(self.files_root, target)
        return target

    def write(
        self,
        relative_path: str | PurePosixPath | Path,
        data: bytes | bytearray | memoryview | str,
        metadata: ArtifactMetadata,
        *,
        encoding: str = "utf-8",
    ) -> ArtifactRef:
        """Persiste bytes e registro; o mesmo retry devolve a mesma referência."""

        payload = data.encode(encoding) if isinstance(data, str) else bytes(data)
        logical = _normalise_relative_path(relative_path)
        target = self.path_for(logical)

        with self._lock:
            existing = self._record_for_path(logical)
            candidate = self._build_record(logical, payload, metadata)
            if existing is not None:
                self._assert_idempotent(existing, candidate, target)
                return existing.ref
            if target.exists():
                raise ArtifactConflict(
                    f"caminho já existe sem registro: {logical.as_posix()}"
                )

            target.parent.mkdir(parents=True, exist_ok=True)
            _reject_symlinks(self.files_root, target)
            _atomic_write(target, payload)
            try:
                self._persist_record(candidate)
            except Exception:
                target.unlink(missing_ok=True)
                raise
            return candidate.ref

    def register(
        self,
        relative_path: str | PurePosixPath | Path,
        metadata: ArtifactMetadata,
    ) -> ArtifactRef:
        """Registra um arquivo já materializado por um worker no store."""

        logical = _normalise_relative_path(relative_path)
        target = self.path_for(logical)
        with self._lock:
            if not target.is_file():
                raise ArtifactNotFound(f"arquivo não encontrado: {logical.as_posix()}")
            _reject_symlinks(self.files_root, target)
            payload = target.read_bytes()
            candidate = self._build_record(logical, payload, metadata)
            existing = self._record_for_path(logical)
            if existing is not None:
                self._assert_idempotent(existing, candidate, target)
                return existing.ref
            self._persist_record(candidate)
            return candidate.ref

    def get(self, reference: ArtifactRef | UUID | str) -> ArtifactRecord:
        artifact_id = self._parse_artifact_id(reference)
        record_path = self._records_root / f"{artifact_id}.json"
        _reject_symlinks(self._records_root, record_path)
        if not record_path.is_file():
            raise ArtifactNotFound(f"artefato não encontrado: {artifact_id}")
        try:
            raw = json.loads(record_path.read_text(encoding="utf-8"))
            return self._deserialize_record(raw)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ArtifactIntegrityError(
                f"registro inválido para artefato {artifact_id}"
            ) from exc

    def resolve(self, reference: ArtifactRef | UUID | str) -> Path:
        """Resolve a referência e confere tamanho e SHA-256 antes de expor o path."""

        record = self.get(reference)
        target = self.path_for(record.relative_path)
        if not target.is_file():
            raise ArtifactNotFound(f"bytes ausentes para {record.ref.artifact_id}")
        payload = target.read_bytes()
        if len(payload) != record.ref.size_bytes or _sha256_bytes(payload) != record.ref.sha256:
            raise ArtifactIntegrityError(
                f"hash ou tamanho divergente para {record.ref.artifact_id}"
            )
        return target

    def read_bytes(self, reference: ArtifactRef | UUID | str) -> bytes:
        return self.resolve(reference).read_bytes()

    def _build_record(
        self,
        logical: PurePosixPath,
        payload: bytes,
        metadata: ArtifactMetadata,
    ) -> ArtifactRecord:
        sha256 = _sha256_bytes(payload)
        identity = json.dumps(
            {
                "relative_path": logical.as_posix(),
                "sha256": sha256,
                "kind": metadata.kind,
                "media_type": metadata.media_type,
                "producer": metadata.producer,
                "run_id": metadata.run_id,
                "task_id": metadata.task_id,
                "attributes": metadata.attributes,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        artifact_id = str(uuid5(NAMESPACE_URL, identity))
        return ArtifactRecord(
            ref=ArtifactRef(
                artifact_id=artifact_id,
                kind=metadata.kind,
                uri=f"artifact://{artifact_id}",
                media_type=metadata.media_type,
                size_bytes=len(payload),
                sha256=sha256,
            ),
            relative_path=logical.as_posix(),
            producer=metadata.producer,
            run_id=metadata.run_id,
            task_id=metadata.task_id,
            attributes=dict(metadata.attributes),
            created_at=_utc_now(),
        )

    def _persist_record(self, record: ArtifactRecord) -> None:
        record_path = self._records_root / f"{record.ref.artifact_id}.json"
        index_path = self._index_path(PurePosixPath(record.relative_path))
        _reject_symlinks(self._records_root, record_path)
        _reject_symlinks(self._index_root, index_path)
        serialised = json.dumps(
            {
                "version": 1,
                "ref": record.ref.as_dict(),
                "relative_path": record.relative_path,
                "producer": record.producer,
                "run_id": record.run_id,
                "task_id": record.task_id,
                "attributes": record.attributes,
                "created_at": record.created_at.isoformat(),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        _atomic_write(record_path, serialised)
        try:
            _atomic_write(index_path, record.ref.artifact_id.encode("ascii"))
        except Exception:
            record_path.unlink(missing_ok=True)
            raise

    def _record_for_path(self, logical: PurePosixPath) -> ArtifactRecord | None:
        index_path = self._index_path(logical)
        _reject_symlinks(self._index_root, index_path)
        if not index_path.exists():
            return None
        try:
            artifact_id = UUID(index_path.read_text(encoding="ascii").strip())
        except (UnicodeDecodeError, ValueError) as exc:
            raise ArtifactIntegrityError(
                f"índice inválido para {logical.as_posix()}"
            ) from exc
        record = self.get(artifact_id)
        if record.relative_path != logical.as_posix():
            raise ArtifactIntegrityError(
                f"índice aponta para outro caminho: {logical.as_posix()}"
            )
        return record

    def _index_path(self, logical: PurePosixPath) -> Path:
        key = hashlib.sha256(logical.as_posix().encode("utf-8")).hexdigest()
        return self._index_root / f"{key}.ref"

    def _assert_idempotent(
        self,
        existing: ArtifactRecord,
        candidate: ArtifactRecord,
        target: Path,
    ) -> None:
        if existing.ref != candidate.ref or existing.relative_path != candidate.relative_path:
            raise ArtifactConflict(
                f"caminho já registrado com conteúdo ou metadados diferentes: "
                f"{candidate.relative_path}"
            )
        if not target.is_file():
            raise ArtifactIntegrityError(f"bytes ausentes para {existing.ref.artifact_id}")
        payload = target.read_bytes()
        if _sha256_bytes(payload) != existing.ref.sha256:
            raise ArtifactIntegrityError(
                f"bytes alterados para {existing.ref.artifact_id}"
            )

    @staticmethod
    def _parse_artifact_id(reference: ArtifactRef | UUID | str) -> UUID:
        if isinstance(reference, ArtifactRef):
            raw = reference.artifact_id
        elif isinstance(reference, UUID):
            return reference
        else:
            raw = reference
            parsed = urlparse(raw)
            if parsed.scheme:
                if parsed.scheme != "artifact" or not parsed.netloc or parsed.path not in {"", "/"}:
                    raise ArtifactNotFound(f"URI de artefato inválida: {raw}")
                raw = parsed.netloc
        try:
            return UUID(raw)
        except (AttributeError, ValueError) as exc:
            raise ArtifactNotFound(f"referência de artefato inválida: {raw!r}") from exc

    @staticmethod
    def _deserialize_record(raw: Mapping[str, Any]) -> ArtifactRecord:
        ref_raw = raw["ref"]
        ref = ArtifactRef(
            artifact_id=str(UUID(ref_raw["artifact_id"])),
            kind=ref_raw["kind"],
            uri=ref_raw["uri"],
            media_type=ref_raw["media_type"],
            size_bytes=int(ref_raw["size_bytes"]),
            sha256=ref_raw["sha256"],
        )
        if ref.uri != f"artifact://{ref.artifact_id}":
            raise ValueError("URI divergente")
        return ArtifactRecord(
            ref=ref,
            relative_path=_normalise_relative_path(raw["relative_path"]).as_posix(),
            producer=raw["producer"],
            run_id=raw.get("run_id"),
            task_id=raw.get("task_id"),
            attributes=raw.get("attributes", {}),
            created_at=datetime.fromisoformat(raw["created_at"]),
        )
