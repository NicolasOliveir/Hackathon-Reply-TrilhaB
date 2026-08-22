from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Collection, Mapping


def _load_executor_module():
    try:
        import tool_executor  # type: ignore[import-not-found]

        return tool_executor
    except ModuleNotFoundError:
        # Desenvolvimento local: usa diretamente a implementação entregue pelo
        # I2-003. No container, o Dockerfile a copia para /app/tool_executor.py.
        source = Path(__file__).parents[1] / "control-api/app/runtime/tools/executor.py"
        spec = importlib.util.spec_from_file_location("tool_executor", source)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"não foi possível carregar ToolExecutor de {source}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module


_executor = _load_executor_module()
ExecutionRequest = _executor.ExecutionRequest
ExecutionResult = _executor.ExecutionResult
ToolExecutor = _executor.ToolExecutor
ToolExecutionError = _executor.ToolExecutionError


def build_executor(workspace: Path) -> Any:
    return ToolExecutor(workspace_root=workspace, output_limit_bytes=4 * 1024 * 1024)


async def run_git(
    executor: Any,
    argv: list[str],
    *,
    accepted_exit_codes: Collection[int] = (0,),
) -> Any:
    result = await executor.execute(
        ExecutionRequest(
            argv=["git", *argv],
            cwd="/workspace",
            timeout_seconds=120,
            profile="generic",
        )
    )
    if result.exit_code not in accepted_exit_codes or result.timed_out:
        detail = (result.stderr or result.stdout).strip()[:2000]
        raise RuntimeError(f"git {' '.join(argv)} falhou: {detail or result.exit_code}")
    return result


async def run_declared(executor: Any, execution: Mapping[str, Any]) -> Any:
    return await executor.execute(
        ExecutionRequest(
            argv=execution["argv"],
            cwd=execution["cwd"],
            timeout_seconds=execution["timeout_seconds"],
            profile=execution["profile"],
            environment=execution.get("environment", {}),
        )
    )
