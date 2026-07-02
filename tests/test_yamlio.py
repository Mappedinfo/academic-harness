from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from academic_harness.yamlio import load_yaml


class YAMLIOTests(unittest.TestCase):
    def test_loads_nested_v1_task_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "task.yaml"
            path.write_text(
                """
task_id: lit_review_001
type: qoder_research
input:
  prompt_file: tasks/prompt.md
output:
  expected:
    - report.md
    - summary.md
policy:
  allow_cloud_web: true
  allow_private_data: false
validators:
  - validators/validate_report.py
""",
                encoding="utf-8",
            )

            data = load_yaml(path)

        self.assertEqual(data["task_id"], "lit_review_001")
        self.assertEqual(data["input"]["prompt_file"], "tasks/prompt.md")
        self.assertEqual(data["output"]["expected"], ["report.md", "summary.md"])
        self.assertEqual(data["policy"]["allow_cloud_web"], True)
        self.assertEqual(data["validators"], ["validators/validate_report.py"])


if __name__ == "__main__":
    unittest.main()

