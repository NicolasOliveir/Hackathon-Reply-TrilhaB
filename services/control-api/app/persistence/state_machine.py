"""Máquina de estados carregada do contrato versionado.

As transições vivem em `packages/contracts/state-machine/v1.json`. Este módulo
lê aquele arquivo em vez de reescrever as regras em Python — duplicar a tabela
aqui criaria uma segunda fonte de verdade, que é exatamente o que o critério de
conclusão de I1-001 proíbe.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


class InvalidTransition(Exception):
    """Transição não declarada no contrato."""

    def __init__(self, state: str, event: str) -> None:
        self.state = state
        self.event = event
        super().__init__(
            f"Transição inválida: estado {state} não aceita o evento {event}."
        )


@dataclass(frozen=True)
class StateMachine:
    contract_version: str
    initial_state: str
    terminal_states: frozenset[str]
    _transitions: dict[tuple[str, str], str]

    def next_state(self, state: str, event: str) -> str:
        try:
            return self._transitions[(state, event)]
        except KeyError:
            raise InvalidTransition(state, event) from None

    def is_terminal(self, state: str) -> bool:
        return state in self.terminal_states

    def accepts(self, state: str, event: str) -> bool:
        return (state, event) in self._transitions


@lru_cache(maxsize=4)
def load_state_machine(path: Path) -> StateMachine:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    transitions = {
        (item["from"], item["event"]): item["to"] for item in raw["transitions"]
    }
    return StateMachine(
        contract_version=raw["contract_version"],
        initial_state=raw["initial_state"],
        terminal_states=frozenset(raw["terminal_states"]),
        _transitions=transitions,
    )
