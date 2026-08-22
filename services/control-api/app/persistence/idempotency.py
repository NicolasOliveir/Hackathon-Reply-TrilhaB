from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.tables import IdempotencyKey


class IdempotencyConflict(Exception):
    """Mesma chave, payload diferente. Repetir um comando com corpo distinto e erro do
    cliente, nao motivo para criar uma segunda execucao."""

    def __init__(self, key: str, endpoint: str) -> None:
        super().__init__(
            f"Idempotency-Key '{key}' ja foi usada em {endpoint} com payload diferente"
        )
        self.key = key
        self.endpoint = endpoint


def request_fingerprint(payload: Any) -> str:
    """Hash canonico do corpo: chaves ordenadas, sem espaco, UTF-8."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def lookup(
    session: AsyncSession, *, key: str, endpoint: str, fingerprint: str
) -> dict[str, Any] | None:
    """Resposta gravada quando a chave ja foi usada com o mesmo payload.

    Devolve `None` quando a chave e nova. Levanta `IdempotencyConflict` quando a chave
    existe com outro corpo.
    """
    record = (
        await session.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.key == key, IdempotencyKey.endpoint == endpoint
            )
        )
    ).scalar_one_or_none()

    if record is None:
        return None
    if record.request_hash != fingerprint:
        raise IdempotencyConflict(key, endpoint)
    return record.response


async def store(
    session: AsyncSession,
    *,
    key: str,
    endpoint: str,
    fingerprint: str,
    response: dict[str, Any],
    run_id: Any | None = None,
) -> None:
    session.add(
        IdempotencyKey(
            key=key,
            endpoint=endpoint,
            request_hash=fingerprint,
            run_id=run_id,
            response=response,
        )
    )
    await session.flush()
