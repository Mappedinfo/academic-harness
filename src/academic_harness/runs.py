from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .executors import ExecutorError, normalize_executor_outputs, resolve_executor_adapter, run_executor
from .index import list_runs, upsert_run
from .kernel import RunContext, RunStateMachine, TraceWriter, check_artifacts, check_preflight, collect_artifacts
from .paths import MANIFEST_FILE, find_project_root, run_dir
from .project import ensure_project_dirs, load_project
from .timeutil import timestamp_id, utc_now_iso
from .validators import run_artifact_validators, run_validators
from .yamlio import load_yaml, read_json, write_json


SUPPORTED_TASK_TYPES = {
    "qoder_research",
    "cloud_experiment",
    "deep_search",
    "local_control",
    "lan_experiment",
    "document_build",
    "artifact_validation",
}
SUPPORTED_MODES = {"full_cloud", "local_control", "lan_control", "hybrid", "fake"}


def run_task(
    task_path: Path,
    adapter: str = "auto",
    run_id: str | None = None,
    project_root: Path | None = None,
    run_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_path = task_path.resolve()
    root, project = load_project(project_root or task_path)
    ensure_project_dirs(root)
    task = _apply_run_options(load_yaml(task_path), run_options)
    _validate_task(task, task_path)

    run_id = run_id or timestamp_id()
    resolved_adapter = resolve_executor_adapter(task, adapter)
    mode = _mode_for_resolved_adapter(task, resolved_adapter, adapter)
    output_dir = run_dir(root, run_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    ctx = RunContext.create(
        project_root=root,
        project=project,
        task=task,
        task_path=task_path,
        run_id=run_id,
        requested_adapter=adapter,
        resolved_adapter=resolved_adapter,
        mode=mode,
    )
    trace = TraceWriter(output_dir, run_id)
    state = RunStateMachine(trace)
    state.enter("created")
    manifest_path = ctx.manifest_path
    started_at = utc_now_iso()
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "project_id": project["project_id"],
        "task_id": task["task_id"],
        "task_type": task["type"],
        "mode": mode,
        "status": "created",
        "started_at": started_at,
        "project_root": str(root),
        "task_path": str(task_path),
        "task": task,
        "adapter": adapter,
        "requested_adapter": adapter,
        "resolved_adapter": resolved_adapter,
        "run_dir": str(output_dir),
        "manifest_path": str(manifest_path),
        "artifacts": [],
        "validators": [],
        "policy": {},
        "trace_path": str(trace.path),
    }
    state.apply(manifest)
    write_json(manifest_path, manifest)
    upsert_run(root, manifest)

    try:
        state.enter("policy_checking", phase="preflight")
        state.apply(manifest)
        pre_policy = check_preflight(ctx)
        manifest["policy"]["preflight"] = pre_policy.as_dict()
        trace.write("policy.preflight", pre_policy.as_dict())
        if pre_policy.decision == "deny":
            manifest["status"] = "blocked"
            manifest["error"] = "; ".join(pre_policy.reasons)
            state.enter("blocked", manifest["error"])
            return manifest
        if pre_policy.decision == "ask":
            manifest["status"] = "awaiting_approval"
            manifest["error"] = "; ".join(pre_policy.reasons)
            state.enter("awaiting_approval", manifest["error"], required_approvals=pre_policy.required_approvals)
            return manifest

        state.enter("approved", "preflight policy allowed")
        state.enter("executing", adapter=resolved_adapter)
        if resolved_adapter in {"qoder_cloud", "qoder_cli", "hybrid", "lan"}:
            state.enter("streaming", adapter=resolved_adapter)

        manifest["status"] = "running"
        state.apply(manifest)
        write_json(manifest_path, manifest)
        upsert_run(root, manifest)

        executor_result = run_executor(root, project, task, run_id, output_dir, adapter)
        manifest["executor"] = executor_result
        manifest["qoder"] = executor_result
        manifest["adapter"] = executor_result.get("adapter", adapter)
        manifest["mode"] = executor_result.get("mode", mode)
        state.enter("collecting_artifacts")
        normalized = normalize_executor_outputs(output_dir, executor_result)
        manifest["artifacts"] = collect_artifacts(root, output_dir, normalized)
        _attach_primary_paths(manifest, output_dir)
        post_policy = check_artifacts(ctx, manifest["artifacts"])
        manifest["policy"]["post_artifact"] = post_policy.as_dict()
        trace.write("policy.post_artifact", post_policy.as_dict())
        write_json(manifest_path, manifest)

        if executor_result.get("status") in {"cancelled", "failed"}:
            manifest["status"] = str(executor_result.get("status"))
            manifest["validators"] = []
            state.enter(manifest["status"], str(executor_result.get("stop_reason") or executor_result.get("error") or manifest["status"]))
        elif post_policy.decision == "deny":
            manifest["status"] = "failed"
            manifest["validators"] = []
            manifest["error"] = "; ".join(post_policy.reasons)
            state.enter("failed", manifest["error"])
        else:
            state.enter("validating")
            artifact_validators = run_artifact_validators(output_dir, manifest_path, task, manifest["artifacts"])
            write_json(manifest_path, manifest)
            local_validators = run_validators(root, output_dir, manifest_path, _local_validators(task))
            manifest["validators"] = artifact_validators + local_validators
            manifest["status"] = "passed" if all(v["status"] == "passed" for v in manifest["validators"]) else "failed"
            state.enter(manifest["status"], "validators completed")
    except (ExecutorError, Exception) as error:
        manifest["status"] = "failed"
        manifest["error"] = str(error)
        state.enter("failed", str(error))
    finally:
        manifest["finished_at"] = utc_now_iso()
        _attach_primary_paths(manifest, output_dir)
        state.apply(manifest)
        write_json(manifest_path, manifest)
        upsert_run(root, manifest)

    return manifest


def rerun_validators(run_id: str, project_root: Path) -> dict[str, Any]:
    root = find_project_root(project_root)
    manifest_path = run_dir(root, run_id) / MANIFEST_FILE
    manifest = read_json(manifest_path)
    validators = _local_validators(manifest.get("task") or {})
    output_dir = Path(manifest["run_dir"])
    artifact_validators = run_artifact_validators(
        output_dir,
        manifest_path,
        manifest.get("task") or {},
        manifest.get("artifacts") or [],
    )
    manifest["validators"] = artifact_validators + run_validators(root, output_dir, manifest_path, validators)
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
    if adapter in {"hybrid", "hybrid_ai"}:
        return "hybrid"
    if adapter in {"local_control", "local"}:
        return "local_control"
    if adapter in {"lan", "lan_experiment", "lan_control"}:
        return "lan_control"
    return "local_control"


def _mode_for_resolved_adapter(task: dict[str, Any], resolved_adapter: str, requested_adapter: str) -> str:
    if requested_adapter == "fake" or resolved_adapter == "fake":
        return "fake"
    if resolved_adapter == "qoder_cloud":
        return "full_cloud"
    if resolved_adapter == "hybrid":
        return "hybrid"
    if resolved_adapter == "lan":
        return "lan_control"
    if resolved_adapter == "local_control":
        return "local_control"
    return task.get("mode") or _mode_for_adapter(requested_adapter)


def _local_validators(task: dict[str, Any]) -> list[str]:
    validators = task.get("validators") or []
    if isinstance(validators, dict):
        validators = validators.get("local") or []
    if isinstance(validators, str):
        return [validators]
    return list(validators)


def _apply_run_options(task: dict[str, Any], run_options: dict[str, Any] | None) -> dict[str, Any]:
    if not run_options:
        return task
    updated = copy.deepcopy(task)
    managed: dict[str, Any] = {}
    existing = updated.get("managed_agents")
    if isinstance(existing, dict):
        managed.update(existing)

    managed_flag = run_options.get("managed_agents")
    if managed_flag == "on":
        managed["enabled"] = True
    elif managed_flag == "off":
        managed["enabled"] = False

    count = run_options.get("managed_agent_count")
    if count is not None:
        managed["total_agents"] = int(count)

    if run_options.get("require_managed_agents"):
        managed["require_managed_agents"] = True

    delegation_strategy = run_options.get("delegation_strategy")
    if delegation_strategy in {"agent_sync", "child_threads"}:
        managed["delegation_strategy"] = str(delegation_strategy)

    if managed:
        updated["managed_agents"] = managed
    return updated
