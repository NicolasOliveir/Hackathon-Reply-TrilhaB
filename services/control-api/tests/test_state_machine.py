from __future__ import annotations

import json

import pytest

from app.contracts import state_machine
from app.contracts.models import EventType, RunState
from tests.conftest import CONTRACTS_DIR


def _definition() -> dict:
    with (CONTRACTS_DIR / "state-machine" / "v1.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def test_estado_inicial_vem_do_contrato() -> None:
    assert state_machine.initial_state() == RunState(_definition()["initial_state"])


def test_terminais_vem_do_contrato() -> None:
    esperados = {RunState(value) for value in _definition()["terminal_states"]}
    assert state_machine.terminal_states() == esperados


def test_todas_as_transicoes_do_contrato_sao_aplicaveis() -> None:
    for transition in _definition()["transitions"]:
        origem = RunState(transition["from"])
        evento = EventType(transition["event"])
        assert state_machine.next_state(origem, evento) == RunState(transition["to"])


def test_transicao_fora_do_contrato_e_recusada() -> None:
    # COMPLETED e terminal: nenhuma transicao parte dele.
    with pytest.raises(state_machine.InvalidTransition):
        state_machine.next_state(RunState.COMPLETED, EventType.TASK_QUEUED)


def test_evento_de_registro_nao_e_gatilho_de_transicao() -> None:
    """`RUN_CREATED` e `BRIEFING_RECEIVED` registram; nao movem estado."""
    assert state_machine.advances_state(EventType.RUN_CREATED) is False
    assert state_machine.advances_state(EventType.BRIEFING_RECEIVED) is False
    assert state_machine.advances_state(EventType.TASK_QUEUED) is True
