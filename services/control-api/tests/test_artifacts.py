"""Testes unitários do ArtifactStore local e confinado."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from app.artifacts import (
    ArtifactConflict,
    ArtifactIntegrityError,
    ArtifactMetadata,
    ArtifactStore,
    UnsafeArtifactPath,
)


def _metadata() -> ArtifactMetadata:
    return ArtifactMetadata(
        kind="test-report",
        media_type="application/json",
        producer="qa",
        run_id="11111111-1111-4111-8111-111111111111",
        task_id="22222222-2222-4222-8222-222222222222",
        attributes={"criterion_id": "AC-001"},
    )


def test_write_persists_metadata_hash_uri_and_bytes(tmp_path: Path):
    store = ArtifactStore(tmp_path / "artifacts")

    reference = store.write("runs/one/report.json", b'{"ok":true}', _metadata())

    assert reference.uri == f"artifact://{reference.artifact_id}"
    assert reference.sha256.startswith("sha256:")
    assert len(reference.sha256) == 71
    assert reference.size_bytes == 11
    assert store.read_bytes(reference) == b'{"ok":true}'
    record = store.get(reference.uri)
    assert record.relative_path == "runs/one/report.json"
    assert record.producer == "qa"
    assert record.attributes == {"criterion_id": "AC-001"}


def test_same_write_is_idempotent_and_conflicting_retry_is_rejected(tmp_path: Path):
    store = ArtifactStore(tmp_path / "artifacts")

    first = store.write("evidence/output.txt", "same", _metadata())
    second = store.write("evidence/output.txt", "same", _metadata())

    assert second == first
    with pytest.raises(ArtifactConflict):
        store.write("evidence/output.txt", "different", _metadata())


def test_store_instances_serialize_concurrent_writes_to_the_same_path(tmp_path: Path):
    root = tmp_path / "artifacts"
    stores = (ArtifactStore(root), ArtifactStore(root))
    barrier = Barrier(2)

    def write(index: int):
        barrier.wait()
        return stores[index].write(
            "evidence/concurrent.txt", f"payload-{index}", _metadata()
        )

    references = []
    conflicts = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(write, index) for index in range(2)]
        for future in futures:
            try:
                references.append(future.result())
            except ArtifactConflict as exc:
                conflicts.append(exc)

    assert len(references) == 1
    assert len(conflicts) == 1
    assert ArtifactStore(root).read_bytes(references[0]) in {
        b"payload-0",
        b"payload-1",
    }


def test_registers_file_materialized_at_confined_path(tmp_path: Path):
    store = ArtifactStore(tmp_path / "artifacts")
    target = store.path_for("screenshots/home.png", create_parents=True)
    target.write_bytes(b"PNG")

    reference = store.register("screenshots/home.png", _metadata())

    assert store.resolve(reference) == target
    assert store.register("screenshots/home.png", _metadata()) == reference


@pytest.mark.parametrize(
    "unsafe", ["../secret", "nested/../../secret", "/etc/passwd", "nested\\..\\secret", "."]
)
def test_rejects_path_traversal_and_absolute_paths(tmp_path: Path, unsafe: str):
    store = ArtifactStore(tmp_path / "artifacts")

    with pytest.raises(UnsafeArtifactPath):
        store.write(unsafe, b"nope", _metadata())


def test_rejects_symlink_in_artifact_path(tmp_path: Path):
    store = ArtifactStore(tmp_path / "artifacts")
    outside = tmp_path / "outside"
    outside.mkdir()
    (store.files_root / "escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(UnsafeArtifactPath):
        store.write("escape/leak.txt", b"nope", _metadata())

    assert not (outside / "leak.txt").exists()


def test_detects_bytes_changed_after_registration(tmp_path: Path):
    store = ArtifactStore(tmp_path / "artifacts")
    reference = store.write("report.txt", b"original", _metadata())
    store.path_for("report.txt").write_bytes(b"tampered")

    with pytest.raises(ArtifactIntegrityError):
        store.resolve(reference)


def test_rejects_store_root_that_is_a_symlink(tmp_path: Path):
    actual = tmp_path / "actual"
    actual.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(actual, target_is_directory=True)

    with pytest.raises(UnsafeArtifactPath):
        ArtifactStore(alias)
