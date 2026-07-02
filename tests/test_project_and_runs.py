from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from academic_harness.project import init_project
from academic_harness.runs import list_project_runs, rerun_validators, run_task


class ProjectAndRunTests(unittest.TestCase):
    def test_init_project_creates_template_and_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")

            self.assertTrue((project / "project.yaml").exists())
            self.assertTrue((project / "tasks" / "sample_task.yaml").exists())
            self.assertTrue((project / "validators" / "validate_report.py").exists())
            self.assertTrue((project / ".workbench" / "index.sqlite").exists())

    def test_fake_qoder_run_writes_manifest_artifacts_and_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            manifest = run_task(
                project / "tasks" / "sample_task.yaml",
                adapter="fake",
                run_id="run_test",
                project_root=project,
            )

            run_dir = Path(manifest["run_dir"])
            self.assertEqual(manifest["status"], "passed")
            self.assertTrue((run_dir / "report.md").exists())
            self.assertTrue((run_dir / "summary.md").exists())
            self.assertTrue((run_dir / "qoder" / "metadata.json").exists())
            self.assertTrue((run_dir / "validation" / "validate_report.json").exists())
            self.assertEqual(len(list_project_runs(project)), 1)

    def test_validator_failure_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            manifest = run_task(
                project / "tasks" / "sample_task.yaml",
                adapter="fake",
                run_id="run_missing_report",
                project_root=project,
            )
            report = Path(manifest["report_path"])
            report.unlink()

            updated = rerun_validators("run_missing_report", project)

            self.assertEqual(updated["status"], "failed")
            self.assertEqual(updated["validators"][0]["status"], "failed")

    def test_local_control_task_runs_without_prompt_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            manifest = run_task(
                project / "tasks" / "sample_local_control.yaml",
                adapter="auto",
                run_id="run_local_control",
                project_root=project,
            )

            run_dir = Path(manifest["run_dir"])
            self.assertEqual(manifest["status"], "passed")
            self.assertEqual(manifest["adapter"], "local_control")
            self.assertEqual(manifest["mode"], "local_control")
            self.assertTrue((run_dir / "qoder" / "artifacts" / "local_control_plan.json").exists())

    def test_cloud_experiment_fake_run_uses_v2_task_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            manifest = run_task(
                project / "tasks" / "sample_cloud_experiment.yaml",
                adapter="fake",
                run_id="run_cloud_fake",
                project_root=project,
            )

            self.assertEqual(manifest["status"], "passed")
            self.assertEqual(manifest["task_type"], "cloud_experiment")
            self.assertEqual(manifest["mode"], "fake")
            self.assertTrue(Path(manifest["report_path"]).exists())

    def test_cancelled_executor_skips_validators(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            qoder_dir = project / ".workbench" / "runs" / "run_cancelled" / "qoder"
            with patch("academic_harness.runs.run_executor") as executor:
                executor.return_value = {
                    "adapter": "qoder_cloud",
                    "mode": "full_cloud",
                    "status": "cancelled",
                    "qoder_dir": str(qoder_dir),
                }
                manifest = run_task(
                    project / "tasks" / "sample_cloud_experiment.yaml",
                    adapter="qoder_cloud",
                    run_id="run_cancelled",
                    project_root=project,
                )

            self.assertEqual(manifest["status"], "cancelled")
            self.assertEqual(manifest["validators"], [])


if __name__ == "__main__":
    unittest.main()
