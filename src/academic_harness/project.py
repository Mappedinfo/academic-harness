from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .index import init_index
from .local_ai import local_ai_status
from .paths import PROJECT_FILE, WORKBENCH_DIR, find_project_root, workbench_dir
from .qoder_dependency import discover_qoder_runner
from .yamlio import dump_yaml, load_yaml


def init_project(project_dir: Path, force: bool = False) -> Path:
    project_dir = project_dir.resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    _write_if_missing(project_dir / PROJECT_FILE, dump_yaml(_default_project(project_dir.name)), force)

    for folder in ["tasks", "validators", "manuscript", "variables", "figures", "tables", f"{WORKBENCH_DIR}/runs"]:
        (project_dir / folder).mkdir(parents=True, exist_ok=True)

    _write_if_missing(project_dir / "tasks" / "sample_prompt.md", _sample_prompt(), force)
    _write_if_missing(project_dir / "tasks" / "sample_cloud_prompt.md", _sample_cloud_prompt(), force)
    _write_if_missing(project_dir / "tasks" / "sample_task.yaml", dump_yaml(_sample_task()), force)
    _write_if_missing(project_dir / "tasks" / "sample_cloud_experiment.yaml", dump_yaml(_sample_cloud_task()), force)
    _write_if_missing(project_dir / "tasks" / "sample_local_control.yaml", dump_yaml(_sample_local_control_task()), force)
    _write_if_missing(project_dir / "tasks" / "sample_lan_traffic_experiment.yaml", dump_yaml(_sample_lan_traffic_task()), force)
    _write_if_missing(project_dir / "tasks" / "sample_lan_traffic_prompt.md", _sample_lan_traffic_prompt(), force)
    _write_if_missing(project_dir / "validators" / "validate_report.py", _validator_script(), force)
    _write_if_missing(project_dir / "manuscript" / "main.qmd", "# Manuscript\n\n", force)
    _write_if_missing(project_dir / "variables" / "registry.yaml", "variables:\n", force)
    _write_if_missing(project_dir / "figures" / "registry.yaml", "figures:\n", force)
    _write_if_missing(project_dir / "tables" / "registry.yaml", "tables:\n", force)
    init_index(project_dir)
    return project_dir


def project_status(project_dir: Path, check_lan: bool = False, check_local_ai: bool = False) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    project_file = project_dir / PROJECT_FILE
    status: dict[str, Any] = {
        "project_root": str(project_dir),
        "ok": False,
        "checks": {},
    }

    project_exists = project_file.exists()
    status["checks"]["project"] = {
        "ok": project_exists,
        "path": str(project_file),
        "message": "project.yaml found" if project_exists else "project.yaml missing",
    }
    if not project_exists:
        status["checks"]["tasks"] = {"ok": False, "message": "project.yaml missing"}
        status["checks"]["runs"] = {"ok": False, "message": "project.yaml missing"}
        status["checks"]["qoder"] = {"ok": False, "message": "project.yaml missing"}
        status["checks"]["local_ai"] = {"ok": False, "message": "project.yaml missing"}
        status["checks"]["lan"] = {"ok": False, "message": "project.yaml missing"}
        return status

    project = load_yaml(project_file)
    tasks_dir = project_dir / str((project.get("local") or {}).get("tasks_dir") or "tasks")
    runs_path = project_dir / WORKBENCH_DIR / "runs"
    tasks_ok = tasks_dir.exists() and any(tasks_dir.glob("*.yaml"))
    status["checks"]["tasks"] = {
        "ok": tasks_ok,
        "path": str(tasks_dir),
        "message": "task yaml found" if tasks_ok else "no task yaml found",
    }
    status["checks"]["runs"] = {
        "ok": runs_path.exists(),
        "path": str(runs_path),
        "message": "runs directory found" if runs_path.exists() else "runs directory missing",
    }
    status["checks"]["qoder"] = _qoder_status(project_dir, project)
    status["checks"]["local_ai"] = local_ai_status(project, check_connection=check_local_ai)
    status["checks"]["lan"] = _lan_status(project, check_lan=check_lan)
    status["ok"] = all(
        status["checks"][name]["ok"]
        for name in ["project", "tasks", "runs"]
    )
    return status


