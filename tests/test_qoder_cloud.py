from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from academic_harness.executors.qoder_cloud import (
    QoderCloudConfig,
    QoderCloudError,
    QoderCloudHTTPError,
    _EventExtractor,
    _build_cloud_prompt,
    _managed_agent_state_path,
    ensure_managed_agent_set,
    resolve_qoder_cloud_config,
)
from academic_harness.kernel.trace_writer import write_qoder_thread_trace
from academic_harness.project import init_project
from academic_harness.yamlio import dump_yaml, load_yaml


class FakeManagedAgentClient:
    def __init__(self, models: list[dict] | None = None) -> None:
        self.created: list[tuple[dict, str | None]] = []
        self.updated: list[tuple[str, int, dict]] = []
        self.agents: dict[str, dict] = {}
        self.conflict_once_for: set[str] = set()
        self.models = models if models is not None else [{"id": "ultimate", "display_name": "Ultimate", "is_enabled": True}]

    def list_models(self) -> dict:
        return {"data": self.models, "has_more": False}

    def create_agent(self, payload: dict, idempotency_key: str | None = None) -> dict:
        agent_id = f"agent_{len(self.agents) + 1:04d}"
        agent = {"type": "agent", "id": agent_id, "version": 1, **payload}
        self.agents[agent_id] = agent
        self.created.append((payload, idempotency_key))
        return agent

    def get_agent(self, agent_id: str) -> dict:
        if agent_id not in self.agents:
            raise QoderCloudHTTPError(404, "not found")
        return self.agents[agent_id]

    def update_agent(self, agent_id: str, version: int, payload: dict) -> dict:
        if agent_id in self.conflict_once_for:
            self.conflict_once_for.remove(agent_id)
            self.agents[agent_id]["version"] = int(self.agents[agent_id]["version"]) + 1
            raise QoderCloudHTTPError(409, "conflict")
        current = self.get_agent(agent_id)
        updated = {**current, **payload, "id": agent_id, "version": int(current["version"]) + 1}
        self.agents[agent_id] = updated
        self.updated.append((agent_id, version, payload))
        return updated


class FailingManagedAgentClient:
    def list_models(self) -> dict:
        return {"data": [{"id": "ultimate", "display_name": "Ultimate", "is_enabled": True}]}

    def create_agent(self, payload: dict, idempotency_key: str | None = None) -> dict:
        raise QoderCloudError("create failed")


