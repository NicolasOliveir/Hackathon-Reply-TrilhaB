"""Credencial de tarefa.

ORQUESTRADOR §8.1: cada container recebe um bearer token aleatório, armazenado
apenas como hash, vinculado a `task_id` e papel, com validade curta.

O valor em claro existe somente na memória do scheduler e na variável de
ambiente do container. Nada no banco permite reconstruí-lo.
"""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass

from ..config import ROLE_SCOPES, BASE_SCOPES
from ..persistence.event_store import sha256_of

TOKEN_BYTES = 32

# Mantido por compatibilidade com I1-005; a fonte canonica passou a ser
# ROLE_SCOPES em config.py, para que emissor de token e gateway leiam do mesmo
# lugar. `model:invoke` continua fora do papel `fake`.
FAKE_WORKER_SCOPES = list(ROLE_SCOPES["fake"])


def scopes_for(role: str) -> list[str]:
    """Escopos do token de um papel."""
    return list(ROLE_SCOPES.get(role, BASE_SCOPES))


@dataclass(frozen=True)
class IssuedToken:
    plaintext: str
    hashed: str


def issue() -> IssuedToken:
    plaintext = secrets.token_urlsafe(TOKEN_BYTES)
    return IssuedToken(plaintext=plaintext, hashed=sha256_of(plaintext))


def matches(presented: str, stored_hash: str | None) -> bool:
    """Compara em tempo constante.

    `hmac.compare_digest` evita que o tempo de resposta revele quantos
    caracteres do token estavam corretos.
    """
    if not presented or not stored_hash:
        return False
    return hmac.compare_digest(sha256_of(presented), stored_hash)
