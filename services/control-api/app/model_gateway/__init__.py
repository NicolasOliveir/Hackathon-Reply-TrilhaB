"""Gateway de modelo: unico ponto do sistema que fala com provedor LLM."""

from .base import (
    ModelGatewayError,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    ProviderNotConfigured,
    ProviderRefused,
)
from .gateway import ModelGateway, UsageTotals, usage_for_task
from .routing import ModelRouter, Route

__all__ = [
    "ModelGateway",
    "ModelGatewayError",
    "ModelProvider",
    "ModelRequest",
    "ModelResponse",
    "ModelRouter",
    "ModelUsage",
    "ProviderNotConfigured",
    "ProviderRefused",
    "Route",
    "UsageTotals",
    "usage_for_task",
]
