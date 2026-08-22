from __future__ import annotations

import json
import unittest
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


CONTRACTS_DIR = Path(__file__).resolve().parents[1]
SCHEMAS_DIR = CONTRACTS_DIR / "schemas" / "v1"
EXAMPLES_DIR = CONTRACTS_DIR / "examples" / "v1"
OPENAPI_PATH = CONTRACTS_DIR / "openapi" / "v1" / "openapi.yaml"
STATE_MACHINE_PATH = CONTRACTS_DIR / "state-machine" / "v1.json"


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def iter_refs(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref" and isinstance(child, str):
                yield child
            else:
                yield from iter_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_refs(child)


class ContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schemas = {
            schema["$id"]: schema
            for schema in (load_json(path) for path in sorted(SCHEMAS_DIR.glob("*.json")))
        }
        resources = (
            (schema_id, Resource.from_contents(schema))
            for schema_id, schema in cls.schemas.items()
        )
        cls.registry = Registry().with_resources(resources)

    def test_every_json_schema_is_valid_draft_2020_12(self) -> None:
        self.assertGreaterEqual(len(self.schemas), 6)
        for schema_id, schema in self.schemas.items():
            with self.subTest(schema=schema_id):
                self.assertEqual(
                    schema["$schema"],
                    "https://json-schema.org/draft/2020-12/schema",
                )
                Draft202012Validator.check_schema(schema)

    def test_manifest_examples_match_expected_validity(self) -> None:
        manifest = load_json(EXAMPLES_DIR / "manifest.json")
        self.assertEqual(manifest["contract_version"], "1.0.0")
        self.assertGreaterEqual(len(manifest["cases"]), 10)

        for case in manifest["cases"]:
            with self.subTest(case=case["name"]):
                schema = self.schemas[case["schema"]]
                document = load_json(EXAMPLES_DIR / case["document"])
                validator = Draft202012Validator(
                    schema,
                    registry=self.registry,
                    format_checker=FormatChecker(),
                )
                errors = list(validator.iter_errors(document))
                if case["valid"]:
                    self.assertEqual(errors, [], [error.message for error in errors])
                else:
                    self.assertNotEqual(errors, [], "invalid example unexpectedly passed")

    def test_openapi_uses_existing_canonical_schema_files(self) -> None:
        with OPENAPI_PATH.open(encoding="utf-8") as source:
            openapi = yaml.safe_load(source)

        self.assertEqual(openapi["openapi"], "3.1.0")
        expected_operations = {
            "createRun",
            "getRun",
            "streamRunEvents",
            "getTaskContext",
            "submitFakeWorkerOutput",
        }
        operation_ids = {
            operation["operationId"]
            for path_item in openapi["paths"].values()
            for method, operation in path_item.items()
            if method in {"get", "post", "put", "patch", "delete"}
        }
        self.assertEqual(operation_ids, expected_operations)

        referenced_files: set[Path] = set()
        for ref in iter_refs(openapi):
            if ref.startswith("#") or "://" in ref:
                continue
            target = (OPENAPI_PATH.parent / ref.split("#", maxsplit=1)[0]).resolve()
            self.assertTrue(target.is_file(), f"missing OpenAPI ref: {ref}")
            referenced_files.add(target)

        expected_files = {
            (SCHEMAS_DIR / name).resolve()
            for name in {
                "create-run-request.schema.json",
                "run-response.schema.json",
                "event-envelope.schema.json",
                "agent-task-context.schema.json",
                "fake-worker-output.schema.json",
            }
        }
        self.assertTrue(expected_files.issubset(referenced_files))

    def test_state_machine_is_deterministic_and_reaches_every_state(self) -> None:
        machine = load_json(STATE_MACHINE_PATH)
        common = self.schemas["https://reply.local/contracts/v1/common.schema.json"]
        states = set(common["$defs"]["runState"]["enum"])
        events = set(common["$defs"]["eventType"]["enum"])
        terminal_states = set(machine["terminal_states"])
        transitions = machine["transitions"]

        self.assertIn(machine["initial_state"], states)
        self.assertTrue(terminal_states.issubset(states))

        transition_keys = [(item["from"], item["event"]) for item in transitions]
        self.assertEqual(len(transition_keys), len(set(transition_keys)))
        for transition in transitions:
            self.assertIn(transition["from"], states)
            self.assertIn(transition["to"], states)
            self.assertIn(transition["event"], events)
            self.assertNotIn(transition["from"], terminal_states)

        reachable = {machine["initial_state"]}
        while True:
            next_states = {
                transition["to"]
                for transition in transitions
                if transition["from"] in reachable
            }
            expanded = reachable | next_states
            if expanded == reachable:
                break
            reachable = expanded

        self.assertEqual(reachable, states)


if __name__ == "__main__":
    unittest.main()
