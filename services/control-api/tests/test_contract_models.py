"""Os modelos Pydantic nao podem divergir dos JSON Schemas versionados.

Este teste percorre o manifesto de exemplos de I1-001 e exige que cada modelo aceite
todo exemplo valido e recuse todo exemplo invalido. Nao ha lista de casos duplicada
aqui: o manifesto e a fonte.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.models import SCHEMA_ID_TO_MODEL
from tests.conftest import load_example


def _cases(manifest: dict, *, valid: bool) -> list[tuple[str, str, str]]:
    return [
        (case["name"], case["schema"], case["document"])
        for case in manifest["cases"]
        if case["valid"] is valid
    ]


def test_manifest_cobre_todos_os_schemas(contract_manifest: dict) -> None:
    """Schema sem exemplo valido no manifesto passaria despercebido por este teste."""
    covered = {
        case["schema"] for case in contract_manifest["cases"] if case["valid"] is True
    }
    assert covered == set(SCHEMA_ID_TO_MODEL), (
        "cada schema precisa de pelo menos um exemplo valido no manifesto"
    )


def test_exemplos_validos_sao_aceitos(contract_manifest: dict) -> None:
    for name, schema_id, document in _cases(contract_manifest, valid=True):
        model = SCHEMA_ID_TO_MODEL.get(schema_id)
        assert model is not None, f"schema sem modelo mapeado: {schema_id}"
        try:
            model.model_validate(load_example(document))
        except ValidationError as error:  # pragma: no cover - mensagem de diagnostico
            pytest.fail(f"'{name}' deveria ser aceito por {model.__name__}: {error}")


def test_exemplos_invalidos_sao_recusados(contract_manifest: dict) -> None:
    for name, schema_id, document in _cases(contract_manifest, valid=False):
        model = SCHEMA_ID_TO_MODEL.get(schema_id)
        assert model is not None, f"schema sem modelo mapeado: {schema_id}"
        with pytest.raises(ValidationError):
            model.model_validate(load_example(document))
            pytest.fail(f"'{name}' deveria ser recusado por {model.__name__}")


def test_campo_extra_e_recusado() -> None:
    """`additionalProperties: false` precisa valer tambem no lado Python."""
    from app.contracts.models import CreateRunRequest

    payload = load_example("valid/create-run-request.json") | {"campo_inventado": 1}
    with pytest.raises(ValidationError):
        CreateRunRequest.model_validate(payload)
