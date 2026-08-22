"""Maquina de estados carregada de `packages/contracts/state-machine/v1.json`.

As transicoes nao sao reescritas em Python. O arquivo versionado do contrato e a unica
fonte; este modulo apenas o interpreta e recusa transicao invalida.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from app.contracts.models import EventType, RunState


class InvalidTransition(Exception):
    """Transicao inexistente no contrato para o par (estado atual, evento)."""

    def __init__(self, current: RunState, event: EventType) -> None:
        super().__init__(
            f"Transicao invalida: estado {current.value} nao aceita o evento {event.value}"
        )
        self.current = current
        self.event = event


def _contracts_dir() -> Path:
    override = os.getenv("CONTRACTS_DIR")
    if override:
        return Path(override)
    # services/control-api/app/contracts/state_machine.py -> raiz do repositorio
    return Path(__file__).resolve().parents[4] / "packages" / "contracts"


@lru_cache(maxsize=1)
def _definition() -> dict:
    path = _contracts_dir() / "state-machine" / "v1.json"
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def _transition_index() -> dict[tuple[str, str], str]:
    return {
        (item["from"], item["event"]): item["to"]
        for item in _definition()["transitions"]
    }


def initial_state() -> RunState:
    return RunState(_definition()["initial_state"])


def terminal_states() -> frozenset[RunState]:
    return frozenset(RunState(value) for value in _definition()["terminal_states"])


def is_terminal(state: RunState) -> bool:
    return state in terminal_states()


def next_state(current: RunState, event: EventType) -> RunState:
    """Estado resultante, ou `InvalidTransition` quando o contrato nao a define."""
    target = _transition_index().get((current.value, event.value))
    if target is None:
        raise InvalidTransition(current, event)
    return RunState(target)


def advances_state(event: EventType) -> bool:
    """`True` quando o evento aparece como gatilho de alguma transicao.

    Eventos de registro puro — `RUN_CREATED`, `BRIEFING_RECEIVED` — nao mudam estado e
    tambem nao devem ser recusados como transicao invalida.
    """
    return any(event.value == key[1] for key in _transition_index())
