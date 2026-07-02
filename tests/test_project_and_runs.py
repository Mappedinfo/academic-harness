from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()

