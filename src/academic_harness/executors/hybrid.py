from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from ..local_ai import LocalAIClient, LocalAIError, parse_json_or_text, resolve_local_ai_config
from ..timeutil import utc_now_iso
from .qoder_cli import prompt_text_for_task
from .qoder_cloud import run_qoder_cloud


def run_hybrid(
    project_root: Path,
    project: dict[str, Any],
    task: dict[str, Any],
    run_id: str,
    run_dir: Path,
) -> dict[str, Any]:
    local_ai_dir = run_dir / "local_ai"
    local_ai_dir.mkdir(parents=True, exist_ok=True)
    try:
        config = resolve_local_ai_config(project, project_root=project_root)
        client = LocalAIClient(config)
        prompt = prompt_text_for_task(project_root, task)
        (local_ai_dir / "input_prompt.md").write_text(prompt, encoding="utf-8")

        preflight = _run_preflight(client, project, task, run_id, prompt)
        _write_json(local_ai_dir / "preflight.json", preflight)
        (local_ai_dir / "prompt_review.md").write_text(preflight["prompt_review"], encoding="utf-8")
        (local_ai_dir / "cloud_prompt.md").write_text(preflight["cloud_prompt"], encoding="utf-8")
        (local_ai_dir / "risk_report.md").write_text(preflight["risk_report"], encoding="utf-8")
        (local_ai_dir / "prompt_patch.md").write_text(preflight["prompt_patch"], encoding="utf-8")
        _write_json(local_ai_dir / "policy_warnings.json", preflight["policy_warnings"])

        cloud_task = _cloud_task_for_hybrid(task, local_ai_dir / "cloud_prompt.md")
        qoder_result = run_qoder_cloud(project_root, project, cloud_task, run_id, run_dir)
        if qoder_result.get("status") in {"failed", "cancelled"}:
            return _failed_result(run_dir, local_ai_dir, "qoder_cloud_failed", str(qoder_result.get("stop_reason") or "Qoder cloud failed"), qoder_result)

        postflight = _run_postflight(client, project, task, run_id, run_dir, qoder_result)
        _write_json(local_ai_dir / "validator_notes.json", postflight["validator_notes"])
        _write_json(local_ai_dir / "suspected_issues.json", postflight["suspected_issues"])
        (local_ai_dir / "review.md").write_text(postflight["review"], encoding="utf-8")
        (local_ai_dir / "audit_report.md").write_text(postflight["audit_report"], encoding="utf-8")
        (local_ai_dir / "artifact_summary.md").write_text(postflight["artifact_summary"], encoding="utf-8")
        (local_ai_dir / "final_report.md").write_text(postflight["final_report"], encoding="utf-8")

        _write_top_level_outputs(run_dir, postflight)
        metadata = {
            "run_id": run_id,
            "adapter": "hybrid",
            "mode": "hybrid",
            "status": "succeeded",
            "created_at": utc_now_iso(),
            "local_ai": config.safe_metadata(),
            "qoder_result": _safe_qoder_result(qoder_result),
            "preflight_path": str(local_ai_dir / "preflight.json"),
            "review_path": str(local_ai_dir / "review.md"),
            "final_report_path": str(local_ai_dir / "final_report.md"),
        }
        _write_json(local_ai_dir / "metadata.json", metadata)
        return {
            "adapter": "hybrid",
            "mode": "hybrid",
            "status": "succeeded",
            "run_dir": str(run_dir),
            "qoder_dir": str(run_dir / "qoder"),
            "local_ai_dir": str(local_ai_dir),
            "metadata_path": str(local_ai_dir / "metadata.json"),
            "qoder_result": qoder_result,
        }
    except Exception as exc:
        return _failed_result(run_dir, local_ai_dir, "hybrid_failed", str(exc), None)


