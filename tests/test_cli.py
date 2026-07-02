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


if __name__ == "__main__":
    unittest.main()
