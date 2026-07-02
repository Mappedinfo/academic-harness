from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from academic_harness.executors.qoder_cloud import _EventExtractor, resolve_qoder_cloud_config
from academic_harness.project import init_project
from academic_harness.yamlio import dump_yaml, load_yaml


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


if __name__ == "__main__":
    unittest.main()
