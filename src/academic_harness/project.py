from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .index import init_index
from .paths import PROJECT_FILE, WORKBENCH_DIR, find_project_root, workbench_dir
from .qoder_dependency import discover_qoder_runner
from .yamlio import dump_yaml, load_yaml


def init_project(project_dir: Path, force: bool = False) -> Path:
    project_dir = project_dir.resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    _write_if_missing(project_dir / PROJECT_FILE, dump_yaml(_default_project(project_dir.name)), force)

    for folder in ["tasks", "validators", "manuscript", "figures", "tables", f"{WORKBENCH_DIR}/runs"]:
        (project_dir / folder).mkdir(parents=True, exist_ok=True)

    _write_if_missing(project_dir / "tasks" / "sample_prompt.md", _sample_prompt(), force)
    _write_if_missing(project_dir / "tasks" / "sample_task.yaml", dump_yaml(_sample_task()), force)
    _write_if_missing(project_dir / "validators" / "validate_report.py", _validator_script(), force)
    _write_if_missing(project_dir / "manuscript" / "main.qmd", "# Manuscript\n\n", force)
    _write_if_missing(project_dir / "figures" / "registry.yaml", "figures:\n", force)
    _write_if_missing(project_dir / "tables" / "registry.yaml", "tables:\n", force)
    init_index(project_dir)
    return project_dir


def project_status(project_dir: Path, check_lan: bool = False) -> dict[str, Any]:
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


def load_project(path: Path) -> tuple[Path, dict[str, Any]]:
    root = find_project_root(path)
    return root, load_yaml(root / PROJECT_FILE)


def ensure_project_dirs(project_root: Path) -> None:
    for folder in ["tasks", "validators", "manuscript", "figures", "tables"]:
        (project_root / folder).mkdir(parents=True, exist_ok=True)
    workbench_dir(project_root).mkdir(parents=True, exist_ok=True)
    (workbench_dir(project_root) / "runs").mkdir(parents=True, exist_ok=True)
    init_index(project_root)


def _qoder_status(project_dir: Path, project: dict[str, Any]) -> dict[str, Any]:
    return discover_qoder_runner(project_dir, project, check_help=True)


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
            "figures_dir": "figures",
            "tables_dir": "tables",
        },
        "qoder": {
            "runner_command": "qoder-run",
            "profile": "default",
        },
    }


def _sample_task() -> dict[str, Any]:
    return {
        "task_id": "sample_qoder_report",
        "type": "qoder_research",
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


def _sample_prompt() -> str:
    return (
        "Write a concise research note about what an academic harness should track. "
        "Include artifact provenance, validation, and reproducibility.\n"
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
