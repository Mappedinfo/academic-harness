from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from academic_harness.project import init_project
from academic_harness.qoder_dependency import discover_qoder_runner, register_qoder_runner
from academic_harness.yamlio import dump_yaml, load_yaml


class QoderDependencyTests(unittest.TestCase):
    def test_registry_discovery_finds_runner_and_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = init_project(root / "demo")
            runner = _fake_runner(root / "bin" / "qoder-run")
            config = root / "config.local.json"
            config.write_text("{}", encoding="utf-8")
            registry = root / "registry.json"
            register_qoder_runner(
                executable_path=runner,
                config_path=config,
                profile="default",
                repo_path=None,
                source="test",
                registry_path=registry,
            )
            data = load_yaml(project / "project.yaml")
            data["qoder"].pop("runner_command", None)
            (project / "project.yaml").write_text(dump_yaml(data), encoding="utf-8")

            with patch.dict(os.environ, {"MAPPEDINFO_QODER_RUNNER_REGISTRY": str(registry)}):
                status = discover_qoder_runner(project, load_yaml(project / "project.yaml"), check_help=True)

        self.assertTrue(status["ok"])
        self.assertEqual(status["source"], "registry")
        self.assertEqual(Path(status["runner_path"]).name, "qoder-run")
        self.assertEqual(Path(status["config_path"]).name, "config.local.json")

    def test_project_runner_overrides_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = init_project(root / "demo")
            registry_runner = _fake_runner(root / "registry" / "qoder-run")
            project_runner = _fake_runner(root / "project" / "qoder-run")
            config = root / "config.local.json"
            config.write_text("{}", encoding="utf-8")
            registry = root / "registry.json"
            register_qoder_runner(
                executable_path=registry_runner,
                config_path=config,
                profile="default",
                repo_path=None,
                source="test",
                registry_path=registry,
            )
            data = load_yaml(project / "project.yaml")
            data["qoder"]["runner_command"] = str(project_runner)
            data["qoder"]["config"] = str(config)
            (project / "project.yaml").write_text(dump_yaml(data), encoding="utf-8")

            with patch.dict(os.environ, {"MAPPEDINFO_QODER_RUNNER_REGISTRY": str(registry)}):
                status = discover_qoder_runner(project, load_yaml(project / "project.yaml"), check_help=True)

        self.assertTrue(status["ok"])
        self.assertEqual(status["source"], "project")
        self.assertEqual(status["runner_path"], str(project_runner))

    def test_missing_runner_returns_install_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            empty_bin = Path(tmp) / "empty-bin"
            empty_bin.mkdir()

            with patch.dict(
                os.environ,
                {
                    "MAPPEDINFO_QODER_RUNNER_REGISTRY": str(Path(tmp) / "missing.json"),
                    "MAPPEDINFO_QODER_DISABLE_NEARBY": "1",
                    "PATH": str(empty_bin),
                },
            ):
                status = discover_qoder_runner(project, load_yaml(project / "project.yaml"), check_help=True)

        self.assertFalse(status["ok"])
        self.assertIsNone(status["runner_path"])
        self.assertIn("qoder install", status["install_hint"])


def _fake_runner(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nif [ \"$1\" = \"--help\" ]; then exit 0; fi\nexit 0\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


if __name__ == "__main__":
    unittest.main()
