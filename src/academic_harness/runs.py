from __future__ import annotations

from pathlib import Path
from typing import Any

from .index import list_runs, upsert_run
from .paths import MANIFEST_FILE, find_project_root, run_dir
from .project import ensure_project_dirs, load_project
from .qoder_adapter import AdapterError, normalize_qoder_outputs, run_qoder_adapter
from .timeutil import timestamp_id, utc_now_iso
from .validators import run_validators
from .yamlio import load_yaml, read_json, write_json


def run_task(task_path: Path, adapter: str = "qoder", run_id: str | None = None, project_root: Path | None = None) -> dict[str, Any]:
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
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "project_id": project["project_id"],
        "task_id": task["task_id"],
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
        qoder_result = run_qoder_adapter(root, project, task, run_id, output_dir, adapter)
        manifest["qoder"] = qoder_result
        manifest["artifacts"] = normalize_qoder_outputs(output_dir, qoder_result)
        _attach_primary_paths(manifest, output_dir)
        write_json(manifest_path, manifest)

        manifest["validators"] = run_validators(root, output_dir, manifest_path, list(task.get("validators") or []))
        manifest["status"] = "passed" if all(v["status"] == "passed" for v in manifest["validators"]) else "failed"
    except (AdapterError, Exception) as error:
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
    validators = list((manifest.get("task") or {}).get("validators") or [])
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
    for key in ["task_id", "type", "input"]:
        if key not in task:
            raise ValueError(f"Missing {key} in {task_path}")
    if task["type"] != "qoder_research":
        raise ValueError(f"Unsupported task type: {task['type']}")
    prompt_file = task.get("input", {}).get("prompt_file")
    if not prompt_file:
        raise ValueError(f"Missing input.prompt_file in {task_path}")
