"""Serialização e leitura incremental do event log em Server-Sent Events."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator

from ...config import CONTRACT_VERSION, Settings
from ...contracts.v1.event_envelope_schema import EventEnvelope
from ...db import get_session_factory
from ...persistence.event_store import EventStore
from ...persistence.models import Event
from ...persistence.state_machine import load_state_machine

DEFAULT_BATCH_SIZE = 100
DEFAULT_HEARTBEAT_SECONDS = 15.0
DEFAULT_POLL_INTERVAL_SECONDS = 0.25


def event_envelope(event: Event) -> EventEnvelope:
    """Converte o modelo persistido usando o contrato gerado como fronteira."""
    return EventEnvelope(
        contract_version=CONTRACT_VERSION,
        event_id=event.event_id,
        sequence=event.sequence,
        run_id=event.run_id,
        ts=event.ts,
        actor=event.actor,
        type=event.type,
        correlation_id=event.correlation_id,
        causation_id=event.causation_id,
        task_id=event.task_id,
        payload=event.payload,
        meta=event.meta,
    )


def encode_event(event: Event) -> str:
    """Codifica um evento SSE anônimo, compatível com `EventSource.onmessage`.

    O `id` é o `sequence`, e não o UUID do evento. Assim o navegador envia o
    cursor no header `Last-Event-ID` ao reconectar e o servidor consulta apenas
    registros posteriores, sem perda nem duplicação.
    """
    payload = event_envelope(event).model_dump(mode="json", exclude_none=False)
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event.sequence}\ndata: {data}\n\n"


async def iter_run_events(
    run_id: uuid.UUID,
    settings: Settings,
    *,
    after_sequence: int = 0,
    batch_size: int = DEFAULT_BATCH_SIZE,
    heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> AsyncIterator[str]:
    """Segue o log de um run a partir de um cursor exclusivo.

    Cada consulta usa uma sessão curta. Uma conexão SSE pode durar horas e não
    deve reter conexão ou transação do PostgreSQL enquanto aguarda novo evento.
    """
    cursor = after_sequence
    last_activity = time.monotonic()
    session_factory = get_session_factory()
    state_machine = load_state_machine(settings.state_machine_path)

    while True:
        async with session_factory() as session:
            store = EventStore(session, state_machine)
            events = await store.list_events(
                run_id,
                after_sequence=cursor,
                limit=batch_size,
            )

        if events:
            for event in events:
                # Avança antes de entregar o chunk: a próxima iteração nunca
                # relê um evento já emitido por esta conexão.
                cursor = event.sequence
                last_activity = time.monotonic()
                yield encode_event(event)

            # Um lote cheio pode esconder mais eventos já persistidos; nesse
            # caso buscamos a próxima página imediatamente. Um lote parcial
            # significa que alcançamos o fim atual do log. Aguardar antes da
            # próxima consulta também faz o cancelamento de um cliente ocorrer
            # sem uma conexão do pool aberta na maioria dos fechamentos.
            if len(events) == batch_size:
                continue

        now = time.monotonic()
        if now - last_activity >= heartbeat_seconds:
            # Comentários SSE mantêm proxies e conexões ociosas vivos sem
            # aparecer como eventos para o cliente.
            yield ": keep-alive\n\n"
            last_activity = now

        await asyncio.sleep(poll_interval_seconds)
