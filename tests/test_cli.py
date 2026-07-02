from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CLITests(unittest.TestCase):
    def test_cli_fake_run(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        env = {"PYTHONPATH": str(repo_root / "src")}
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "demo"
            init = subprocess.run(
                [sys.executable, "-m", "academic_harness", "init", str(project)],
                cwd=repo_root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(init.returncode, 0, init.stderr)

            run = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "academic_harness",
                    "task",
                    "run",
                    str(project / "tasks" / "sample_task.yaml"),
                    "--project",
                    str(project),
                    "--adapter",
                    "fake",
                    "--run-id",
                    "run_cli",
                ],
                cwd=repo_root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("run_id=run_cli", run.stdout)
            self.assertTrue((project / ".workbench" / "runs" / "run_cli" / "manifest.json").exists())

            status = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "academic_harness",
                    "project",
                    "status",
                    "--project",
                    str(project),
                    "--json",
                ],
                cwd=repo_root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn('"project"', status.stdout)
            self.assertIn('"qoder"', status.stdout)
            self.assertIn('"local_ai"', status.stdout)

            failed_hybrid = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "academic_harness",
                    "task",
                    "run",
                    str(project / "tasks" / "sample_cloud_experiment.yaml"),
                    "--project",
                    str(project),
                    "--adapter",
                    "hybrid",
                    "--run-id",
                    "run_hybrid_missing_local_ai",
                ],
                cwd=repo_root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(failed_hybrid.returncode, 1)
            self.assertIn("status=blocked", failed_hybrid.stdout)

            set_local_ai = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "academic_harness",
                    "project",
                    "set-local-ai",
                    "--project",
                    str(project),
                    "--enabled",
                    "true",
                    "--provider",
                    "ollama",
                    "--base-url",
                    "http://127.0.0.1:11434/v1",
                    "--model",
                    "qwen",
                    "--timeout-seconds",
                    "30",
                ],
                cwd=repo_root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(set_local_ai.returncode, 0, set_local_ai.stderr)
            self.assertIn('"local_ai"', set_local_ai.stdout)
            self.assertIn('"ok": true', set_local_ai.stdout)


if __name__ == "__main__":
    unittest.main()
