from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..qoder_dependency import discover_qoder_runner


class QoderCLIError(RuntimeError):
    pass


def run_qoder_cli(
    project_root: Path,
    project: dict[str, Any],
    task: dict[str, Any],
    run_id: str,
    run_dir: Path,
) -> dict[str, Any]:
    qoder_dir = run_dir / "qoder"
    qoder_dir.mkdir(parents=True, exist_ok=True)

    qoder = discover_qoder_runner(project_root, project, check_help=False)
    runner_command = qoder.get("runner_path")
    if not runner_command:
        raise QoderCLIError(f"qoder-run not found. {qoder.get('install_hint')}")
    if not qoder.get("config_path"):
        raise QoderCLIError("Qoder config missing. Save a project Qoder config or run academic-harness qoder install.")

    prompt_file = resolve_prompt_file(project_root, task)
    profile = qoder.get("profile") or "default"
    command = [
        str(runner_command),
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
        "--config",
        str(qoder["config_path"]),
    ]

    completed = subprocess.run(
        command,
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise QoderCLIError(completed.stderr.strip() or completed.stdout.strip() or "qoder-run failed")

    return {
        "adapter": "qoder_cli",
        "mode": task.get("mode") or "local_control",
        "qoder_dir": str(qoder_dir),
        "command": command,
        "runner_source": qoder.get("source"),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def normalize_qoder_outputs(run_dir: Path, result: dict[str, Any]) -> list[dict[str, Any]]:
    qoder_dir = Path(result["qoder_dir"])
    artifacts: list[dict[str, Any]] = []

    for filename, kind in [("report.md", "report"), ("summary.md", "summary")]:
        source = qoder_dir / filename
        if source.exists():
            target = run_dir / filename
            if source.resolve() != target.resolve():
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


def resolve_prompt_file(project_root: Path, task: dict[str, Any]) -> Path:
    input_config = task.get("input") or {}
    prompt_file = input_config.get("prompt_file") if isinstance(input_config, dict) else None
    if not prompt_file:
        raise QoderCLIError("Missing input.prompt_file")
    return resolve_project_path(project_root, str(prompt_file))


def prompt_text_for_task(project_root: Path, task: dict[str, Any]) -> str:
    input_config = task.get("input") or {}
    if isinstance(input_config, dict) and input_config.get("prompt_file"):
        return resolve_prompt_file(project_root, task).read_text(encoding="utf-8")
    plan = task.get("plan") or {}
    if isinstance(plan, dict) and plan.get("objective"):
        return str(plan["objective"]).strip() + "\n"
    raise QoderCLIError("Missing input.prompt_file or plan.objective")


def resolve_project_path(project_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_root / path


def _artifact_record(path: Path, kind: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "path": str(path),
        "size": path.stat().st_size,
    }


def write_fake_qoder_files(qoder_dir: Path, task: dict[str, Any], run_id: str, prompt: str, adapter: str) -> None:
    report = (
        f"# {adapter.replace('_', ' ').title()} Report\n\n"
        f"Run: `{run_id}`\n\n"
        f"Task: `{task['task_id']}`\n\n"
        f"Prompt excerpt:\n\n{prompt[:500].strip()}\n"
    )
    summary = f"{adapter} completed task `{task['task_id']}` for run `{run_id}`.\n"
    (qoder_dir / "report.md").write_text(report, encoding="utf-8")
    (qoder_dir / "summary.md").write_text(summary, encoding="utf-8")
    (qoder_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    (qoder_dir / "events.sse").write_text("", encoding="utf-8")
    (qoder_dir / "events.jsonl").write_text("", encoding="utf-8")
    (qoder_dir / "session.json").write_text(json.dumps({"id": f"{adapter}_{run_id}", "status": "idle"}) + "\n", encoding="utf-8")
    (qoder_dir / "metadata.json").write_text(
        json.dumps({"run_id": run_id, "status": "idle", "adapter": adapter}, indent=2) + "\n",
        encoding="utf-8",
    )
    artifacts_dir = qoder_dir / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    (artifacts_dir / f"{adapter}_artifact.md").write_text(report, encoding="utf-8")
