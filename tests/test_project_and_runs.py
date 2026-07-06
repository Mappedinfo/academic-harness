from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from academic_harness.project import init_project
from academic_harness.runs import list_project_runs, rerun_validators, run_task
from academic_harness.yamlio import read_json
from academic_harness.yamlio import dump_yaml, load_yaml


class FakeHybridLocalAIClient:
    def __init__(self, config) -> None:
        self.config = config
        self.calls = 0

    def chat(self, messages, temperature: float = 0.2) -> str:
        self.calls += 1
        if self.calls == 1:
            return """{
  "prompt_review": "Prompt is ready for cloud dispatch.",
  "cloud_prompt": "Cloud prompt from local preflight."
}"""
        return """{
  "final_report": "# Final Hybrid Report\\n\\nIntegrated locally.",
  "review": "Local review passed.",
  "summary": "Hybrid summary.",
  "validator_notes": {"status": "passed"}
}"""


def fake_qoder_cloud(project_root, project, task, run_id, run_dir):
    qoder_dir = run_dir / "qoder"
    qoder_dir.mkdir(parents=True, exist_ok=True)
    (qoder_dir / "report.md").write_text("# Qoder Report\n\nCloud body.\n", encoding="utf-8")
    (qoder_dir / "summary.md").write_text("Qoder summary.\n", encoding="utf-8")
    (qoder_dir / "metadata.json").write_text('{"status":"succeeded"}\n', encoding="utf-8")
    (qoder_dir / "events.sse").write_text("", encoding="utf-8")
    (qoder_dir / "events.jsonl").write_text("", encoding="utf-8")
    (qoder_dir / "session.json").write_text('{"id":"sess_test"}\n', encoding="utf-8")
    artifacts_dir = qoder_dir / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    (artifacts_dir / "cloud_artifact.md").write_text("# Cloud Artifact\n", encoding="utf-8")
    return {
        "adapter": "qoder_cloud",
        "mode": "full_cloud",
        "status": "succeeded",
        "qoder_dir": str(qoder_dir),
        "session_id": "sess_test",
    }


def configure_qoder(project: Path) -> None:
    config = project / "qoder.local.json"
    config.write_text(
        """{
  "profiles": {
    "default": {
      "base_url": "https://api.qoder.com.cn/api/v1/cloud",
      "agent_id": "agent_test",
      "environment_id": "env_test",
      "token_env": "TEST_QODER_TOKEN",
      "env_file": ".env"
    }
  }
}
""",
        encoding="utf-8",
    )
    (project / ".env").write_text("TEST_QODER_TOKEN=test-token\n", encoding="utf-8")
    data = load_yaml(project / "project.yaml")
    data["qoder"]["config"] = "qoder.local.json"
    data["qoder"]["runner_command"] = "/bin/echo"
    (project / "project.yaml").write_text(dump_yaml(data), encoding="utf-8")


