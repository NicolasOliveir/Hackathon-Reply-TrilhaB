from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

import yaml


COMPOSE_PATH = Path(__file__).resolve().parents[1] / "compose.yaml"
WORKER_DOCKERFILE = (
    Path(__file__).resolve().parents[2] / "services" / "agent-worker" / "Dockerfile"
)
CONTROL_API_DOCKERFILE = (
    Path(__file__).resolve().parents[2] / "services" / "control-api" / "Dockerfile"
)
CONTROL_PANEL_DOCKERFILE = (
    Path(__file__).resolve().parents[2] / "apps" / "control-panel" / "Dockerfile"
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

    def test_only_control_api_receives_the_docker_socket(self) -> None:
        control_api = self.services["control-api"]
        self.assertIn(
            "/var/run/docker.sock:/var/run/docker.sock:ro",
            control_api["volumes"],
        )
        self.assertNotIn("/var/run/docker.sock", str(self.services["fake-worker"]))
        self.assertEqual(control_api["environment"]["RUNTIME_BACKEND"], "docker")
        self.assertEqual(control_api["environment"]["SCHEDULER_ENABLED"], "true")

    def test_control_api_uses_the_real_application_image(self) -> None:
        build = self.services["control-api"]["build"]
        self.assertEqual(build["context"], "..")
        self.assertEqual(build["dockerfile"], "services/control-api/Dockerfile")
        dockerfile = CONTROL_API_DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("app.main:app", dockerfile)
        self.assertIn("alembic upgrade head", dockerfile)

    def test_control_panel_uses_the_real_react_build(self) -> None:
        panel = self.services["control-panel"]
        self.assertEqual(panel["build"]["context"], "..")
        self.assertEqual(
            panel["build"]["dockerfile"], "apps/control-panel/Dockerfile"
        )
        self.assertNotIn("volumes", panel)
        dockerfile = CONTROL_PANEL_DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("npm run build", dockerfile)
        self.assertIn("/usr/share/nginx/html", dockerfile)

    def test_e2e_harness_is_profiled_and_has_no_control_network(self) -> None:
        harness = self.services["e2e"]
        self.assertEqual(harness["profiles"], ["e2e"])
        self.assertEqual(harness["networks"], ["public_net"])
        self.assertNotIn("control_net", harness["networks"])
        self.assertNotIn("/var/run/docker.sock", str(harness))

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