class QoderCloudConfigTests(unittest.TestCase):
    def test_resolves_profile_config_and_env_file_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            config = project / "qoder.config.local.json"
            config.write_text(
                """{
  "profiles": {
    "default": {
      "base_url": "https://api.qoder.com.cn/api/v1/cloud",
      "agent_id": "agent_test",
      "agent_version": "v1",
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
            project_yaml = project / "project.yaml"
            loaded = load_yaml(project_yaml)
            loaded["qoder"] = {"config": str(config), "profile": "default"}
            project_yaml.write_text(dump_yaml(loaded), encoding="utf-8")

            loaded = load_yaml(project_yaml)
            resolved = resolve_qoder_cloud_config(project, loaded, task={})

            self.assertEqual(resolved.base_url, "https://api.qoder.com.cn/api/v1/cloud")
            self.assertEqual(resolved.agent_id, "agent_test")
            self.assertEqual(resolved.agent_version, "v1")
            self.assertEqual(resolved.environment_id, "env_test")
            self.assertEqual(resolved.profile, "default")
            self.assertEqual(resolved.token, "test-token")

    def test_create_session_sends_agent_as_string_even_with_version(self) -> None:
        captured: list[dict] = []
        config = QoderCloudConfig(
            base_url="https://api.qoder.com.cn/api/v1/cloud",
            agent_id="agent_base",
            agent_version="1",
            environment_id="env_base",
            token="test-token",
            profile="default",
            config_path=None,
        )
        from academic_harness.executors.qoder_cloud import QoderCloudClient

        client = QoderCloudClient(config)

        def fake_request(
            method: str,
            path: str,
            payload: dict | None,
            extra_headers: dict[str, str] | None = None,
        ) -> dict:
            self.assertEqual(method, "POST")
            self.assertEqual(path, "sessions")
            self.assertIsNotNone(payload)
            captured.append(payload or {})
            return {"id": "sess_test"}

        client._request_json = fake_request  # type: ignore[method-assign]

        client.create_session(metadata={"run_id": "run_test"})

        self.assertEqual(captured[0]["agent"], "agent_base")
        self.assertEqual(captured[0]["environment_id"], "env_base")
        self.assertEqual(captured[0]["metadata"]["run_id"], "run_test")
        self.assertNotIn("agent_version", captured[0])

    def test_write_extractor_prefers_report_over_later_index_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            qoder_dir = Path(tmp) / "qoder"
            artifacts_dir = qoder_dir / "artifacts"
            artifacts_dir.mkdir(parents=True)
            extractor = _EventExtractor(qoder_dir, artifacts_dir)

            extractor.consume(
                {
                    "sse_event": "agent.tool_use",
                    "data": {
                        "type": "agent.tool_use",
                        "name": "Write",
                        "input": {"file_path": "/data/report.md", "content": "# Primary Report\n"},
                    },
                }
            )
            extractor.consume(
                {
                    "sse_event": "agent.tool_use",
                    "data": {
                        "type": "agent.tool_use",
                        "name": "Write",
                        "input": {"file_path": "/data/artifacts/README.md", "content": "# Artifact Index\n"},
                    },
                }
            )
            extractor.consume({"sse_event": "agent.message", "data": {"type": "agent.message", "content": "done"}})
            extractor.write_outputs()

            self.assertEqual((qoder_dir / "report.md").read_text(encoding="utf-8"), "# Primary Report\n")
            self.assertEqual((qoder_dir / "summary.md").read_text(encoding="utf-8"), "done")

    def test_waiting_message_is_not_report_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            qoder_dir = Path(tmp) / "qoder"
            artifacts_dir = qoder_dir / "artifacts"
            artifacts_dir.mkdir(parents=True)
            extractor = _EventExtractor(qoder_dir, artifacts_dir)

            extractor.consume(
                {
                    "sse_event": "agent.message",
                    "data": {
                        "type": "agent.message",
                        "content": "All three worker agents have been dispatched. Waiting for results from all workers...",
                    },
                }
            )
            extractor.write_outputs()

            self.assertFalse((qoder_dir / "report.md").exists())
            self.assertTrue((qoder_dir / "summary.md").exists())

    def test_session_error_is_recorded_without_fake_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            qoder_dir = Path(tmp) / "qoder"
            artifacts_dir = qoder_dir / "artifacts"
            artifacts_dir.mkdir(parents=True)
            extractor = _EventExtractor(qoder_dir, artifacts_dir)

            waiting_record = {
                "sse_event": "agent.message",
                "id": "evt_waiting",
                "data": {
                    "type": "agent.message",
                    "content": "All three workers are running. Polling for their responses.",
                },
            }
            error_record = {
                "sse_event": "session.error",
                "id": "evt_error",
                "data": {
                    "type": "session.error",
                    "error": {
                        "type": "unknown_error",
                        "message": "model provider error: FORBIDDEN: billing daily count exceeded",
                    },
                },
            }

            extractor.consume(waiting_record)
            extractor.consume(error_record)
            extractor.write_outputs()
            summary = extractor.summary()

            self.assertTrue(extractor.is_terminal_error(error_record))
            self.assertFalse((qoder_dir / "report.md").exists())
            self.assertEqual(summary["errors"][0]["message"], "model provider error: FORBIDDEN: billing daily count exceeded")

    def test_managed_agent_thread_events_write_delegation_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            qoder_dir = Path(tmp) / "qoder"
            qoder_dir.mkdir()
            summary = write_qoder_thread_trace(
                "run_trace",
                qoder_dir,
                [
                    {
                        "type": "session.thread_created",
                        "session_thread_id": "sthr_child",
                        "agent_name": "Evidence Worker",
                        "processed_at": "2026-07-02T00:00:00Z",
                    },
                    {
                        "type": "agent.thread_message_sent",
                        "to_session_thread_id": "sthr_child",
                        "to_agent_name": "Evidence Worker",
                        "text_excerpt": "Collect evidence",
                        "processed_at": "2026-07-02T00:00:01Z",
                    },
                    {
                        "type": "agent.thread_message_received",
                        "from_session_thread_id": "sthr_child",
                        "from_agent_name": "Evidence Worker",
                        "text_excerpt": "Evidence result",
                        "processed_at": "2026-07-02T00:00:02Z",
                    },
                    {
                        "type": "session.thread_status_idle",
                        "session_thread_id": "sthr_child",
                        "agent_name": "Evidence Worker",
                        "processed_at": "2026-07-02T00:00:03Z",
                    },
                ],
            )

            self.assertEqual(summary["thread_count"], 1)
            self.assertEqual(summary["delegation_count"], 1)
            delegation = (qoder_dir / "delegations.jsonl").read_text(encoding="utf-8")
            self.assertIn('"run_id": "run_trace"', delegation)
            self.assertIn('"task_excerpt": "Collect evidence"', delegation)
            self.assertIn('"result_excerpt": "Evidence result"', delegation)
            self.assertTrue((qoder_dir / "threads.json").exists())

    def test_ensure_managed_agent_set_creates_default_four_agent_roster(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = init_project(Path(tmp) / "demo")
            project = load_yaml(project_root / "project.yaml")
            task = load_yaml(project_root / "tasks" / "sample_cloud_experiment.yaml")
            config = QoderCloudConfig(
                base_url="https://api.qoder.com.cn/api/v1/cloud",
                agent_id="agent_base",
                environment_id="env_base",
                token="test-token",
                profile="default",
                config_path=None,
                managed_agents={"enabled": True, "total_agents": 4},
            )
            client = FakeManagedAgentClient()

            runtime = ensure_managed_agent_set(project_root, project, task, client, config)  # type: ignore[arg-type]

            self.assertTrue(runtime["active"])
            self.assertEqual(len(client.created), 4)
            self.assertEqual(len(runtime["workers"]), 3)
            self.assertEqual(runtime["delegation_strategy"], "agent_sync")
            self.assertTrue(runtime["schema_ok"])
            self.assertEqual(runtime["agent_count"], 4)
            self.assertFalse(runtime["include_self"])
            for worker_payload, _ in client.created[:-1]:
                self.assertNotIn("multiagent", worker_payload)
                self.assertIn("send_to_parent", worker_payload["system"])
            coordinator_payload = client.created[-1][0]
            self.assertIn("multiagent", coordinator_payload)
            self.assertEqual(coordinator_payload["multiagent"]["type"], "coordinator")
            self.assertEqual(len(coordinator_payload["multiagent"]["agents"]), 3)
            self.assertEqual(
                {entry["id"] for entry in coordinator_payload["multiagent"]["agents"]},
                {worker["id"] for worker in runtime["workers"]},
            )
            for entry in coordinator_payload["multiagent"]["agents"]:
                self.assertEqual(entry["type"], "agent")
                self.assertIsInstance(entry["version"], int)
                self.assertGreater(entry["version"], 0)
                self.assertTrue(entry["name"])
            self.assertEqual(coordinator_payload["tools"][0]["type"], "agent_toolset_20260401")
            self.assertFalse(
                {"Agent", "create_agent", "send_to_agent", "list_agents"}.intersection(
                    set(coordinator_payload["tools"][0].get("enabled_tools", []))
                )
            )
            self.assertIn("injected tool named exactly Agent", coordinator_payload["system"])
            self.assertIn("Before any WebSearch", coordinator_payload["system"])
            self.assertIn("bounded one-response task", coordinator_payload["system"])
            prompt = _build_cloud_prompt(project_root, project, task, "run_test", runtime)
            self.assertIn("Delegation strategy: agent_sync", prompt)
            self.assertIn("injected tool named exactly Agent", prompt)
            self.assertIn("Before any WebSearch", prompt)
            self.assertIn("bounded one-response tasks", prompt)
            self.assertTrue(_managed_agent_state_path(project_root).exists())

    def test_ensure_managed_agent_set_auto_selects_first_available_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = init_project(Path(tmp) / "demo")
            project = load_yaml(project_root / "project.yaml")
            task = load_yaml(project_root / "tasks" / "sample_cloud_experiment.yaml")
            config = QoderCloudConfig(
                base_url="https://api.qoder.com.cn/api/v1/cloud",
                agent_id="agent_base",
                environment_id="env_base",
                token="test-token",
                profile="default",
                config_path=None,
                managed_agents={"enabled": True, "total_agents": 4},
            )
            client = FakeManagedAgentClient(
                models=[{"id": "cn-research", "display_name": "CN Research", "is_enabled": True}]
            )

            runtime = ensure_managed_agent_set(project_root, project, task, client, config)  # type: ignore[arg-type]

            self.assertTrue(runtime["active"])
            self.assertEqual(runtime["resolved_model"], "cn-research")
            self.assertEqual(runtime["model_source"], "auto_first_concrete")
            self.assertTrue(all(payload["model"] == "cn-research" for payload, _ in client.created))

    def test_multiagent_schema_can_include_self_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = init_project(Path(tmp) / "demo")
            project = load_yaml(project_root / "project.yaml")
            task = load_yaml(project_root / "tasks" / "sample_cloud_experiment.yaml")
            config = QoderCloudConfig(
                base_url="https://api.qoder.com.cn/api/v1/cloud",
                agent_id="agent_base",
                environment_id="env_base",
                token="test-token",
                profile="default",
                config_path=None,
                managed_agents={"enabled": True, "total_agents": 3, "include_self": True},
            )
            client = FakeManagedAgentClient()

            runtime = ensure_managed_agent_set(project_root, project, task, client, config)  # type: ignore[arg-type]
            coordinator_payload = client.created[-1][0]
            entries = coordinator_payload["multiagent"]["agents"]

            self.assertTrue(runtime["include_self"])
            self.assertEqual(len(entries), 3)
            self.assertEqual(entries[-1], {"type": "self"})
            self.assertTrue(runtime["schema_ok"])

    def test_child_threads_strategy_keeps_create_agent_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = init_project(Path(tmp) / "demo")
            project = load_yaml(project_root / "project.yaml")
            task = load_yaml(project_root / "tasks" / "sample_cloud_experiment.yaml")
            config = QoderCloudConfig(
                base_url="https://api.qoder.com.cn/api/v1/cloud",
                agent_id="agent_base",
                environment_id="env_base",
                token="test-token",
                profile="default",
                config_path=None,
                managed_agents={"enabled": True, "total_agents": 4, "delegation_strategy": "child_threads"},
            )
            client = FakeManagedAgentClient()

            runtime = ensure_managed_agent_set(project_root, project, task, client, config)  # type: ignore[arg-type]
            coordinator_payload = client.created[-1][0]
            prompt = _build_cloud_prompt(project_root, project, task, "run_test", runtime)

            self.assertEqual(runtime["delegation_strategy"], "child_threads")
            self.assertIn("Use the injected create_agent tool", coordinator_payload["system"])
            self.assertIn("Delegation strategy: child_threads", prompt)
            self.assertIn("Use create_agent to create one child thread", prompt)

    def test_ensure_managed_agent_set_auto_prefers_concrete_qoder_model_over_auto(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = init_project(Path(tmp) / "demo")
            project = load_yaml(project_root / "project.yaml")
            task = load_yaml(project_root / "tasks" / "sample_cloud_experiment.yaml")
            config = QoderCloudConfig(
                base_url="https://api.qoder.com.cn/api/v1/cloud",
                agent_id="agent_base",
                environment_id="env_base",
                token="test-token",
                profile="default",
                config_path=None,
                managed_agents={"enabled": True, "total_agents": 4},
            )
            client = FakeManagedAgentClient(
                models=[
                    {"id": "auto", "display_name": "Auto", "is_enabled": True},
                    {"id": "qmodel_latest", "display_name": "Qwen Max", "is_enabled": True},
                ]
            )

            runtime = ensure_managed_agent_set(project_root, project, task, client, config)  # type: ignore[arg-type]

            self.assertEqual(runtime["resolved_model"], "qmodel_latest")
            self.assertEqual(runtime["model_source"], "auto_preferred")
            self.assertTrue(all(payload["model"] == "qmodel_latest" for payload, _ in client.created))

    def test_ensure_managed_agent_set_falls_back_when_model_list_empty_unless_strict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = init_project(Path(tmp) / "demo")
            project = load_yaml(project_root / "project.yaml")
            task = load_yaml(project_root / "tasks" / "sample_cloud_experiment.yaml")
            config = QoderCloudConfig(
                base_url="https://api.qoder.com.cn/api/v1/cloud",
                agent_id="agent_base",
                environment_id="env_base",
                token="test-token",
                profile="default",
                config_path=None,
                managed_agents={"enabled": True, "total_agents": 4},
            )

            runtime = ensure_managed_agent_set(
                project_root,
                project,
                task,
                FakeManagedAgentClient(models=[]),  # type: ignore[arg-type]
                config,
            )

            self.assertFalse(runtime["active"])
            self.assertEqual(runtime["fallback"], "single_agent")
            self.assertIn("no enabled Qoder models", runtime["error"])

            strict = QoderCloudConfig(
                base_url=config.base_url,
                agent_id=config.agent_id,
                environment_id=config.environment_id,
                token=config.token,
                profile=config.profile,
                config_path=None,
                managed_agents={"enabled": True, "require_managed_agents": True},
            )
            with self.assertRaises(QoderCloudError):
                ensure_managed_agent_set(
                    project_root,
                    project,
                    task,
                    FakeManagedAgentClient(models=[]),  # type: ignore[arg-type]
                    strict,
                )

    def test_ensure_managed_agent_set_rejects_explicit_unavailable_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = init_project(Path(tmp) / "demo")
            project = load_yaml(project_root / "project.yaml")
            task = load_yaml(project_root / "tasks" / "sample_cloud_experiment.yaml")
            config = QoderCloudConfig(
                base_url="https://api.qoder.com.cn/api/v1/cloud",
                agent_id="agent_base",
                environment_id="env_base",
                token="test-token",
                profile="default",
                config_path=None,
                managed_agents={"enabled": True, "model": "ultimate"},
            )

            with self.assertRaisesRegex(QoderCloudError, "available models: cn-research"):
                ensure_managed_agent_set(
                    project_root,
                    project,
                    task,
                    FakeManagedAgentClient(
                        models=[{"id": "cn-research", "display_name": "CN Research", "is_enabled": True}]
                    ),  # type: ignore[arg-type]
                    config,
                )

    def test_ensure_managed_agent_set_reuses_matching_local_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = init_project(Path(tmp) / "demo")
            project = load_yaml(project_root / "project.yaml")
            task = load_yaml(project_root / "tasks" / "sample_cloud_experiment.yaml")
            config = QoderCloudConfig(
                base_url="https://api.qoder.com.cn/api/v1/cloud",
                agent_id="agent_base",
                environment_id="env_base",
                token="test-token",
                profile="default",
                config_path=None,
                managed_agents={"enabled": True, "total_agents": 4},
            )
            first_client = FakeManagedAgentClient()
            ensure_managed_agent_set(project_root, project, task, first_client, config)  # type: ignore[arg-type]
            second_client = FakeManagedAgentClient()

            runtime = ensure_managed_agent_set(project_root, project, task, second_client, config)  # type: ignore[arg-type]

            self.assertTrue(runtime["reused"])
            self.assertEqual(second_client.created, [])
            self.assertEqual(second_client.updated, [])

    def test_ensure_managed_agent_set_retries_version_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = init_project(Path(tmp) / "demo")
            project = load_yaml(project_root / "project.yaml")
            task = load_yaml(project_root / "tasks" / "sample_cloud_experiment.yaml")
            config = QoderCloudConfig(
                base_url="https://api.qoder.com.cn/api/v1/cloud",
                agent_id="agent_base",
                environment_id="env_base",
                token="test-token",
                profile="default",
                config_path=None,
                managed_agents={"enabled": True, "total_agents": 4},
            )
            client = FakeManagedAgentClient()
            ensure_managed_agent_set(project_root, project, task, client, config)  # type: ignore[arg-type]
            state = _managed_agent_state_path(project_root)
            self.assertTrue(state.exists())

            data = load_yaml(project_root / "project.yaml")
            data["title"] = "Changed Demo"
            project = data
            conflicted_agent_id = next(iter(client.agents))
            client.conflict_once_for.add(conflicted_agent_id)

            runtime = ensure_managed_agent_set(project_root, project, task, client, config)  # type: ignore[arg-type]

            self.assertTrue(runtime["active"])
            self.assertGreater(len(client.updated), 0)
            self.assertTrue(any(update[0] == conflicted_agent_id for update in client.updated))

    def test_ensure_managed_agent_set_falls_back_unless_strict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = init_project(Path(tmp) / "demo")
            project = load_yaml(project_root / "project.yaml")
            task = load_yaml(project_root / "tasks" / "sample_cloud_experiment.yaml")
            config = QoderCloudConfig(
                base_url="https://api.qoder.com.cn/api/v1/cloud",
                agent_id="agent_base",
                environment_id="env_base",
                token="test-token",
                profile="default",
                config_path=None,
                managed_agents={"enabled": True, "total_agents": 4},
            )

            runtime = ensure_managed_agent_set(project_root, project, task, FailingManagedAgentClient(), config)  # type: ignore[arg-type]

            self.assertFalse(runtime["active"])
            self.assertEqual(runtime["fallback"], "single_agent")

            strict = QoderCloudConfig(
                base_url=config.base_url,
                agent_id=config.agent_id,
                environment_id=config.environment_id,
                token=config.token,
                profile=config.profile,
                config_path=None,
                managed_agents={"enabled": True, "require_managed_agents": True},
            )
            with self.assertRaises(QoderCloudError):
                ensure_managed_agent_set(project_root, project, task, FailingManagedAgentClient(), strict)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