def normalize_hybrid_outputs(run_dir: Path, result: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for filename, kind in [("report.md", "report"), ("summary.md", "summary")]:
        path = run_dir / filename
        if path.exists():
            artifacts.append(_artifact_record(path, kind))

    local_ai_dir = Path(result.get("local_ai_dir") or run_dir / "local_ai")
    if local_ai_dir.exists():
        for path in sorted(local_ai_dir.iterdir()):
            if path.is_file():
                artifacts.append(_artifact_record(path, "local_ai"))

    qoder_dir = Path(result.get("qoder_dir") or run_dir / "qoder")
    for raw_name in [
        "metadata.json",
        "session.json",
        "events.sse",
        "events.jsonl",
        "prompt.txt",
        "agent_roster.json",
        "threads.json",
        "delegations.jsonl",
        "report.md",
        "summary.md",
    ]:
        raw_path = qoder_dir / raw_name
        if raw_path.exists():
            artifacts.append(_artifact_record(raw_path, "qoder_raw"))
    artifact_dir = qoder_dir / "artifacts"
    if artifact_dir.exists():
        for path in sorted(artifact_dir.iterdir()):
            if path.is_file():
                artifacts.append(_artifact_record(path, "qoder_artifact"))
    return artifacts


def _run_preflight(
    client: LocalAIClient,
    project: dict[str, Any],
    task: dict[str, Any],
    run_id: str,
    prompt: str,
) -> dict[str, Any]:
    content = client.chat(
        [
            {
                "role": "system",
                "content": (
                    "You are the local controller for an academic harness. Review the user task, decompose it, "
                    "and produce a Qoder Cloud dispatch prompt. Return JSON with keys prompt_review, cloud_prompt, "
                    "risk_report, prompt_patch, and policy_warnings. Local preflight is advisory only: do not rewrite "
                    "the task or validator contract."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Run ID: {run_id}\n"
                    f"Project: {project.get('project_id')}\n"
                    f"Task: {task.get('task_id')} ({task.get('type')})\n\n"
                    f"Original prompt:\n{prompt}"
                ),
            },
        ],
        temperature=0.2,
    )
    parsed = parse_json_or_text(content)
    prompt_review = str(parsed.get("prompt_review") or parsed.get("review") or parsed.get("text") or content).strip()
    cloud_prompt = str(parsed.get("cloud_prompt") or "").strip()
    if not cloud_prompt:
        cloud_prompt = _fallback_cloud_prompt(project, task, run_id, prompt, prompt_review)
    risk_report = str(parsed.get("risk_report") or prompt_review).strip()
    prompt_patch = str(parsed.get("prompt_patch") or cloud_prompt).strip()
    policy_warnings = parsed.get("policy_warnings")
    if not isinstance(policy_warnings, dict):
        policy_warnings = {"warnings": policy_warnings if isinstance(policy_warnings, list) else []}
    return {
        "run_id": run_id,
        "created_at": utc_now_iso(),
        "prompt_review": prompt_review,
        "cloud_prompt": cloud_prompt,
        "risk_report": risk_report + "\n",
        "prompt_patch": prompt_patch + "\n",
        "policy_warnings": policy_warnings,
        "raw_response": content,
    }


def _run_postflight(
    client: LocalAIClient,
    project: dict[str, Any],
    task: dict[str, Any],
    run_id: str,
    run_dir: Path,
    qoder_result: dict[str, Any],
) -> dict[str, Any]:
    qoder_dir = Path(qoder_result.get("qoder_dir") or run_dir / "qoder")
    report = _read_optional(qoder_dir / "report.md")
    summary = _read_optional(qoder_dir / "summary.md")
    metadata = _read_optional(qoder_dir / "metadata.json")
    if not report.strip():
        raise LocalAIError("Qoder report.md is missing or empty; cannot run local postflight")
    content = client.chat(
        [
            {
                "role": "system",
                "content": (
                    "You are the local academic reviewer and integrator. Review Qoder output, preserve evidence, "
                    "flag weaknesses, and produce the final report. Return JSON with final_report, review, summary, "
                    "validator_notes, audit_report, artifact_summary, and suspected_issues. Local postflight is "
                    "advisory: it may identify issues and integrate a report, but it does not decide whether the run passes."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Run ID: {run_id}\nProject: {project.get('project_id')}\nTask: {task.get('task_id')}\n\n"
                    f"Qoder summary:\n{summary}\n\nQoder metadata:\n{metadata[:4000]}\n\nQoder report:\n{report}"
                ),
            },
        ],
        temperature=0.2,
    )
    parsed = parse_json_or_text(content)
    final_report = str(parsed.get("final_report") or parsed.get("report") or parsed.get("text") or content).strip()
    review = str(parsed.get("review") or parsed.get("validator_review") or "Local AI review completed.").strip()
    summary_text = str(parsed.get("summary") or "Hybrid AI run completed.").strip()
    validator_notes = parsed.get("validator_notes")
    if not isinstance(validator_notes, dict):
        validator_notes = {"status": "reviewed", "notes": review}
    suspected_issues = parsed.get("suspected_issues")
    if not isinstance(suspected_issues, dict):
        suspected_issues = {"issues": suspected_issues if isinstance(suspected_issues, list) else []}
    audit_report = str(parsed.get("audit_report") or review).strip()
    artifact_summary = str(parsed.get("artifact_summary") or summary_text).strip()
    return {
        "final_report": final_report + "\n",
        "review": review + "\n",
        "summary": summary_text + "\n",
        "validator_notes": validator_notes,
        "audit_report": audit_report + "\n",
        "artifact_summary": artifact_summary + "\n",
        "suspected_issues": suspected_issues,
        "raw_response": content,
    }


def _cloud_task_for_hybrid(task: dict[str, Any], cloud_prompt_path: Path) -> dict[str, Any]:
    cloud_task = copy.deepcopy(task)
    cloud_task["mode"] = "full_cloud"
    cloud_task["input"] = {"prompt_file": str(cloud_prompt_path)}
    cloud_task["hybrid"] = {"source_task_id": task.get("task_id")}
    return cloud_task


def _fallback_cloud_prompt(project: dict[str, Any], task: dict[str, Any], run_id: str, prompt: str, review: str) -> str:
    return f"""You are the Qoder Cloud execution agent for an Academic Harness hybrid run.

Run ID: {run_id}
Project: {project.get('project_id')}
Task: {task.get('task_id')}

Local preflight review:
{review}

Dispatch instructions:
- Use Qoder Cloud for web/evidence search, synthesis, and artifact writing.
- If managed agents are available, delegate search, synthesis, writing, and review.
- Write the primary document with the Write tool as report.md.
- Keep the final assistant message as a concise summary.

Original user task:
{prompt.strip()}
"""


def _write_top_level_outputs(run_dir: Path, postflight: dict[str, Any]) -> None:
    (run_dir / "report.md").write_text(str(postflight["final_report"]), encoding="utf-8")
    (run_dir / "summary.md").write_text(str(postflight["summary"]), encoding="utf-8")


def _failed_result(
    run_dir: Path,
    local_ai_dir: Path,
    error_type: str,
    message: str,
    qoder_result: dict[str, Any] | None,
) -> dict[str, Any]:
    local_ai_dir.mkdir(parents=True, exist_ok=True)
    error = {
        "type": error_type,
        "message": message,
        "created_at": utc_now_iso(),
        "qoder_result": _safe_qoder_result(qoder_result or {}),
    }
    _write_json(local_ai_dir / "error.json", error)
    return {
        "adapter": "hybrid",
        "mode": "hybrid",
        "status": "failed",
        "stop_reason": message,
        "run_dir": str(run_dir),
        "qoder_dir": str(run_dir / "qoder"),
        "local_ai_dir": str(local_ai_dir),
        "error_path": str(local_ai_dir / "error.json"),
        "qoder_result": qoder_result,
    }


def _safe_qoder_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in result.items()
        if key not in {"stdout", "stderr", "command"} and isinstance(value, (str, int, float, bool, type(None), dict, list))
    }


def _read_optional(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _artifact_record(path: Path, kind: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "path": str(path),
        "size": path.stat().st_size,
    }
