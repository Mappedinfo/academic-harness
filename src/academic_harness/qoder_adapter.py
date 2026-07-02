from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


class AdapterError(RuntimeError):
    pass


def run_qoder_adapter(
    project_root: Path,
    project: dict[str, Any],
    task: dict[str, Any],
    run_id: str,
    run_dir: Path,
    adapter: str,
) -> dict[str, Any]:
    qoder_dir = run_dir / "qoder"
    qoder_dir.mkdir(parents=True, exist_ok=True)

    if adapter == "fake":
        return _run_fake_adapter(project_root, task, run_id, qoder_dir)
    if adapter == "qoder":
        return _run_live_qoder(project_root, project, task, run_id, qoder_dir)
    raise AdapterError(f"Unsupported adapter: {adapter}")


def normalize_qoder_outputs(run_dir: Path, qoder_result: dict[str, Any]) -> list[dict[str, Any]]:
    qoder_dir = Path(qoder_result["qoder_dir"])
    artifacts: list[dict[str, Any]] = []

    for filename, kind in [("report.md", "report"), ("summary.md", "summary")]:
        source = qoder_dir / filename
        if source.exists():
            target = run_dir / filename
            shutil.copyfile(source, target)
            artifacts.append(_artifact_record(target, kind))

    artifact_dir = qoder_dir / "artifacts"
    if artifact_dir.exists():
        for path in sorted(artifact_dir.iterdir()):
            if path.is_file():
                artifacts.append(_artifact_record(path, "qoder_artifact"))

    for raw_name in ["metadata.json", "session.json", "events.sse", "events.jsonl", "prompt.txt"]:
        raw_path = qoder_dir / raw_name
        if raw_path.exists():
            artifacts.append(_artifact_record(raw_path, "qoder_raw"))

    return artifacts


def _run_live_qoder(
    project_root: Path,
    project: dict[str, Any],
    task: dict[str, Any],
    run_id: str,
    qoder_dir: Path,
) -> dict[str, Any]:
    qoder = project.get("qoder") or {}
    runner_command = qoder.get("runner_command") or "qoder-run"
    profile = qoder.get("profile") or "default"
    config = qoder.get("config")
    prompt_file = _resolve_project_path(project_root, task["input"]["prompt_file"])

    command = [
        runner_command,
        "--prompt-file",
        str(prompt_file),
        "--profile",
        str(profile),
        "--run-id",
        run_id,
        "--run-dir",
        str(qoder_dir),
        "--metadata",
        f"project_id={project['project_id']}",
        "--metadata",
        f"task_id={task['task_id']}",
        "--metadata",
        f"run_id={run_id}",
    ]
    if config:
        command.extend(["--config", str(_resolve_project_path(project_root, str(config)))])

    completed = subprocess.run(
        command,
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AdapterError(completed.stderr.strip() or completed.stdout.strip() or "qoder-run failed")

    return {
        "adapter": "qoder",
        "qoder_dir": str(qoder_dir),
        "command": command,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _run_fake_adapter(project_root: Path, task: dict[str, Any], run_id: str, qoder_dir: Path) -> dict[str, Any]:
    prompt_file = _resolve_project_path(project_root, task["input"]["prompt_file"])
    prompt = prompt_file.read_text(encoding="utf-8")
    report = (
        f"# Fake Qoder Report\n\n"
        f"Run: `{run_id}`\n\n"
        f"Task: `{task['task_id']}`\n\n"
        f"Prompt excerpt:\n\n{prompt[:500].strip()}\n"
    )
    summary = f"Fake adapter completed task `{task['task_id']}` for run `{run_id}`.\n"
    (qoder_dir / "report.md").write_text(report, encoding="utf-8")
    (qoder_dir / "summary.md").write_text(summary, encoding="utf-8")
    (qoder_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    (qoder_dir / "events.sse").write_text("", encoding="utf-8")
    (qoder_dir / "events.jsonl").write_text("", encoding="utf-8")
    (qoder_dir / "session.json").write_text(json.dumps({"id": f"fake_{run_id}", "status": "idle"}) + "\n", encoding="utf-8")
    (qoder_dir / "metadata.json").write_text(
        json.dumps({"run_id": run_id, "status": "idle", "adapter": "fake"}, indent=2) + "\n",
        encoding="utf-8",
    )
    artifacts_dir = qoder_dir / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    (artifacts_dir / "fake_artifact.md").write_text(report, encoding="utf-8")
    return {
        "adapter": "fake",
        "qoder_dir": str(qoder_dir),
        "command": ["fake-qoder"],
        "stdout": "",
        "stderr": "",
    }


def _resolve_project_path(project_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_root / path


def _artifact_record(path: Path, kind: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "path": str(path),
        "size": path.stat().st_size,
    }