def set_lan_config(
    project_dir: Path,
    server: str | None,
    project_root: str | None,
    ssh_alias: str | None,
    enabled: bool | None,
) -> dict[str, Any]:
    root, project = load_project(project_dir)
    lan = dict(project.get("lan") or {})
    if server is not None:
        lan["server"] = server
    if project_root is not None:
        lan["project_root"] = project_root
    if ssh_alias is not None:
        lan["ssh_alias"] = ssh_alias
    if enabled is not None:
        lan["enabled"] = enabled
    project["lan"] = lan
    (root / PROJECT_FILE).write_text(dump_yaml(project), encoding="utf-8")
    return project_status(root, check_lan=False)


def set_qoder_config(
    project_dir: Path,
    runner_command: str | None,
    config: str | None,
    profile: str | None,
) -> dict[str, Any]:
    root, project = load_project(project_dir)
    qoder = dict(project.get("qoder") or {})
    if runner_command is not None:
        qoder["runner_command"] = runner_command
    if config is not None:
        qoder["config"] = config
    if profile is not None:
        qoder["profile"] = profile
    project["qoder"] = qoder
    (root / PROJECT_FILE).write_text(dump_yaml(project), encoding="utf-8")
    return project_status(root, check_lan=False)


def set_local_ai_config(
    project_dir: Path,
    enabled: bool | None,
    provider: str | None,
    base_url: str | None,
    model: str | None,
    api_key_env: str | None,
    timeout_seconds: int | None,
) -> dict[str, Any]:
    root, project = load_project(project_dir)
    local_ai = dict(project.get("local_ai") or {})
    if enabled is not None:
        local_ai["enabled"] = enabled
    if provider is not None:
        local_ai["provider"] = provider
    if base_url is not None:
        local_ai["base_url"] = base_url
    if model is not None:
        local_ai["model"] = model
    if api_key_env is not None:
        local_ai["api_key_env"] = api_key_env
    if timeout_seconds is not None:
        local_ai["timeout_seconds"] = timeout_seconds
    project["local_ai"] = local_ai
    (root / PROJECT_FILE).write_text(dump_yaml(project), encoding="utf-8")
    return project_status(root, check_lan=False)


def reset_qoder_config(project_dir: Path) -> dict[str, Any]:
    root, project = load_project(project_dir)
    project["qoder"] = {"profile": "default"}
    (root / PROJECT_FILE).write_text(dump_yaml(project), encoding="utf-8")
    return project_status(root, check_lan=False)


def load_project(path: Path) -> tuple[Path, dict[str, Any]]:
    root = find_project_root(path)
    return root, load_yaml(root / PROJECT_FILE)


def ensure_project_dirs(project_root: Path) -> None:
    for folder in ["tasks", "validators", "manuscript", "variables", "figures", "tables"]:
        (project_root / folder).mkdir(parents=True, exist_ok=True)
    workbench_dir(project_root).mkdir(parents=True, exist_ok=True)
    (workbench_dir(project_root) / "runs").mkdir(parents=True, exist_ok=True)
    init_index(project_root)


def _qoder_status(project_dir: Path, project: dict[str, Any]) -> dict[str, Any]:
    status = discover_qoder_runner(project_dir, project, check_help=True)
    try:
        from .executors.qoder_cloud import managed_agents_status, qoder_models_status

        models = qoder_models_status(project_dir, project)
        status["models"] = models
        status["managed_agents"] = managed_agents_status(project_dir, project, models)
    except Exception as error:
        status["models"] = {
            "ok": False,
            "available_models": [],
            "ids": [],
            "message": f"models status unavailable: {error}",
        }
        status["managed_agents"] = {
            "enabled": False,
            "ready": False,
            "model_ok": False,
            "schema_ok": False,
            "agent_count": 0,
            "delegation_strategy": "agent_sync",
            "include_self": False,
            "message": f"managed agents status unavailable: {error}",
        }
    return status


