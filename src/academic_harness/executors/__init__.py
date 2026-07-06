from __future__ import annotations

from pathlib import Path
from typing import Any

from .fake import run_fake
from .hybrid import normalize_hybrid_outputs, run_hybrid
from .lan import normalize_lan_outputs, run_lan_experiment
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
    resolved = resolve_executor_adapter(task, adapter)
    if resolved == "fake":
        return run_fake(project_root, task, run_id, run_dir)
    if resolved == "qoder_cli":
        return run_qoder_cli(project_root, project, task, run_id, run_dir)
    if resolved == "qoder_cloud":
        return run_qoder_cloud(project_root, project, task, run_id, run_dir)
    if resolved == "hybrid":
        return run_hybrid(project_root, project, task, run_id, run_dir)
    if resolved == "lan":
        return run_lan_experiment(project_root, project, task, run_id, run_dir)
    if resolved == "local_control":
        return run_local_control(project_root, project, task, run_id, run_dir)
    raise ExecutorError(f"Unsupported executor: {adapter}")


def normalize_executor_outputs(run_dir: Path, result: dict[str, Any]) -> list[dict[str, Any]]:
    adapter = result.get("adapter")
    if adapter == "hybrid":
        return normalize_hybrid_outputs(run_dir, result)
    if adapter == "lan":
        return normalize_lan_outputs(run_dir, result)
    if adapter in {"qoder", "qoder_cli", "qoder_cloud", "fake", "local_control"}:
        return normalize_qoder_outputs(run_dir, result)
    return []


def resolve_executor_adapter(task: dict[str, Any], requested: str) -> str:
    if requested == "auto":
        mode = task.get("mode")
        task_type = task.get("type")
        if mode == "hybrid":
            return "hybrid"
        if mode == "full_cloud" or task_type in {"cloud_experiment", "deep_search"}:
            return "qoder_cloud"
        if mode == "lan_control" or task_type == "lan_experiment":
            return "lan"
        if mode == "local_control" or task_type == "local_control":
            return "local_control"
        if mode == "fake":
            return "fake"
        return "qoder_cli"
    if requested in {"qoder", "qoder_cli"}:
        return "qoder_cli"
    if requested in {"qoder_cloud", "cloud"}:
        return "qoder_cloud"
    if requested in {"hybrid", "hybrid_ai"}:
        return "hybrid"
    if requested in {"local_control", "local"}:
        return "local_control"
    if requested in {"lan", "lan_experiment", "lan_control"}:
        return "lan"
    if requested == "fake":
        return "fake"

    mode = task.get("mode")
    task_type = task.get("type")
    if mode == "hybrid":
        return "hybrid"
    if mode == "full_cloud" or task_type in {"cloud_experiment", "deep_search"}:
        return "qoder_cloud"
    if mode == "lan_control" or task_type == "lan_experiment":
        return "lan"
    if mode == "local_control" or task_type == "local_control":
        return "local_control"
    return requested
