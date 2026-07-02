from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .kernel.policy_gate import expected_artifacts, missing_expected_artifacts
from .yamlio import write_json


def run_validators(
    project_root: Path,
    run_dir: Path,
    manifest_path: Path,
    validator_paths: list[str],
) -> list[dict[str, Any]]:
    validation_dir = run_dir / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    for validator in validator_paths:
        validator_path = _resolve_project_path(project_root, validator)
        report_path = validation_dir / f"{validator_path.stem}.json"
        if not validator_path.exists():
            result = {
                "validator": validator,
                "status": "failed",
                "error": f"Validator not found: {validator_path}",
                "report_path": str(report_path),
            }
            write_json(report_path, result)
            results.append(result)
            continue

        completed = subprocess.run(
            [
                sys.executable,
                str(validator_path),
                "--run-dir",
                str(run_dir),
                "--manifest",
                str(manifest_path),
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        result = _parse_validator_output(validator, completed.stdout)
        result.setdefault("validator", validator)
        result["status"] = "passed" if completed.returncode == 0 and result.get("status") == "passed" else "failed"
        result["returncode"] = completed.returncode
        result["stdout"] = completed.stdout
        result["stderr"] = completed.stderr
        result["report_path"] = str(report_path)
        write_json(report_path, result)
        results.append(result)

    return results


def run_artifact_validators(
    run_dir: Path,
    manifest_path: Path,
    task: dict[str, Any],
    artifacts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    validation_dir = run_dir / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    report_path = validation_dir / "artifact_contract.json"
    checks: list[dict[str, Any]] = []
    expected = expected_artifacts(task)
    policy = task.get("policy") if isinstance(task.get("policy"), dict) else {}
    require_artifact_delivery = _bool(policy.get("require_artifact_delivery"), False)

    if expected:
        missing = missing_expected_artifacts(run_dir, task, artifacts)
        for item in expected:
            checks.append(
                {
                    "name": f"expected:{item}",
                    "status": "failed" if item in missing else "passed",
                }
            )
    else:
        checks.append(
            {
                "name": "expected_artifacts_declared",
                "status": "failed" if require_artifact_delivery else "warning",
                "message": "no expected artifacts declared",
            }
        )

    artifact_policy = task.get("artifact_validator") if isinstance(task.get("artifact_validator"), dict) else {}
    min_report_chars = _int(artifact_policy.get("min_report_chars"), 0)
    if min_report_chars:
        report = run_dir / "report.md"
        report_chars = len(report.read_text(encoding="utf-8")) if report.exists() else 0
        checks.append(
            {
                "name": "min_report_chars",
                "status": "passed" if report_chars >= min_report_chars else "failed",
                "actual": report_chars,
                "minimum": min_report_chars,
            }
        )

    if _bool(artifact_policy.get("require_events_jsonl"), False):
        events = run_dir / "qoder" / "events.jsonl"
        checks.append(
            {
                "name": "events_jsonl",
                "status": "passed" if events.exists() and events.stat().st_size >= 0 else "failed",
                "path": str(events),
            }
        )

    status = "failed" if any(check["status"] == "failed" for check in checks) else "passed"
    result = {
        "validator": "artifact_contract",
        "status": status,
        "checks": checks,
        "manifest": str(manifest_path),
        "report_path": str(report_path),
    }
    write_json(report_path, result)
    return [result]


def _resolve_project_path(project_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_root / path


def _parse_validator_output(validator: str, stdout: str) -> dict[str, Any]:
    if not stdout.strip():
        return {"validator": validator, "status": "failed", "error": "Validator produced no JSON output"}
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {
            "validator": validator,
            "status": "failed",
            "error": "Validator stdout was not JSON",
            "raw_stdout": stdout,
        }
    return data if isinstance(data, dict) else {"validator": validator, "status": "failed", "raw_stdout": stdout}


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
