from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

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

