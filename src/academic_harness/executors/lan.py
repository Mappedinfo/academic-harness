from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

from ..yamlio import write_json
from .qoder_cli import prompt_text_for_task


class LANExecutorError(RuntimeError):
    pass


def run_lan_experiment(
    project_root: Path,
    project: dict[str, Any],
    task: dict[str, Any],
    run_id: str,
    run_dir: Path,
) -> dict[str, Any]:
    settings = _lan_settings(project, task)
    ssh_alias = str(settings.get("ssh_alias") or "").strip()
    remote_project_root = str(settings.get("project_root") or "").strip().rstrip("/")
    if not bool(settings.get("enabled")):
        raise LANExecutorError("LAN is disabled; enable project.lan before running a LAN experiment")
    if not ssh_alias:
        raise LANExecutorError("LAN ssh_alias is missing")
    if not remote_project_root:
        raise LANExecutorError("LAN project_root is missing")

    lan_dir = run_dir / "lan"
    lan_dir.mkdir(parents=True, exist_ok=True)
    remote_run_dir = _posix_join(remote_project_root, ".workbench", "runs", run_id)
    prompt = prompt_text_for_task(project_root, task)
    input_payload = _input_payload(project, task, run_id, prompt, remote_project_root, remote_run_dir)
    input_path = lan_dir / "input.json"
    runner_path = lan_dir / "remote_runner.py"
    write_json(input_path, input_payload)
    runner_path.write_text(_remote_runner_script(), encoding="utf-8")

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    _run_checked(
        ["ssh", ssh_alias, "mkdir", "-p", remote_run_dir, f"{remote_run_dir}/artifacts", f"{remote_run_dir}/figures", f"{remote_run_dir}/tables"],
        stdout_lines,
        stderr_lines,
        "create remote run directory",
    )
    _run_checked(["scp", str(input_path), f"{ssh_alias}:{remote_run_dir}/input.json"], stdout_lines, stderr_lines, "upload LAN input")
    _run_checked(["scp", str(runner_path), f"{ssh_alias}:{remote_run_dir}/remote_runner.py"], stdout_lines, stderr_lines, "upload LAN runner")

    remote_command = _remote_command(task, remote_project_root, remote_run_dir)
    if remote_command:
        command = ["ssh", ssh_alias, "bash", "-lc", remote_command]
    else:
        command = ["ssh", ssh_alias, "python3", f"{remote_run_dir}/remote_runner.py", remote_run_dir]
    _run_checked(command, stdout_lines, stderr_lines, "run LAN experiment")

    collected = _collect_outputs(ssh_alias, remote_run_dir, lan_dir, task, stdout_lines, stderr_lines)
    (lan_dir / "stdout.log").write_text("\n".join(stdout_lines).strip() + "\n", encoding="utf-8")
    (lan_dir / "stderr.log").write_text("\n".join(stderr_lines).strip() + "\n", encoding="utf-8")
    metadata = {
        "adapter": "lan",
        "mode": "lan_control",
        "status": "succeeded",
        "run_id": run_id,
        "ssh_alias": ssh_alias,
        "remote_project_root": remote_project_root,
        "remote_run_dir": remote_run_dir,
        "collected": collected,
        "data_policy": "remote_only",
    }
    write_json(lan_dir / "metadata.json", metadata)
    return {
        "adapter": "lan",
        "mode": "lan_control",
        "status": "succeeded",
        "lan_dir": str(lan_dir),
        "remote_run_dir": remote_run_dir,
        "ssh_alias": ssh_alias,
        "metadata_path": str(lan_dir / "metadata.json"),
        "stdout": "\n".join(stdout_lines),
        "stderr": "\n".join(stderr_lines),
    }


def normalize_lan_outputs(run_dir: Path, result: dict[str, Any]) -> list[dict[str, Any]]:
    lan_dir = Path(result["lan_dir"])
    artifacts: list[dict[str, Any]] = []
    for filename, kind in [("report.md", "report"), ("summary.md", "summary")]:
        source = lan_dir / filename
        if source.exists():
            target = run_dir / filename
            shutil.copyfile(source, target)
            artifacts.append(_artifact_record(target, kind))

    for folder, kind in [("artifacts", "lan_artifact"), ("figures", "figure_registry"), ("tables", "table_registry")]:
        source_dir = lan_dir / folder
        if source_dir.exists():
            for path in sorted(source_dir.rglob("*")):
                if path.is_file():
                    artifacts.append(_artifact_record(path, kind))

    for raw_name in ["metadata.json", "input.json", "stdout.log", "stderr.log", "remote_runner.py"]:
        raw_path = lan_dir / raw_name
        if raw_path.exists():
            artifacts.append(_artifact_record(raw_path, "lan_raw"))
    return artifacts


