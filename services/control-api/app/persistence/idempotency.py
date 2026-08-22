"""Deduplicação de comandos por `Idempotency-Key`.

Contrato (openapi/v1): a chave é obrigatória em `POST /api/v1/runs`; repetir a
chave com o mesmo payload devolve a resposta original, e repetir com payload
diferente devolve `409`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from sqlalchemy.ext.asyncio import AsyncSession

from .event_store import sha256_of
from .models import IdempotencyKey


class IdempotencyConflict(Exception):
    """Mesma chave, payload diferente."""


@dataclass(frozen=True)
class ReplayedResponse:
    status: int
    body: dict[str, Any]


def hash_request(payload: Any) -> str:
    """Hash canônico do corpo da requisição.

    `sort_keys` e separadores fixos evitam que uma diferença apenas de
    formatação — ordem de chaves ou espaçamento — seja lida como payload
    diferente e gere um 409 indevido.
    """
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return sha256_of(canonical)


async def claim(
    session: AsyncSession, *, scope: str, key: str, request_hash: str
) -> ReplayedResponse | None:
    """Reserva a chave ou devolve a resposta já registrada.

    Retorna `None` quando a chave é nova e o comando deve executar.
    Retorna `ReplayedResponse` quando o mesmo comando já foi processado.
    Levanta `IdempotencyConflict` quando a chave existe com outro payload.

    O `ON CONFLICT DO NOTHING` seguido de leitura fecha a corrida entre duas
    requisições simultâneas com a mesma chave: uma insere, a outra lê.
    """
    statement = (
        pg_insert(IdempotencyKey)
        .values(
            scope=scope,
            key=key,
            request_hash=request_hash,
            response_status=0,
            response_body={},
        )
        .on_conflict_do_nothing(index_elements=[IdempotencyKey.scope, IdempotencyKey.key])
        .returning(IdempotencyKey.id)
    )
    result = await session.execute(statement)
    if result.scalar_one_or_none() is not None:
        return None

    existing = (
        await session.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.scope == scope, IdempotencyKey.key == key
            )
        )
    ).scalar_one()

    if existing.request_hash != request_hash:
        raise IdempotencyConflict(
            f"Idempotency-Key '{key}' já foi usada com um payload diferente."
        )

    if existing.response_status == 0:
        # A requisição original ainda está em voo. Tratar como conflito é mais
        # honesto do que devolver um corpo vazio ou esperar em loop.
        raise IdempotencyConflict(
            f"Idempotency-Key '{key}' está sendo processada por outra requisição."
        )

    return ReplayedResponse(
        status=existing.response_status, body=existing.response_body
    )


async def record_response(
    session: AsyncSession,
    *,
    scope: str,
    key: str,
    status: int,
    body: dict[str, Any],
    run_id: Any | None = None,
) -> None:
    """Completa a reserva com a resposta definitiva."""
    existing = (
        await session.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.scope == scope, IdempotencyKey.key == key
            )
        )
    ).scalar_one()
    existing.response_status = status
    existing.response_body = body
    existing.run_id = run_id
    await session.flush()
