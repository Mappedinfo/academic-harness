from __future__ import annotations

from pathlib import Path
from typing import Any

from .qoder_cli import prompt_text_for_task, write_fake_qoder_files


def run_fake(
    project_root: Path,
    task: dict[str, Any],
    run_id: str,
    run_dir: Path,
) -> dict[str, Any]:
    qoder_dir = run_dir / "qoder"
    qoder_dir.mkdir(parents=True, exist_ok=True)
    prompt = prompt_text_for_task(project_root, task)
    write_fake_qoder_files(qoder_dir, task, run_id, prompt, "fake")
    return {
        "adapter": "fake",
        "mode": "fake",
        "qoder_dir": str(qoder_dir),
        "command": ["fake-qoder"],
        "stdout": "",
        "stderr": "",
    }
