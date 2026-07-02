from __future__ import annotations

from pathlib import Path
from typing import Any

from .executors import ExecutorError, normalize_executor_outputs, run_executor
from .index import list_runs, upsert_run
from .paths import MANIFEST_FILE, find_project_root, run_dir
from .project import ensure_project_dirs, load_project
from .timeutil import timestamp_id, utc_now_iso
from .validators import run_validators
from .yamlio import load_yaml, read_json, write_json


SUPPORTED_TASK_TYPES = {
    "qoder_research",
    "cloud_experiment",
    "local_control",
    "lan_experiment",
    "document_build",
    "artifact_validation",
}
SUPPORTED_MODES = {"full_cloud", "local_control", "lan_control", "fake"}


def run_task(task_path: Path, adapter: str = "auto", run_id: str | None = None, project_root: Path | None = None) -> dict[str, Any]:
    task_path = task_path.resolve()
    root, project = load_project(project_root or task_path)
    ensure_project_dirs(root)
    task = load_yaml(task_path)
    _validate_task(task, task_path)

    run_id = run_id or timestamp_id()
    output_dir = run_dir(root, run_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / MANIFEST_FILE
    started_at = utc_now_iso()
    mode = task.get("mode") or _mode_for_adapter(adapter)
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "project_id": project["project_id"],
        "task_id": task["task_id"],
        "task_type": task["type"],
        "mode": mode,
        "status": "running",
        "started_at": started_at,
        "project_root": str(root),
        "task_path": str(task_path),
        "task": task,
        "adapter": adapter,
        "run_dir": str(output_dir),
        "manifest_path": str(manifest_path),
        "artifacts": [],
        "validators": [],
    }
    write_json(manifest_path, manifest)
    upsert_run(root, manifest)

    try:
        executor_result = run_executor(root, project, task, run_id, output_dir, adapter)
        manifest["executor"] = executor_result
        manifest["qoder"] = executor_result
        manifest["adapter"] = executor_result.get("adapter", adapter)
        manifest["mode"] = executor_result.get("mode", mode)
        manifest["artifacts"] = normalize_executor_outputs(output_dir, executor_result)
        _attach_primary_paths(manifest, output_dir)
        write_json(manifest_path, manifest)

        if executor_result.get("status") == "cancelled":
            manifest["status"] = "cancelled"
            manifest["validators"] = []
        else:
            manifest["validators"] = run_validators(root, output_dir, manifest_path, _local_validators(task))
            manifest["status"] = "passed" if all(v["status"] == "passed" for v in manifest["validators"]) else "failed"
    except (ExecutorError, Exception) as error:
        manifest["status"] = "failed"
        manifest["error"] = str(error)
    finally:
        manifest["finished_at"] = utc_now_iso()
        _attach_primary_paths(manifest, output_dir)
        write_json(manifest_path, manifest)
        upsert_run(root, manifest)

    return manifest


def rerun_validators(run_id: str, project_root: Path) -> dict[str, Any]:
    root = find_project_root(project_root)
    manifest_path = run_dir(root, run_id) / MANIFEST_FILE
    manifest = read_json(manifest_path)
    validators = _local_validators(manifest.get("task") or {})
    manifest["validators"] = run_validators(root, Path(manifest["run_dir"]), manifest_path, validators)
    manifest["status"] = "passed" if all(v["status"] == "passed" for v in manifest["validators"]) else "failed"
    manifest["finished_at"] = utc_now_iso()
    write_json(manifest_path, manifest)
    upsert_run(root, manifest)
    return manifest


def show_run(run_id: str, project_root: Path) -> dict[str, Any]:
    root = find_project_root(project_root)
    return read_json(run_dir(root, run_id) / MANIFEST_FILE)


def list_project_runs(project_root: Path) -> list[dict[str, Any]]:
    root = find_project_root(project_root)
    return list_runs(root)


def _attach_primary_paths(manifest: dict[str, Any], output_dir: Path) -> None:
    report = output_dir / "report.md"
    summary = output_dir / "summary.md"
    if report.exists():
        manifest["report_path"] = str(report)
    if summary.exists():
        manifest["summary_path"] = str(summary)


def _validate_task(task: dict[str, Any], task_path: Path) -> None:
    for key in ["task_id", "type"]:
        if key not in task:
            raise ValueError(f"Missing {key} in {task_path}")
    if task["type"] not in SUPPORTED_TASK_TYPES:
        raise ValueError(f"Unsupported task type: {task['type']}")
    mode = task.get("mode")
    if mode and mode not in SUPPORTED_MODES:
        raise ValueError(f"Unsupported task mode: {mode}")
    input_config = task.get("input") or {}
    plan = task.get("plan") or {}
    prompt_file = input_config.get("prompt_file") if isinstance(input_config, dict) else None
    objective = plan.get("objective") if isinstance(plan, dict) else None
    if not prompt_file and not objective:
        raise ValueError(f"Missing input.prompt_file or plan.objective in {task_path}")


def _mode_for_adapter(adapter: str) -> str:
    if adapter == "auto":
        return "local_control"
    if adapter == "fake":
        return "fake"
    if adapter in {"qoder_cloud", "cloud"}:
        return "full_cloud"
    if adapter in {"local_control", "local"}:
        return "local_control"
    return "local_control"


def _local_validators(task: dict[str, Any]) -> list[str]:
    validators = task.get("validators") or []
    if isinstance(validators, dict):
        validators = validators.get("local") or []
    if isinstance(validators, str):
        return [validators]
    return list(validators)
