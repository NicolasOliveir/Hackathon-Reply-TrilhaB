"""Upload e leitura de artefatos exclusivamente pela API central."""

from __future__ import annotations

import asyncio
import base64
import binascii
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from ...artifacts import (
    ArtifactConflict,
    ArtifactIntegrityError,
    ArtifactMetadata,
    ArtifactNotFound,
    ArtifactStore,
    UnsafeArtifactPath,
)
from ...config import CONTRACT_VERSION, Settings, get_settings
from ...db import transaction
from .tasks import _authenticate

router = APIRouter(prefix="/internal/v1/tasks", tags=["internal"])


class ArtifactUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str = Field(default=CONTRACT_VERSION, pattern="^1\\.0\\.0$")
    path: str = Field(min_length=1, max_length=500)
    kind: str = Field(min_length=1, max_length=80)
    media_type: str = Field(min_length=3, max_length=120)
    content_base64: str = Field(min_length=1)
    attributes: dict[str, Any] = Field(default_factory=dict)


def _decode_content(encoded: str, maximum: int) -> bytes:
    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="content_base64 inválido.",
        ) from exc
    if len(content) > maximum:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"artefato excede o limite de {maximum} bytes.",
        )
    return content


@router.post(
    "/{task_id}/artifacts",
    status_code=status.HTTP_201_CREATED,
    response_model=None,
    summary="Persiste um artefato da tarefa no armazenamento central.",
)
async def upload_artifact(
    task_id: uuid.UUID,
    payload: ArtifactUpload,
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    async with transaction() as session:
        task = await _authenticate(session, task_id, authorization)
        if "artifact:write" not in settings.scopes_for_role(task.role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"papel '{task.role}' não possui artifact:write.",
            )
        run_id = str(task.run_id)
        role = task.role

    content = _decode_content(payload.content_base64, settings.artifact_max_bytes)
    store = ArtifactStore(settings.artifact_root)
    logical_path = f"runs/{run_id}/tasks/{task_id}/{payload.path}"
    try:
        reference = await asyncio.to_thread(
            store.write,
            logical_path,
            content,
            ArtifactMetadata(
                kind=payload.kind,
                media_type=payload.media_type,
                producer=role,
                run_id=run_id,
                task_id=str(task_id),
                attributes=payload.attributes,
            ),
        )
    except UnsafeArtifactPath as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ArtifactConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return reference.as_dict()


@router.get(
    "/{task_id}/artifacts/{artifact_id}",
    response_class=Response,
    summary="Lê um artefato do mesmo run da tarefa autenticada.",
)
async def download_artifact(
    task_id: uuid.UUID,
    artifact_id: uuid.UUID,
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    async with transaction() as session:
        task = await _authenticate(session, task_id, authorization)
        run_id = str(task.run_id)

    store = ArtifactStore(settings.artifact_root)
    try:
        record = await asyncio.to_thread(store.get, artifact_id)
        if record.run_id != run_id:
            raise ArtifactNotFound(str(artifact_id))
        content = await asyncio.to_thread(store.read_bytes, artifact_id)
    except ArtifactNotFound as exc:
        raise HTTPException(status_code=404, detail="artefato não encontrado") from exc
    except ArtifactIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return Response(
        content=content,
        media_type=record.ref.media_type,
        headers={
            "ETag": f'"{record.ref.sha256}"',
            "X-Artifact-Id": record.ref.artifact_id,
        },
    )
