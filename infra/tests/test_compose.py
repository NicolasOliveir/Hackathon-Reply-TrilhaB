from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

import yaml


COMPOSE_PATH = Path(__file__).resolve().parents[1] / "compose.yaml"
WORKER_DOCKERFILE = (
    Path(__file__).resolve().parents[2] / "services" / "agent-worker" / "Dockerfile"
)


class ComposeTopologyTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with COMPOSE_PATH.open(encoding="utf-8") as source:
            cls.compose: dict[str, Any] = yaml.safe_load(source)
        cls.services = cls.compose["services"]

    def test_fixed_services_have_healthchecks(self) -> None:
        for service_name in {"control-api", "control-panel", "postgres"}:
            with self.subTest(service=service_name):
                self.assertIn(service_name, self.services)
                self.assertIn("healthcheck", self.services[service_name])

    def test_network_boundaries_match_architecture(self) -> None:
        self.assertEqual(self.services["postgres"]["networks"], ["control_net"])
        self.assertNotIn("ports", self.services["postgres"])
        self.assertEqual(
            set(self.services["control-api"]["networks"]),
            {"public_net", "control_net", "agent_net"},
        )
        self.assertEqual(self.services["control-panel"]["networks"], ["public_net"])
        self.assertEqual(self.services["fake-worker"]["networks"], ["agent_net"])
        self.assertTrue(self.compose["networks"]["control_net"]["internal"])
        self.assertTrue(self.compose["networks"]["agent_net"]["internal"])

    def test_worker_has_only_task_credentials_and_no_privileged_mounts(self) -> None:
        worker = self.services["fake-worker"]
        self.assertEqual(
            set(worker["environment"]),
            {"RUN_ID", "TASK_ID", "CONTROL_API_URL", "TASK_TOKEN"},
        )
        self.assertNotIn("DATABASE_URL", worker["environment"])
        self.assertNotIn("DOCKER_HOST", worker["environment"])
        self.assertEqual(worker.get("volumes", []), [])
        self.assertNotIn("/var/run/docker.sock", str(worker))
        self.assertTrue(worker["read_only"])
        self.assertEqual(worker["cap_drop"], ["ALL"])
        self.assertIn("no-new-privileges:true", worker["security_opt"])
        self.assertEqual(worker["profiles"], ["manual"])

    def test_declares_persistent_runtime_volumes(self) -> None:
        self.assertEqual(
            set(self.compose["volumes"]),
            {"postgres_data", "run_workspaces", "run_artifacts"},
        )

    def test_worker_image_declares_non_root_user(self) -> None:
        dockerfile = WORKER_DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("USER 10001:10001", dockerfile)
        self.assertNotIn("USER root", dockerfile)


if __name__ == "__main__":
    unittest.main()