class ProjectAndRunTests(unittest.TestCase):
    def test_init_project_creates_template_and_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")

            self.assertTrue((project / "project.yaml").exists())
            self.assertTrue((project / "tasks" / "sample_task.yaml").exists())
            self.assertTrue((project / "tasks" / "sample_lan_traffic_experiment.yaml").exists())
            self.assertTrue((project / "variables" / "registry.yaml").exists())
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
            self.assertTrue((run_dir / "artifacts.json").exists())
            self.assertTrue((run_dir / "trace.jsonl").exists())
            self.assertTrue((run_dir / "validation" / "artifact_contract.json").exists())
            self.assertTrue((run_dir / "validation" / "validate_report.json").exists())
            self.assertEqual(manifest["state"], "passed")
            self.assertEqual(manifest["policy"]["preflight"]["decision"], "allow")
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

    def test_lan_experiment_requires_lan_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            manifest = run_task(
                project / "tasks" / "sample_lan_traffic_experiment.yaml",
                adapter="lan",
                run_id="run_lan_blocked",
                project_root=project,
            )

            self.assertEqual(manifest["status"], "blocked")
            self.assertIn("LAN experiment requested", manifest["error"])

    def test_lan_experiment_collects_remote_report_and_registries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            data = load_yaml(project / "project.yaml")
            data["lan"] = {
                "enabled": True,
                "server": "dev-container",
                "project_root": "/remote/demo",
                "ssh_alias": "docker-dev",
            }
            (project / "project.yaml").write_text(dump_yaml(data), encoding="utf-8")
            import subprocess

            real_subprocess_run = subprocess.run

            def fake_run(command, capture_output=True, text=True, check=False, **kwargs):
                class Completed:
                    returncode = 0
                    stdout = ""
                    stderr = ""

                if command[0] == "ssh":
                    return Completed()
                if command[0] == "scp":
                    if str(command[1]).startswith("docker-dev:"):
                        target = Path(command[2])
                        target.parent.mkdir(parents=True, exist_ok=True)
                        name = target.name
                        if name == "report.md":
                            target.write_text("# Remote LAN Report\n", encoding="utf-8")
                        elif name == "summary.md":
                            target.write_text("Remote summary\n", encoding="utf-8")
                        elif name.endswith(".json"):
                            target.write_text("{}\n", encoding="utf-8")
                        else:
                            target.write_text("figures:\n", encoding="utf-8")
                    return Completed()

                return real_subprocess_run(command, capture_output=capture_output, text=text, check=check, **kwargs)

            with patch("academic_harness.executors.lan.subprocess.run", side_effect=fake_run):
                manifest = run_task(
                    project / "tasks" / "sample_lan_traffic_experiment.yaml",
                    adapter="lan",
                    run_id="run_lan",
                    project_root=project,
                )

            run_dir = Path(manifest["run_dir"])
            self.assertEqual(manifest["status"], "passed")
            self.assertEqual(manifest["adapter"], "lan")
            self.assertEqual(manifest["mode"], "lan_control")
            self.assertTrue((run_dir / "report.md").exists())
            self.assertTrue((run_dir / "lan" / "artifacts" / "variables.json").exists())
            self.assertTrue((run_dir / "lan" / "figures" / "registry.yaml").exists())

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

    def test_task_run_options_apply_managed_agent_override_without_editing_task_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            task_path = project / "tasks" / "sample_cloud_experiment.yaml"
            original = task_path.read_text(encoding="utf-8")
            manifest = run_task(
                task_path,
                adapter="fake",
                run_id="run_options",
                project_root=project,
                run_options={
                    "managed_agents": "on",
                    "managed_agent_count": 5,
                    "require_managed_agents": True,
                    "delegation_strategy": "child_threads",
                },
            )

            self.assertEqual(manifest["task"]["managed_agents"]["enabled"], True)
            self.assertEqual(manifest["task"]["managed_agents"]["total_agents"], 5)
            self.assertEqual(manifest["task"]["managed_agents"]["require_managed_agents"], True)
            self.assertEqual(manifest["task"]["managed_agents"]["delegation_strategy"], "child_threads")
            self.assertEqual(task_path.read_text(encoding="utf-8"), original)

    def test_cancelled_executor_skips_validators(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            configure_qoder(project)
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

    def test_failed_executor_skips_validators(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            configure_qoder(project)
            data = load_yaml(project / "project.yaml")
            data["local_ai"]["enabled"] = True
            data["local_ai"]["model"] = "fake-local"
            (project / "project.yaml").write_text(dump_yaml(data), encoding="utf-8")
            with patch("academic_harness.runs.run_executor") as executor:
                executor.return_value = {
                    "adapter": "hybrid",
                    "mode": "hybrid",
                    "status": "failed",
                    "run_dir": str(project / ".workbench" / "runs" / "run_failed"),
                }
                manifest = run_task(
                    project / "tasks" / "sample_cloud_experiment.yaml",
                    adapter="hybrid",
                    run_id="run_failed",
                    project_root=project,
                )

            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["validators"], [])

    def test_hybrid_executor_runs_local_preflight_qoder_and_local_postflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            configure_qoder(project)
            data = load_yaml(project / "project.yaml")
            data["local_ai"] = {
                "enabled": True,
                "provider": "openai_compatible",
                "base_url": "http://127.0.0.1:11434/v1",
                "model": "fake-local",
            }
            (project / "project.yaml").write_text(dump_yaml(data), encoding="utf-8")

            with patch("academic_harness.executors.hybrid.LocalAIClient", FakeHybridLocalAIClient):
                with patch("academic_harness.executors.hybrid.run_qoder_cloud", fake_qoder_cloud):
                    manifest = run_task(
                        project / "tasks" / "sample_cloud_experiment.yaml",
                        adapter="hybrid",
                        run_id="run_hybrid",
                        project_root=project,
                    )

            run_dir = Path(manifest["run_dir"])
            self.assertEqual(manifest["status"], "passed")
            self.assertEqual(manifest["adapter"], "hybrid")
            self.assertEqual((run_dir / "report.md").read_text(encoding="utf-8"), "# Final Hybrid Report\n\nIntegrated locally.\n")
            self.assertTrue((run_dir / "local_ai" / "preflight.json").exists())
            self.assertTrue((run_dir / "local_ai" / "risk_report.md").exists())
            self.assertTrue((run_dir / "local_ai" / "prompt_patch.md").exists())
            self.assertTrue((run_dir / "local_ai" / "policy_warnings.json").exists())
            self.assertTrue((run_dir / "local_ai" / "review.md").exists())
            self.assertTrue((run_dir / "local_ai" / "audit_report.md").exists())
            self.assertTrue((run_dir / "local_ai" / "artifact_summary.md").exists())
            self.assertTrue((run_dir / "local_ai" / "suspected_issues.json").exists())
            self.assertTrue((run_dir / "qoder" / "report.md").exists())

    def test_policy_denies_full_cloud_private_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            configure_qoder(project)
            task_path = project / "tasks" / "private_cloud.yaml"
            task = load_yaml(project / "tasks" / "sample_cloud_experiment.yaml")
            task["input"] = {"prompt_file": str(Path(tmp) / "private-data" / "prompt.md")}
            task_path.write_text(dump_yaml(task), encoding="utf-8")

            manifest = run_task(task_path, adapter="qoder_cloud", run_id="run_policy_private", project_root=project)

            self.assertEqual(manifest["status"], "blocked")
            self.assertEqual(manifest["state"], "blocked")
            self.assertIn("allow_private_data=false", manifest["error"])
            self.assertEqual(manifest["policy"]["preflight"]["decision"], "deny")

    def test_policy_asks_on_adapter_mode_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            configure_qoder(project)
            task_path = project / "tasks" / "sample_cloud_experiment.yaml"

            manifest = run_task(task_path, adapter="local_control", run_id="run_policy_ask", project_root=project)

            self.assertEqual(manifest["status"], "awaiting_approval")
            self.assertEqual(manifest["state"], "awaiting_approval")
            self.assertIn("adapter_mode_mismatch", manifest["policy"]["preflight"]["required_approvals"])

    def test_artifact_contract_failure_prevents_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            task_path = project / "tasks" / "sample_task.yaml"
            task = load_yaml(task_path)
            task["output"]["expected"] = ["report.md", "summary.md", "missing.json"]
            task_path.write_text(dump_yaml(task), encoding="utf-8")

            manifest = run_task(task_path, adapter="fake", run_id="run_missing_artifact", project_root=project)
            artifact_contract = read_json(Path(manifest["run_dir"]) / "validation" / "artifact_contract.json")

            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(artifact_contract["status"], "failed")
            self.assertTrue(any(check["name"] == "expected:missing.json" for check in artifact_contract["checks"]))

    def test_local_validator_non_json_stdout_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            validator = project / "validators" / "bad_validator.py"
            validator.write_text("print('not json')\n", encoding="utf-8")
            task_path = project / "tasks" / "sample_task.yaml"
            task = load_yaml(task_path)
            task["validators"] = ["validators/bad_validator.py"]
            task_path.write_text(dump_yaml(task), encoding="utf-8")

            manifest = run_task(task_path, adapter="fake", run_id="run_bad_validator", project_root=project)

            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["validators"][0]["validator"], "artifact_contract")
            self.assertEqual(manifest["validators"][0]["status"], "passed")
            self.assertEqual(manifest["validators"][1]["status"], "failed")
            self.assertIn("not JSON", manifest["validators"][1]["error"])


if __name__ == "__main__":
    unittest.main()
