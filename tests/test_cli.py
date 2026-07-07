from __future__ import annotations

import json
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

            task_list = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "academic_harness",
                    "task",
                    "list",
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
            self.assertEqual(task_list.returncode, 0, task_list.stderr)
            tasks = json.loads(task_list.stdout)
            self.assertTrue(any(task["task_id"] == "sample_qoder_report" for task in tasks))

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

            run_json = subprocess.run(
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
                    "run_cli_json",
                    "--json",
                ],
                cwd=repo_root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(run_json.returncode, 0, run_json.stderr)
            run_manifest = json.loads(run_json.stdout)
            self.assertEqual(run_manifest["run_id"], "run_cli_json")
            self.assertEqual(run_manifest["status"], "passed")

            validate_json = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "academic_harness",
                    "validate",
                    "run_cli_json",
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
            self.assertEqual(validate_json.returncode, 0, validate_json.stderr)
            validated = json.loads(validate_json.stdout)
            self.assertEqual(validated["run_id"], "run_cli_json")
            self.assertEqual(validated["status"], "passed")

            trace_json = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "academic_harness",
                    "run",
                    "trace",
                    "run_cli_json",
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
            self.assertEqual(trace_json.returncode, 0, trace_json.stderr)
            trace = json.loads(trace_json.stdout)
            self.assertEqual(trace["run_id"], "run_cli_json")
            self.assertTrue(any(event["type"] == "state.enter" for event in trace["events"]))

            link_pi = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "academic_harness",
                    "run",
                    "link-pi",
                    "run_cli_json",
                    "--project",
                    str(project),
                    "--pi-session-id",
                    "pi_session_test",
                    "--pi-entry-id",
                    "pi_entry_test",
                    "--pi-session-file",
                    "/tmp/pi-session-test.jsonl",
                ],
                cwd=repo_root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(link_pi.returncode, 0, link_pi.stderr)
            linked = json.loads(link_pi.stdout)
            self.assertEqual(linked["pi"]["run_id"], "run_cli_json")
            self.assertEqual(linked["pi"]["pi_session_id"], "pi_session_test")
            self.assertEqual(linked["pi"]["pi_entry_id"], "pi_entry_test")
            self.assertEqual(linked["pi"]["pi_session_file"], "/tmp/pi-session-test.jsonl")

            linked_trace = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "academic_harness",
                    "run",
                    "trace",
                    "run_cli_json",
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
            self.assertEqual(linked_trace.returncode, 0, linked_trace.stderr)
            linked_trace_payload = json.loads(linked_trace.stdout)
            self.assertTrue(any(event["type"] == "pi.linked" for event in linked_trace_payload["events"]))

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

            disable_local_ai = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "academic_harness",
                    "project",
                    "set-local-ai",
                    "--project",
                    str(project),
                    "--enabled",
                    "false",
                ],
                cwd=repo_root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(disable_local_ai.returncode, 0, disable_local_ai.stderr)

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