def _lan_status(project: dict[str, Any], check_lan: bool) -> dict[str, Any]:
    lan = project.get("lan") or {}
    enabled = bool(lan.get("enabled", False))
    server = str(lan.get("server") or "").strip()
    project_root = str(lan.get("project_root") or "").strip()
    ssh_alias = str(lan.get("ssh_alias") or "").strip()

    if not enabled:
        return {
            "ok": True,
            "enabled": False,
            "server": server,
            "project_root": project_root,
            "ssh_alias": ssh_alias,
            "message": "LAN disabled",
        }

    configured = bool(server and project_root)
    result: dict[str, Any] = {
        "ok": configured,
        "enabled": True,
        "server": server,
        "project_root": project_root,
        "ssh_alias": ssh_alias,
        "message": "LAN configured" if configured else "LAN enabled but server/project_root missing",
    }
    if check_lan and ssh_alias:
        try:
            completed = subprocess.run(
                ["ssh", ssh_alias, "true"],
                capture_output=True,
                text=True,
                check=False,
                timeout=8,
            )
            result["ssh_ok"] = completed.returncode == 0
            result["ok"] = configured and completed.returncode == 0
            result["message"] = "LAN ssh check ok" if completed.returncode == 0 else "LAN ssh check failed"
        except Exception as error:
            result["ssh_ok"] = False
            result["ok"] = False
            result["message"] = f"LAN ssh check error: {error}"
    return result


