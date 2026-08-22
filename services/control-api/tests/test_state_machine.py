"""Testes da máquina de estados. Não tocam o banco.

Cobrem que as transições vêm do contrato versionado e que uma transição não
declarada é recusada antes de qualquer gravação.
"""

from __future__ import annotations

import pytest

from app.persistence.state_machine import (
    InvalidTransition,
    load_state_machine,
)

CONTRACT = (
    __import__("pathlib").Path(__file__).resolve().parents[3]
    / "packages"
    / "contracts"
    / "state-machine"
    / "v1.json"
)


@pytest.fixture(scope="module")
def machine():
    return load_state_machine(CONTRACT)


def test_loads_the_versioned_contract(machine):
    assert machine.contract_version == "1.0.0"
    assert machine.initial_state == "RECEIVED"
    assert machine.terminal_states == {"COMPLETED", "FAILED", "CANCELED"}


def test_creation_path_matches_the_contract(machine):
    assert machine.next_state("RECEIVED", "TASK_QUEUED") == "WORKER_QUEUED"
    assert machine.next_state("WORKER_QUEUED", "AGENT_STARTED") == "WORKER_RUNNING"
    assert (
        machine.next_state("WORKER_RUNNING", "FAKE_WORKER_COMPLETED") == "COMPLETED"
    )


def test_undeclared_transition_is_rejected(machine):
    with pytest.raises(InvalidTransition):
        machine.next_state("RECEIVED", "FAKE_WORKER_COMPLETED")


def test_terminal_states_accept_nothing(machine):
    for state in machine.terminal_states:
        assert not machine.accepts(state, "TASK_QUEUED")
        assert machine.is_terminal(state)


def test_cancel_is_allowed_from_every_non_terminal_state(machine):
    for state in ("RECEIVED", "WORKER_QUEUED", "WORKER_RUNNING"):
        assert machine.next_state(state, "RUN_CANCELED") == "CANCELED"
