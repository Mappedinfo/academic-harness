from __future__ import annotations

from pathlib import Path
from typing import Any

from .fake import run_fake
from .local_control import run_local_control
from .qoder_cli import normalize_qoder_outputs, run_qoder_cli
from .qoder_cloud import run_qoder_cloud


class ExecutorError(RuntimeError):
    pass


def run_executor(
    project_root: Path,
    project: dict[str, Any],
    task: dict[str, Any],
    run_id: str,
    run_dir: Path,
    adapter: str,
) -> dict[str, Any]:
    resolved = _resolve_adapter(task, adapter)
    if resolved == "fake":
        return run_fake(project_root, task, run_id, run_dir)
    if resolved == "qoder_cli":
        return run_qoder_cli(project_root, project, task, run_id, run_dir)
    if resolved == "qoder_cloud":
        return run_qoder_cloud(project_root, project, task, run_id, run_dir)
    if resolved == "local_control":
        return run_local_control(project_root, project, task, run_id, run_dir)
    raise ExecutorError(f"Unsupported executor: {adapter}")


def normalize_executor_outputs(run_dir: Path, result: dict[str, Any]) -> list[dict[str, Any]]:
    adapter = result.get("adapter")
    if adapter in {"qoder", "qoder_cli", "qoder_cloud", "fake", "local_control"}:
        return normalize_qoder_outputs(run_dir, result)
    return []


def _resolve_adapter(task: dict[str, Any], requested: str) -> str:
    if requested == "auto":
        mode = task.get("mode")
        task_type = task.get("type")
        if mode == "full_cloud" or task_type == "cloud_experiment":
            return "qoder_cloud"
        if mode == "local_control" or task_type == "local_control":
            return "local_control"
        if mode == "fake":
            return "fake"
        return "qoder_cli"
    if requested in {"qoder", "qoder_cli"}:
        return "qoder_cli"
    if requested in {"qoder_cloud", "cloud"}:
        return "qoder_cloud"
    if requested in {"local_control", "local"}:
        return "local_control"
    if requested == "fake":
        return "fake"

    mode = task.get("mode")
    task_type = task.get("type")
    if mode == "full_cloud" or task_type == "cloud_experiment":
        return "qoder_cloud"
    if mode == "local_control" or task_type == "local_control":
        return "local_control"
    return requested
