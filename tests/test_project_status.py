from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from academic_harness.project import init_project, project_status, reset_qoder_config, set_lan_config, set_qoder_config
from academic_harness.yamlio import dump_yaml, load_yaml


class ProjectStatusTests(unittest.TestCase):
    def test_missing_project_status_is_structured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            status = project_status(Path(tmp) / "missing")

        self.assertFalse(status["ok"])
        self.assertFalse(status["checks"]["project"]["ok"])
        self.assertIn("project.yaml missing", status["checks"]["project"]["message"])

    def test_valid_project_status_checks_qoder_config_and_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            qoder_config = project / "qoder.local.json"
            qoder_config.write_text("{}", encoding="utf-8")
            data = load_yaml(project / "project.yaml")
            data["qoder"]["runner_command"] = "/bin/echo"
            data["qoder"]["config"] = "qoder.local.json"
            (project / "project.yaml").write_text(dump_yaml(data), encoding="utf-8")

            status = project_status(project)

        self.assertTrue(status["ok"])
        self.assertTrue(status["checks"]["tasks"]["ok"])
        self.assertTrue(status["checks"]["qoder"]["ok"])
        self.assertEqual(status["checks"]["qoder"]["config_path"].split("/")[-1], "qoder.local.json")

    def test_missing_qoder_config_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            data = load_yaml(project / "project.yaml")
            data["qoder"]["runner_command"] = "/bin/echo"
            data["qoder"]["config"] = "missing.local.json"
            (project / "project.yaml").write_text(dump_yaml(data), encoding="utf-8")

            status = project_status(project)

        self.assertFalse(status["checks"]["qoder"]["ok"])
        self.assertIn("config missing", status["checks"]["qoder"]["message"])

    def test_missing_tasks_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            for task in (project / "tasks").glob("*.yaml"):
                task.unlink()

            status = project_status(project)

        self.assertFalse(status["checks"]["tasks"]["ok"])
        self.assertIn("no task yaml", status["checks"]["tasks"]["message"])

    def test_lan_config_writer_preserves_project_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            status = set_lan_config(
                project,
                server="lab-gpu-01",
                project_root="/data/projects/demo",
                ssh_alias="lab-gpu-01",
                enabled=True,
            )
            data = load_yaml(project / "project.yaml")

        self.assertEqual(data["project_id"], "demo")
        self.assertEqual(data["qoder"]["profile"], "default")
        self.assertEqual(data["lan"]["server"], "lab-gpu-01")
        self.assertEqual(data["lan"]["project_root"], "/data/projects/demo")
        self.assertEqual(data["lan"]["ssh_alias"], "lab-gpu-01")
        self.assertTrue(data["lan"]["enabled"])
        self.assertTrue(status["checks"]["lan"]["ok"])

    def test_default_and_reset_qoder_config_use_system_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            data = load_yaml(project / "project.yaml")
            self.assertNotIn("runner_command", data["qoder"])
            self.assertNotIn("config", data["qoder"])

            data["qoder"]["runner_command"] = "/bin/echo"
            data["qoder"]["config"] = "qoder.local.json"
            (project / "project.yaml").write_text(dump_yaml(data), encoding="utf-8")
            reset_qoder_config(project)
            reset_data = load_yaml(project / "project.yaml")

        self.assertEqual(reset_data["qoder"], {"profile": "default"})

    def test_qoder_config_writer_preserves_project_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            qoder_config = project / "qoder.local.json"
            qoder_config.write_text("{}", encoding="utf-8")
            status = set_qoder_config(
                project,
                runner_command="/bin/echo",
                config="qoder.local.json",
                profile="research",
            )
            data = load_yaml(project / "project.yaml")

        self.assertEqual(data["project_id"], "demo")
        self.assertEqual(data["qoder"]["runner_command"], "/bin/echo")
        self.assertEqual(data["qoder"]["config"], "qoder.local.json")
        self.assertEqual(data["qoder"]["profile"], "research")
        self.assertTrue(status["checks"]["qoder"]["ok"])


if __name__ == "__main__":
    unittest.main()
