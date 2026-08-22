"""Execução confinada das ferramentas declaradas por Dev, QA e runner.

Este módulo executa somente um vetor de argumentos. Ele deliberadamente não
oferece uma opção de shell, redirecionamento ou expansão de variáveis.
"""

from __future__ import annotations

import asyncio
import os
import re
import signal
import time
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath

MAX_ARGV_ITEMS = 64
MAX_ARGUMENT_LENGTH = 1000
MAX_TIMEOUT_SECONDS = 1800
DEFAULT_OUTPUT_LIMIT_BYTES = 64 * 1024
READ_CHUNK_BYTES = 8192

_ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ToolExecutionError(Exception):
    """Erro de validação ou infraestrutura anterior à execução."""


class InvalidExecution(ToolExecutionError):
    """Especificação de execução inválida."""


class CommandNotAllowed(ToolExecutionError):
    """Executável não permitido para o perfil solicitado."""


class WorkingDirectoryNotAllowed(ToolExecutionError):
    """Diretório virtual ausente ou fora de uma raiz autorizada."""


class ToolProfile(StrEnum):
    python = "python"
    node = "node"
    api = "api"
    browser = "browser"
    generic = "generic"


# A allowlist fica visível e injetável. Consumidores podem reduzi-la por
# scaffold, mas não precisam aceitar comandos livres vindos do LLM.
DEFAULT_COMMAND_ALLOWLIST: Mapping[ToolProfile, frozenset[str]] = {
    ToolProfile.python: frozenset({"python", "python3", "pytest", "ruff", "mypy"}),
    ToolProfile.node: frozenset({"node", "npm", "npx", "pnpm", "yarn"}),
    ToolProfile.api: frozenset({"curl"}),
    ToolProfile.browser: frozenset({"playwright"}),
    ToolProfile.generic: frozenset({"git"}),
}


@dataclass(frozen=True)
class ExecutionRequest:
    """Comando declarativo alinhado ao ``executionSpec`` do contrato v1."""

    argv: Sequence[str]
    cwd: str
    timeout_seconds: int
    profile: ToolProfile | str
    environment: Mapping[str, str] | None = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.argv, (str, bytes)):
            raise InvalidExecution("argv precisa ser uma sequência de argumentos")
        argv = tuple(self.argv)
        environment = dict(self.environment or {})
        try:
            profile = ToolProfile(self.profile)
        except ValueError as exc:
            raise InvalidExecution(
                f"perfil de ferramenta desconhecido: {self.profile!r}"
            ) from exc

        if not argv or len(argv) > MAX_ARGV_ITEMS:
            raise InvalidExecution(f"argv precisa conter entre 1 e {MAX_ARGV_ITEMS} itens")
        if any(
            not isinstance(argument, str)
            or not argument
            or len(argument) > MAX_ARGUMENT_LENGTH
            or "\x00" in argument
            for argument in argv
        ):
            raise InvalidExecution("argv contém um argumento inválido")
        if not isinstance(self.cwd, str) or not self.cwd:
            raise InvalidExecution("cwd precisa ser uma string não vazia")
        if not 1 <= self.timeout_seconds <= MAX_TIMEOUT_SECONDS:
            raise InvalidExecution(
                f"timeout_seconds precisa estar entre 1 e {MAX_TIMEOUT_SECONDS}"
            )
        if len(environment) > 32:
            raise InvalidExecution("environment aceita no máximo 32 variáveis")
        for name, value in environment.items():
            if not isinstance(name, str) or not _ENVIRONMENT_NAME.fullmatch(name):
                raise InvalidExecution(f"nome de variável de ambiente inválido: {name!r}")
            if not isinstance(value, str) or len(value) > 2000 or "\x00" in value:
                raise InvalidExecution(f"valor inválido para a variável {name!r}")

        object.__setattr__(self, "argv", argv)
        object.__setattr__(self, "profile", profile)
        object.__setattr__(self, "environment", environment)


@dataclass(frozen=True)
class ExecutionResult:
    argv: tuple[str, ...]
    cwd: str
    exit_code: int | None
    duration_ms: int
    stdout: str
    stderr: str
    timed_out: bool
    output_truncated: bool

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class _OutputBudget:
    """Orçamento compartilhado por stdout e stderr, sem acumular além do teto."""

    def __init__(self, limit: int) -> None:
        self.remaining = limit
        self.truncated = False
        self._lock = asyncio.Lock()

    async def take(self, chunk: bytes) -> bytes:
        async with self._lock:
            if len(chunk) <= self.remaining:
                self.remaining -= len(chunk)
                return chunk
            kept = chunk[: self.remaining]
            self.remaining = 0
            self.truncated = True
            return kept


async def _read_bounded(
    stream: asyncio.StreamReader | None, budget: _OutputBudget
) -> bytes:
    if stream is None:  # pragma: no cover - PIPE é obrigatório nesta implementação
        return b""
    chunks: list[bytes] = []
    while True:
        chunk = await stream.read(READ_CHUNK_BYTES)
        if not chunk:
            break
        kept = await budget.take(chunk)
        if kept:
            chunks.append(kept)
    return b"".join(chunks)


