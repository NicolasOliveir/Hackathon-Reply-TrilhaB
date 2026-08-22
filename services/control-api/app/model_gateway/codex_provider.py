"""Provedor Codex via CLI.

O Codex não é uma API HTTP com chave: é um binário autenticado pela sessão do
ChatGPT. A consequência arquitetural importa — a credencial vive no
`~/.codex/` do processo do `control-api` e **não** é uma variável de ambiente
que possa vazar para um container de agente.

`--output-schema` faz o CLI validar a saída contra JSON Schema antes de devolver,
o que dispensa parsing tolerante quando o chamador pede estrutura.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from .base import (
    ModelGatewayError,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    ProviderNotConfigured,
)

DEFAULT_MODEL = "gpt-5.6-terra"
DEFAULT_BINARY = "codex"

# Sandbox mínimo: o gateway pede texto, não edição de arquivo. Deixar o CLI em
# modo de escrita daria a ele mais poder do que a chamada precisa.
SANDBOX = "read-only"


class CodexProvider(ModelProvider):
    name = "codex"

    def __init__(
        self,
        binary: str = DEFAULT_BINARY,
        default_model: str = DEFAULT_MODEL,
        working_directory: str | None = None,
        codex_home: str | None = None,
    ) -> None:
        self._binary = binary
        self._default_model = default_model
        self._working_directory = working_directory
        # Aponta o CLI para o diretorio de sessao montado no container. Sem
        # isto o CLI procura em ~/.codex do usuario do processo, que dentro do
        # container nao e o mesmo do host.
        self._codex_home = codex_home

    def _resolve_binary(self) -> str:
        resolved = shutil.which(self._binary)
        if resolved is None:
            raise ProviderNotConfigured(
                f"binário '{self._binary}' não encontrado no PATH. O provedor codex "
                "exige o CLI instalado e autenticado no container do control-api."
            )
        return resolved

    async def invoke(self, request: ModelRequest) -> ModelResponse:
        binary = self._resolve_binary()
        model = request.model or self._default_model

        with tempfile.TemporaryDirectory(prefix="codex-gateway-") as tmp:
            schema_path = Path(tmp) / "schema.json"
            result_path = Path(tmp) / "result.txt"

            args = [
                "exec",
                "--sandbox",
                SANDBOX,
                "--output-last-message",
                str(result_path),
                "--model",
                model,
            ]
            if request.output_schema is not None:
                schema_path.write_text(
                    json.dumps(
                        _codex_output_schema(request.output_schema),
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                args += ["--output-schema", str(schema_path)]
            if request.effort:
                args += ["--config", f"model_reasoning_effort={json.dumps(request.effort)}"]

            prompt = request.prompt
            if request.system:
                prompt = f"{request.system}\n\n---\n\n{prompt}"
            args.append(prompt)

            started = time.perf_counter()
            stdout, stderr, exit_code, timed_out = await self._run(
                binary, args, request.timeout_seconds
            )
            latency_ms = int((time.perf_counter() - started) * 1000)

            if timed_out:
                raise ModelGatewayError(
                    f"codex excedeu {request.timeout_seconds}s sem responder."
                )
            if exit_code != 0:
                # O stderr do CLI pode conter caminho local; recortar evita que
                # um detalhe de ambiente entre no event log.
                raise ModelGatewayError(
                    f"codex encerrou com codigo {exit_code}: {stderr.strip()[:500]}"
                )

            text = (
                result_path.read_text(encoding="utf-8")
                if result_path.exists()
                else stdout
            )

        return ModelResponse(
            provider=self.name,
            model=model,
            text=text,
            # O CLI não expõe contagem de token na saída estruturada. Registrar
            # zero é honesto; inventar estimativa corromperia a auditoria de uso.
            usage=ModelUsage(),
            stop_reason="end_turn",
            latency_ms=latency_ms,
            parsed=_maybe_json(text) if request.output_schema is not None else None,
        )

    async def _run(
        self, binary: str, args: list[str], timeout_seconds: int
    ) -> tuple[str, str, int | None, bool]:
        environment = dict(os.environ)
        if self._codex_home:
            environment["CODEX_HOME"] = self._codex_home

        process = await asyncio.create_subprocess_exec(
            binary,
            *args,
            cwd=self._working_directory,
            env=environment,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout_seconds
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return "", "", None, True

        return (
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
            process.returncode,
            False,
        )


def _maybe_json(text: str) -> dict | None:
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _codex_output_schema(schema: dict) -> dict:
    """Remove keywords recusadas pelo structured output do Codex.

    `uniqueItems` continua no schema canônico e é aplicado pelo PO após a
    resposta. Aqui removemos somente a restrição que a Responses API não aceita
    no `response_format`; não alteramos o contrato persistido nem seu validador.
    """

    def normalize(value):
        if isinstance(value, dict):
            reference = value.get("$ref")
            if isinstance(reference, str) and reference.startswith(("http://", "https://")):
                # O CLI recusa referências remotas no response_format. A API
                # ainda valida a resposta contra o schema canônico completo.
                return {"type": "string"}
            return {
                key: normalize(item)
                for key, item in value.items()
                if key != "uniqueItems"
            }
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    return normalize(schema)
