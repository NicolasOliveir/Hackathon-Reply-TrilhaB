"""Diagnóstico de credencial dos provedores.

Existe por um motivo operacional: com plano (assinatura) em vez de chave de API,
a falha não é "401 na primeira chamada" — é o perfil não estar montado, não ser
gravável, ou estar com permissão aberta demais. Descobrir isso no meio da demo é
tarde.

**Nada aqui devolve valor de credencial.** Só caminho, existência, permissão e
qual fonte o SDK usaria.

Fatos verificados no SDK `anthropic` 1.0.0, não inferidos:

- ordem de resolução: `ANTHROPIC_API_KEY` → `ANTHROPIC_AUTH_TOKEN` → perfil
  (`ANTHROPIC_PROFILE` / `ANTHROPIC_CONFIG_DIR`) → federação → perfil ativo em
  disco (`lib/credentials/_chain.py`);
- o perfil vive em `<config_dir>/configs/<perfil>.json`, e o perfil ativo é o
  nomeado em `<config_dir>/active_config`, ou `default` (`_client.py:173-178`);
- ao renovar, o SDK **grava de volta**: `mkstemp` no diretório do arquivo,
  `fchmod 0600` e `os.replace` (`lib/credentials/_providers.py:470-480`);
- ele **recusa** arquivo group-readable, pedindo `chmod 600`
  (`lib/credentials/_providers.py:388`).

As duas últimas são a razão de o diretório precisar ser montado **gravável** e
com permissão restrita: um mount read-only funciona por alguns minutos e falha
quando o token expira.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PROFILE = "default"


@dataclass(frozen=True)
class CredentialStatus:
    provider: str
    source: str
    ready: bool
    detail: str
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "provider": self.provider,
            "source": self.source,
            "ready": self.ready,
            "detail": self.detail,
            "warnings": list(self.warnings),
        }


def _anthropic_config_dir() -> Path:
    override = os.getenv("ANTHROPIC_CONFIG_DIR")
    if override:
        return Path(override)
    return Path.home() / ".config" / "anthropic"


def _check_writable(directory: Path) -> str | None:
    """O refresh grava um temporário no diretório e renomeia sobre o arquivo."""
    if not directory.exists():
        return None
    if not os.access(directory, os.W_OK):
        return (
            f"{directory} não é gravável. O SDK renova o token e grava de volta; "
            "com mount read-only a autenticação falha quando o token expira."
        )
    return None


def _check_permissions(path: Path) -> str | None:
    """O SDK recusa credencial legível pelo grupo."""
    if not path.exists() or os.name == "nt":
        # No Windows o bit de grupo não tem o mesmo significado, e o próprio SDK
        # só aplica a checagem em POSIX.
        return None
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        return f"{path} está com modo {mode:#o}; o SDK exige 0600 — rode chmod 600."
    return None


def describe_anthropic() -> CredentialStatus:
    warnings: list[str] = []

    if os.getenv("ANTHROPIC_API_KEY"):
        return CredentialStatus(
            provider="anthropic",
            source="ANTHROPIC_API_KEY",
            ready=True,
            detail="chave estática no ambiente do control-api",
        )
    if os.getenv("ANTHROPIC_AUTH_TOKEN"):
        return CredentialStatus(
            provider="anthropic",
            source="ANTHROPIC_AUTH_TOKEN",
            ready=True,
            detail="token estático no ambiente do control-api",
        )

    config_dir = _anthropic_config_dir()
    profile = os.getenv("ANTHROPIC_PROFILE")
    if not profile:
        active = config_dir / "active_config"
        profile = (
            active.read_text(encoding="utf-8").strip()
            if active.exists()
            else DEFAULT_PROFILE
        )

    credentials = config_dir / "configs" / f"{profile}.json"
    if not credentials.exists():
        return CredentialStatus(
            provider="anthropic",
            source="perfil",
            ready=False,
            detail=(
                f"perfil '{profile}' não encontrado em {credentials}. "
                "Rode `ant auth login` e monte o diretório no container."
            ),
        )

    for warning in (_check_writable(config_dir / "configs"), _check_permissions(credentials)):
        if warning:
            warnings.append(warning)

    return CredentialStatus(
        provider="anthropic",
        source=f"perfil '{profile}'",
        ready=True,
        detail=f"credencial de assinatura em {credentials}",
        warnings=tuple(warnings),
    )


def describe_codex(binary: str = "codex") -> CredentialStatus:
    import shutil

    resolved = shutil.which(binary)
    if resolved is None:
        return CredentialStatus(
            provider="codex",
            source="CLI",
            ready=False,
            detail=(
                f"binário '{binary}' fora do PATH. O provedor codex exige o CLI "
                "instalado na imagem do control-api."
            ),
        )

    home = Path(os.getenv("CODEX_HOME") or (Path.home() / ".codex"))
    auth = home / "auth.json"
    if not auth.exists():
        return CredentialStatus(
            provider="codex",
            source="sessão ChatGPT",
            ready=False,
            detail=f"sessão ausente em {auth}. Rode `codex login` e monte {home}.",
        )

    warnings = [w for w in (_check_writable(home), _check_permissions(auth)) if w]
    return CredentialStatus(
        provider="codex",
        source="sessão ChatGPT",
        ready=True,
        detail=f"sessão em {auth} (CLI em {resolved})",
        warnings=tuple(warnings),
    )


def describe(providers: list[str], *, codex_binary: str = "codex") -> list[CredentialStatus]:
    statuses: list[CredentialStatus] = []
    for name in providers:
        if name == "anthropic":
            statuses.append(describe_anthropic())
        elif name == "codex":
            statuses.append(describe_codex(codex_binary))
        elif name == "echo":
            statuses.append(
                CredentialStatus(
                    provider="echo",
                    source="nenhuma",
                    ready=True,
                    detail="provedor determinístico, sem rede",
                )
            )
    return statuses