class ToolExecutor:
    """Executa comandos permitidos traduzindo cwd virtual para paths locais."""

    def __init__(
        self,
        *,
        workspace_root: str | Path | None = None,
        tests_root: str | Path | None = None,
        command_allowlist: Mapping[ToolProfile | str, Collection[str]] | None = None,
        output_limit_bytes: int = DEFAULT_OUTPUT_LIMIT_BYTES,
        base_environment: Mapping[str, str] | None = None,
    ) -> None:
        if workspace_root is None and tests_root is None:
            raise ValueError("ao menos uma raiz virtual precisa ser configurada")
        if output_limit_bytes < 1:
            raise ValueError("output_limit_bytes precisa ser positivo")

        roots: dict[str, Path] = {}
        if workspace_root is not None:
            roots["/workspace"] = Path(workspace_root).resolve()
        if tests_root is not None:
            roots["/tests"] = Path(tests_root).resolve()
        self._roots = roots
        self._output_limit_bytes = output_limit_bytes
        self._base_environment = dict(
            os.environ if base_environment is None else base_environment
        )

        configured = (
            DEFAULT_COMMAND_ALLOWLIST
            if command_allowlist is None
            else command_allowlist
        )
        allowlist: dict[ToolProfile, frozenset[str]] = {}
        for raw_profile, raw_commands in configured.items():
            try:
                profile = ToolProfile(raw_profile)
            except ValueError as exc:
                raise ValueError(f"perfil desconhecido na allowlist: {raw_profile!r}") from exc
            commands = frozenset(raw_commands)
            if any(
                not command or "/" in command or "\\" in command
                for command in commands
            ):
                raise ValueError("allowlist aceita somente nomes simples de executáveis")
            allowlist[profile] = commands
        self._command_allowlist = allowlist

    def _resolve_cwd(self, virtual_cwd: str) -> Path:
        if not virtual_cwd.startswith("/") or "\x00" in virtual_cwd:
            raise WorkingDirectoryNotAllowed(
                f"cwd precisa ser absoluto e virtual: {virtual_cwd!r}"
            )

        virtual = PurePosixPath(virtual_cwd)
        if ".." in virtual.parts:
            raise WorkingDirectoryNotAllowed(f"cwd contém traversal: {virtual_cwd!r}")

        root_name = next(
            (
                candidate
                for candidate in ("/workspace", "/tests")
                if virtual_cwd == candidate or virtual_cwd.startswith(f"{candidate}/")
            ),
            None,
        )
        if root_name is None or root_name not in self._roots:
            raise WorkingDirectoryNotAllowed(f"cwd fora das raízes montadas: {virtual_cwd!r}")

        root = self._roots[root_name]
        relative_parts = virtual.parts[2:]
        resolved = root.joinpath(*relative_parts).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise WorkingDirectoryNotAllowed(
                f"cwd resolve fora de {root_name}: {virtual_cwd!r}"
            ) from exc
        if not resolved.is_dir():
            raise WorkingDirectoryNotAllowed(f"cwd não existe: {virtual_cwd!r}")
        return resolved

    def _assert_command_allowed(self, request: ExecutionRequest) -> None:
        command = request.argv[0]
        if "/" in command or "\\" in command:
            raise CommandNotAllowed("o executável precisa ser um nome simples, sem path")
        allowed = self._command_allowlist.get(request.profile, frozenset())
        if command not in allowed:
            raise CommandNotAllowed(
                f"comando {command!r} não permitido no perfil {request.profile.value!r}"
            )

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Executa sem shell, mata o grupo no timeout e drena saída com limite."""

        self._assert_command_allowed(request)
        cwd = self._resolve_cwd(request.cwd)
        environment = {**self._base_environment, **request.environment}
        started = time.monotonic()

        process = await asyncio.create_subprocess_exec(
            *request.argv,
            cwd=cwd,
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        budget = _OutputBudget(self._output_limit_bytes)
        stdout_task = asyncio.create_task(_read_bounded(process.stdout, budget))
        stderr_task = asyncio.create_task(_read_bounded(process.stderr, budget))
        timed_out = False

        try:
            await asyncio.wait_for(process.wait(), timeout=request.timeout_seconds)
        except TimeoutError:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                process.kill()
            await process.wait()

        stdout_raw, stderr_raw = await asyncio.gather(stdout_task, stderr_task)
        duration_ms = max(0, round((time.monotonic() - started) * 1000))
        return ExecutionResult(
            argv=tuple(request.argv),
            cwd=request.cwd,
            exit_code=None if timed_out else process.returncode,
            duration_ms=duration_ms,
            stdout=stdout_raw.decode("utf-8", errors="replace"),
            stderr=stderr_raw.decode("utf-8", errors="replace"),
            timed_out=timed_out,
            output_truncated=budget.truncated,
        )
