from __future__ import annotations

from pathlib import Path
from typing import Any

from .index import init_index
from .paths import PROJECT_FILE, WORKBENCH_DIR, find_project_root, workbench_dir
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


def load_project(path: Path) -> tuple[Path, dict[str, Any]]:
    root = find_project_root(path)
    return root, load_yaml(root / PROJECT_FILE)


def ensure_project_dirs(project_root: Path) -> None:
    for folder in ["tasks", "validators", "manuscript", "figures", "tables"]:
        (project_root / folder).mkdir(parents=True, exist_ok=True)
    workbench_dir(project_root).mkdir(parents=True, exist_ok=True)
    (workbench_dir(project_root) / "runs").mkdir(parents=True, exist_ok=True)
    init_index(project_root)


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
            "config": "../qoder-agent-runner/config.local.json",
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