def _write_if_missing(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _default_project(name: str) -> dict[str, Any]:
    project_id = name.replace(" ", "-").lower() or "academic-project"
    return {
        "project_id": project_id,
        "title": name or "Academic Project",
        "local": {
            "tasks_dir": "tasks",
            "validators_dir": "validators",
            "manuscript_dir": "manuscript",
            "variables_dir": "variables",
            "figures_dir": "figures",
            "tables_dir": "tables",
        },
        "variables": {},
        "lan": {
            "enabled": False,
            "server": "",
            "project_root": "",
            "ssh_alias": "",
        },
        "qoder": {
            "profile": "default",
            "managed_agents": {
                "enabled": True,
                "delegation_strategy": "agent_sync",
                "include_self": False,
                "total_agents": 4,
                "model": "",
                "require_managed_agents": False,
            },
        },
        "local_ai": {
            "enabled": False,
            "provider": "openai_compatible",
            "base_url": "http://127.0.0.1:11434/v1",
            "model": "",
            "api_key_env": "LOCAL_AI_API_KEY",
            "timeout_seconds": 120,
        },
    }


def _sample_task() -> dict[str, Any]:
    return {
        "task_id": "sample_qoder_report",
        "type": "qoder_research",
        "mode": "local_control",
        "title": "Sample Qoder Report",
        "input": {
            "prompt_file": "tasks/sample_prompt.md",
        },
        "output": {
            "expected": ["report.md", "summary.md"],
        },
        "policy": {
            "allow_cloud_web": True,
            "allow_private_data": False,
        },
        "validators": ["validators/validate_report.py"],
    }


def _sample_cloud_task() -> dict[str, Any]:
    return {
        "task_id": "sample_cloud_experiment",
        "type": "cloud_experiment",
        "mode": "full_cloud",
        "title": "Sample Full Cloud Experiment",
        "input": {
            "prompt_file": "tasks/sample_cloud_prompt.md",
        },
        "coordinator": {
            "strategy": "decompose_and_synthesize",
            "max_child_agents": 3,
            "managed_agents": {
                "enabled": True,
                "delegation_strategy": "agent_sync",
                "include_self": False,
                "total_agents": 4,
                "model": "",
                "require_managed_agents": False,
            },
        },
        "expected_artifacts": ["report.md", "summary.md", "artifacts/"],
        "policy": {
            "allow_cloud_web": True,
            "allow_private_data": False,
            "local_agent_allowed": False,
        },
        "validators": {
            "local": ["validators/validate_report.py"],
            "cloud": [],
        },
    }


def _sample_local_control_task() -> dict[str, Any]:
    return {
        "task_id": "sample_local_control_plan",
        "type": "local_control",
        "mode": "local_control",
        "title": "Sample Local Control Plan",
        "plan": {
            "objective": "Create a local control plan before dispatching a research task to Qoder Cloud.",
        },
        "output": {
            "expected": ["report.md", "summary.md", "artifacts/local_control_plan.json"],
        },
        "policy": {
            "allow_cloud_web": False,
            "allow_private_data": False,
        },
        "validators": ["validators/validate_report.py"],
    }


def _sample_lan_traffic_task() -> dict[str, Any]:
    return {
        "task_id": "sample_lan_traffic_experiment",
        "type": "lan_experiment",
        "mode": "lan_control",
        "title": "Traffic Flow Generation and Prediction LAN Experiment",
        "input": {
            "prompt_file": "tasks/sample_lan_traffic_prompt.md",
        },
        "experiment": {
            "topic": "traffic flow generation and prediction",
            "metrics": ["MAE", "RMSE", "MAPE"],
            "variables": {
                "prediction_horizon_minutes": [15, 30, 60],
                "history_window_minutes": [30, 60, 120],
                "model_family": ["stgcn", "dcrnn", "transformer"],
            },
        },
        "output": {
            "expected": [
                "report.md",
                "summary.md",
                "lan/artifacts/variables.json",
                "lan/artifacts/metrics.json",
                "lan/figures/registry.yaml",
                "lan/tables/registry.yaml",
            ],
            "collect": [
                "report.md",
                "summary.md",
                "artifacts/variables.json",
                "artifacts/metrics.json",
                "artifacts/experiment_plan.json",
                "artifacts/remote_data_contract.json",
                "figures/registry.yaml",
                "tables/registry.yaml",
            ],
        },
        "policy": {
            "allow_cloud_web": False,
            "allow_private_data": False,
            "remote_data_only": True,
            "require_artifact_delivery": True,
        },
        "validators": ["validators/validate_report.py"],
    }


def _sample_prompt() -> str:
    return (
        "Write a concise research note about what an academic harness should track. "
        "Include artifact provenance, validation, and reproducibility.\n"
    )


def _sample_cloud_prompt() -> str:
    return (
        "Design a small academic experiment plan for comparing inference-time scaling "
        "with larger pretrained models on reasoning tasks. Include decomposition, "
        "evidence to collect, expected artifacts, validation checks, and limitations.\n"
    )


def _sample_lan_traffic_prompt() -> str:
    return (
        "Run a remote-only LAN experiment plan for traffic flow generation and prediction. "
        "Use data only on the remote worker. Compare short-horizon forecasting settings, "
        "track variables, register figures/tables, and return only a report, summary, "
        "variable registry, figure registry, table registry, and lightweight metrics metadata.\n"
    )


def _validator_script() -> str:
    return '''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    report = run_dir / "report.md"
    summary = run_dir / "summary.md"
    result = {
        "validator": "validate_report.py",
        "status": "passed",
        "checks": [],
    }

    if not report.exists() or not report.read_text(encoding="utf-8").strip():
        result["status"] = "failed"
        result["checks"].append({"name": "report_exists", "status": "failed"})
    else:
        result["checks"].append({"name": "report_exists", "status": "passed"})

    result["checks"].append({
        "name": "summary_optional",
        "status": "passed" if summary.exists() else "warning",
    })
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
'''