def _lan_settings(project: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(project.get("lan"), dict):
        merged.update(project["lan"])
    for key in ["lan", "remote"]:
        if isinstance(task.get(key), dict):
            merged.update(task[key])
    return merged


def _input_payload(
    project: dict[str, Any],
    task: dict[str, Any],
    run_id: str,
    prompt: str,
    remote_project_root: str,
    remote_run_dir: str,
) -> dict[str, Any]:
    variables: dict[str, Any] = {}
    if isinstance(project.get("variables"), dict):
        variables.update(project["variables"])
    if isinstance(task.get("variables"), dict):
        variables.update(task["variables"])
    experiment = task.get("experiment") if isinstance(task.get("experiment"), dict) else {}
    if isinstance(experiment.get("variables"), dict):
        variables.update(experiment["variables"])
    return {
        "run_id": run_id,
        "project_id": project.get("project_id"),
        "title": project.get("title"),
        "task": task,
        "prompt": prompt,
        "variables": variables,
        "experiment": experiment,
        "remote_project_root": remote_project_root,
        "remote_run_dir": remote_run_dir,
        "data_policy": {
            "data_location": "remote_only",
            "local_download_allowed": False,
        },
    }


def _remote_command(task: dict[str, Any], remote_project_root: str, remote_run_dir: str) -> str | None:
    remote = task.get("remote") if isinstance(task.get("remote"), dict) else {}
    lan = task.get("lan") if isinstance(task.get("lan"), dict) else {}
    command = remote.get("command") or lan.get("command")
    if not command:
        return None
    if isinstance(command, list):
        command_text = " ".join(shlex.quote(str(item)) for item in command)
    else:
        command_text = str(command)
    return command_text.format(
        remote_project_root=shlex.quote(remote_project_root),
        remote_run_dir=shlex.quote(remote_run_dir),
        input_json=shlex.quote(f"{remote_run_dir}/input.json"),
    )


def _collect_outputs(
    ssh_alias: str,
    remote_run_dir: str,
    lan_dir: Path,
    task: dict[str, Any],
    stdout_lines: list[str],
    stderr_lines: list[str],
) -> list[str]:
    output = task.get("output") if isinstance(task.get("output"), dict) else {}
    collect = output.get("collect") if isinstance(output.get("collect"), list) else None
    rel_paths = [str(item).strip().rstrip("/") for item in collect or _default_collect_paths()]
    collected: list[str] = []
    for rel_path in rel_paths:
        if not rel_path:
            continue
        local_path = lan_dir / rel_path
        local_path.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            ["scp", f"{ssh_alias}:{remote_run_dir}/{rel_path}", str(local_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.stdout:
            stdout_lines.append(completed.stdout.strip())
        if completed.stderr:
            stderr_lines.append(completed.stderr.strip())
        if completed.returncode == 0 and local_path.exists():
            collected.append(rel_path)
    return collected


def _default_collect_paths() -> list[str]:
    return [
        "report.md",
        "summary.md",
        "artifacts/variables.json",
        "artifacts/metrics.json",
        "artifacts/experiment_plan.json",
        "artifacts/remote_data_contract.json",
        "figures/registry.yaml",
        "tables/registry.yaml",
    ]


def _run_checked(command: list[str], stdout_lines: list[str], stderr_lines: list[str], label: str) -> None:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.stdout:
        stdout_lines.append(completed.stdout.strip())
    if completed.stderr:
        stderr_lines.append(completed.stderr.strip())
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
        raise LANExecutorError(f"{label} failed: {detail}")


def _remote_runner_script() -> str:
    return r'''#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def synthetic_traffic_series(n=288):
    values = []
    for i in range(n):
        hour = (i % 288) / 12.0
        morning = 42.0 * math.exp(-((hour - 8.0) ** 2) / 5.0)
        evening = 48.0 * math.exp(-((hour - 18.0) ** 2) / 6.0)
        daily = 18.0 * math.sin((2.0 * math.pi * i) / 288.0)
        short = 5.0 * math.sin((2.0 * math.pi * i) / 18.0)
        values.append(max(1.0, 90.0 + morning + evening + daily + short))
    return values


def evaluate_persistence(values, horizon_minutes):
    step = max(1, int(round(float(horizon_minutes) / 5.0)))
    errors = []
    pct_errors = []
    for index in range(step, len(values)):
        predicted = values[index - step]
        actual = values[index]
        error = predicted - actual
        errors.append(error)
        pct_errors.append(abs(error) / max(abs(actual), 1e-6))
    mae = sum(abs(error) for error in errors) / len(errors)
    rmse = math.sqrt(sum(error * error for error in errors) / len(errors))
    mape = 100.0 * sum(pct_errors) / len(pct_errors)
    return {"MAE": round(mae, 4), "RMSE": round(rmse, 4), "MAPE": round(mape, 4)}


def main() -> int:
    run_dir = Path(sys.argv[1])
    payload = json.loads((run_dir / "input.json").read_text(encoding="utf-8"))
    task = payload.get("task") or {}
    experiment = payload.get("experiment") or {}
    variables = payload.get("variables") or {}
    artifacts = run_dir / "artifacts"
    figures = run_dir / "figures"
    tables = run_dir / "tables"
    artifacts.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)

    topic = experiment.get("topic") or task.get("title") or "LAN experiment"
    metrics = experiment.get("metrics") or ["MAE", "RMSE", "MAPE"]
    horizons = variables.get("prediction_horizon_minutes") or [15, 30, 60]
    values = synthetic_traffic_series()
    metric_results = {str(horizon): evaluate_persistence(values, horizon) for horizon in horizons}
    variable_lines = "\n".join(f"- `{key}`: `{value}`" for key, value in sorted(variables.items())) or "- no variables declared"
    metric_lines = "\n".join(f"- {metric}" for metric in metrics)
    result_lines = "\n".join(
        f"- {horizon} min: MAE={result['MAE']}, RMSE={result['RMSE']}, MAPE={result['MAPE']}%"
        for horizon, result in metric_results.items()
    )
    prompt = str(payload.get("prompt") or "").strip()
    report = f"""# LAN Experiment Report

Run: `{payload.get('run_id')}`

Task: `{task.get('task_id')}`

Topic: {topic}

## Remote-Only Data Contract

- Remote project root: `{payload.get('remote_project_root')}`
- Remote run directory: `{payload.get('remote_run_dir')}`
- Data policy: source data remains on the LAN worker; this runner only exports report, summary, registries, and light metadata.

## Objective

{prompt}

## Variables

{variable_lines}

## Traffic Flow Experiment Skeleton

This remote run generated a synthetic traffic-flow sequence on the LAN worker and evaluated a persistence baseline for short-horizon prediction. A production task can replace the synthetic generator with remote datasets and scripts under the remote project root without changing the local artifact contract.

Expected evaluation metrics:

{metric_lines}

Baseline results:

{result_lines}

## Output Management

- Figures are registered in `figures/registry.yaml`.
- Tables are registered in `tables/registry.yaml`.
- Variables are captured in `artifacts/variables.json`.
- Metrics are captured in `artifacts/metrics.json`.
"""
    (run_dir / "report.md").write_text(report, encoding="utf-8")
    (run_dir / "summary.md").write_text(
        f"LAN experiment `{payload.get('run_id')}` prepared remote-only traffic-flow experiment artifacts.\n",
        encoding="utf-8",
    )
    (artifacts / "variables.json").write_text(json.dumps(variables, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (artifacts / "metrics.json").write_text(json.dumps({
        "series": "synthetic_remote_only",
        "time_step_minutes": 5,
        "baseline": "persistence",
        "results": metric_results,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (artifacts / "experiment_plan.json").write_text(json.dumps({
        "topic": topic,
        "metrics": metrics,
        "task_id": task.get("task_id"),
        "run_id": payload.get("run_id"),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (artifacts / "remote_data_contract.json").write_text(json.dumps(payload.get("data_policy"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (figures / "registry.yaml").write_text(
        "figures:\n"
        "  - id: traffic_flow_prediction_overview\n"
        "    title: Traffic flow prediction overview\n"
        "    path: remote-only\n"
        "    status: planned\n",
        encoding="utf-8",
    )
    (tables / "registry.yaml").write_text(
        "tables:\n"
        "  - id: traffic_flow_metrics\n"
        "    title: Traffic flow prediction metrics\n"
        "    path: remote-only\n"
        "    status: planned\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _posix_join(*parts: str) -> str:
    current = PurePosixPath(parts[0])
    for part in parts[1:]:
        current = current / part
    return str(current)


def _artifact_record(path: Path, kind: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "path": str(path),
        "size": path.stat().st_size,
    }
