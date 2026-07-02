from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..timeutil import utc_now_iso
from .qoder_cli import prompt_text_for_task


def run_local_control(
    project_root: Path,
    project: dict[str, Any],
    task: dict[str, Any],
    run_id: str,
    run_dir: Path,
) -> dict[str, Any]:
    qoder_dir = run_dir / "qoder"
    artifacts_dir = qoder_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    prompt = prompt_text_for_task(project_root, task)
    plan = _local_control_plan(project, task, prompt)
    report = _render_report(project, task, run_id, prompt, plan)
    summary = (
        f"Local control run `{run_id}` prepared an execution plan for task "
        f"`{task['task_id']}`. No remote agent was started in this mode.\n"
    )

    (qoder_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    (qoder_dir / "report.md").write_text(report, encoding="utf-8")
    (qoder_dir / "summary.md").write_text(summary, encoding="utf-8")
    (qoder_dir / "events.sse").write_text("", encoding="utf-8")
    (qoder_dir / "events.jsonl").write_text(json.dumps({"event": "local_control.plan", "data": plan}, ensure_ascii=False) + "\n", encoding="utf-8")
    (qoder_dir / "session.json").write_text(json.dumps({"id": f"local_control_{run_id}", "status": "idle"}) + "\n", encoding="utf-8")
    (qoder_dir / "metadata.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "idle",
                "adapter": "local_control",
                "mode": "local_control",
                "created_at": utc_now_iso(),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (artifacts_dir / "local_control_plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return {
        "adapter": "local_control",
        "mode": "local_control",
        "qoder_dir": str(qoder_dir),
        "command": ["local-control"],
        "stdout": "",
        "stderr": "",
    }


def _local_control_plan(project: dict[str, Any], task: dict[str, Any], prompt: str) -> dict[str, Any]:
    expected = list((task.get("output") or {}).get("expected") or ["report.md", "summary.md"])
    validators = list(task.get("validators") or [])
    return {
        "project_id": project.get("project_id"),
        "task_id": task.get("task_id"),
        "mode": "local_control",
        "objective": (task.get("plan") or {}).get("objective") or prompt.strip().splitlines()[0][:200],
        "expected_outputs": expected,
        "validators": validators,
        "suggested_steps": [
            "Review and edit the task prompt.",
            "Run a fake/local-control pass to check expected outputs and validators.",
            "Run qoder_cloud/full_cloud when cloud execution should own decomposition and artifact generation.",
            "Inspect report.md, summary.md, raw events, and validator output before accepting the run.",
        ],
    }


def _render_report(project: dict[str, Any], task: dict[str, Any], run_id: str, prompt: str, plan: dict[str, Any]) -> str:
    steps = "\n".join(f"- {step}" for step in plan["suggested_steps"])
    expected = "\n".join(f"- {item}" for item in plan["expected_outputs"])
    return f"""# Local Control Plan

Run: `{run_id}`

Project: `{project.get("project_id")}`

Task: `{task.get("task_id")}`

Mode: `local_control`

## Objective

{plan["objective"]}

## Expected Outputs

{expected}

## Suggested Control Steps

{steps}

## Prompt Snapshot

```text
{prompt.strip()}
```
"""
