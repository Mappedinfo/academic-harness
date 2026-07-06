from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .run_context import RunContext


Decision = Literal["allow", "deny", "ask"]


@dataclass(frozen=True)
class PolicyDecision:
    decision: Decision
    reasons: list[str] = field(default_factory=list)
    required_approvals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reasons": list(self.reasons),
            "required_approvals": list(self.required_approvals),
            "warnings": list(self.warnings),
        }


def check_preflight(ctx: RunContext) -> PolicyDecision:
    reasons: list[str] = []
    warnings: list[str] = []
    approvals: list[str] = []
    policy = _policy(ctx.task)

    if _adapter_mode_mismatch(ctx):
        approvals.append("adapter_mode_mismatch")
        reasons.append(
            f"requested adapter {ctx.requested_adapter} resolves to {ctx.resolved_adapter}, "
            f"but task mode is {ctx.mode}"
        )

    expected = expected_artifacts(ctx.task)
    if not expected:
        warnings.append("task has no expected artifacts")
        if _bool(policy.get("require_artifact_delivery"), False):
            reasons.append("policy.require_artifact_delivery=true but no expected artifacts are declared")

    if _uses_cloud_runtime(ctx) and not _bool(policy.get("allow_cloud_web"), True):
        reasons.append("cloud runtime requested while policy.allow_cloud_web=false")

    if _uses_cloud_runtime(ctx) and not _bool(policy.get("allow_private_data"), False):
        private_paths = _private_paths(ctx)
        if private_paths:
            reasons.append("full_cloud/hybrid cannot use private paths when policy.allow_private_data=false: " + ", ".join(private_paths))

    if _uses_qoder_cloud(ctx):
        qoder_error = _qoder_config_error(ctx)
        if qoder_error:
            reasons.append(qoder_error)

    if ctx.resolved_adapter == "hybrid":
        local_ai_error = _local_ai_config_error(ctx)
        if local_ai_error:
            reasons.append(local_ai_error)

    if ctx.resolved_adapter == "lan":
        lan_error = _lan_config_error(ctx)
        if lan_error:
            reasons.append(lan_error)

    max_error = _managed_agent_limit_error(ctx)
    if max_error:
        reasons.append(max_error)

    cloud_validators = _cloud_validators(ctx.task)
    if cloud_validators:
        approvals.append("cloud_validators_not_implemented")
        reasons.append("cloud validators are declared but v0.3 only runs artifact and local validators")

    if reasons and approvals and not any(reason.startswith("missing") for reason in reasons):
        return PolicyDecision("ask", reasons=reasons, required_approvals=approvals, warnings=warnings)
    if reasons:
        return PolicyDecision("deny", reasons=reasons, required_approvals=approvals, warnings=warnings)
    if approvals:
        return PolicyDecision("ask", reasons=reasons, required_approvals=approvals, warnings=warnings)
    return PolicyDecision("allow", warnings=warnings)


def check_artifacts(ctx: RunContext, artifacts: list[dict[str, Any]]) -> PolicyDecision:
    policy = _policy(ctx.task)
    if not _bool(policy.get("require_artifact_delivery"), False):
        return PolicyDecision("allow")
    missing = missing_expected_artifacts(ctx.run_dir, ctx.task, artifacts)
    if missing:
        return PolicyDecision("deny", reasons=["required artifacts missing: " + ", ".join(missing)])
    return PolicyDecision("allow")


def expected_artifacts(task: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    output = task.get("output")
    if isinstance(output, dict):
        expected = output.get("expected")
        if isinstance(expected, list):
            values.extend(expected)
        elif isinstance(expected, str):
            values.append(expected)
    expected_artifacts_value = task.get("expected_artifacts")
    if isinstance(expected_artifacts_value, list):
        values.extend(expected_artifacts_value)
    elif isinstance(expected_artifacts_value, str):
        values.append(expected_artifacts_value)
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def missing_expected_artifacts(run_dir: Path, task: dict[str, Any], artifacts: list[dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    artifact_paths = [Path(str(item.get("path"))) for item in artifacts if item.get("path")]
    for expected in expected_artifacts(task):
        if _expected_exists(run_dir, expected, artifact_paths):
            continue
        missing.append(expected)
    return missing


def _expected_exists(run_dir: Path, expected: str, artifact_paths: list[Path]) -> bool:
    normalized = expected.rstrip("/")
    if expected.endswith("/"):
        directory = run_dir / normalized
        if directory.exists() and any(directory.iterdir()):
            return True
        qoder_directory = run_dir / "qoder" / normalized
        if qoder_directory.exists() and any(qoder_directory.iterdir()):
            return True
        return any(
            path.exists()
            and (_is_relative_to(path, run_dir / normalized) or _is_relative_to(path, run_dir / "qoder" / normalized))
            for path in artifact_paths
        )
    candidate = run_dir / expected
    if candidate.exists():
        return True
    return any(path.exists() and (path.name == Path(expected).name or str(path).endswith(expected)) for path in artifact_paths)


def _adapter_mode_mismatch(ctx: RunContext) -> bool:
    if ctx.requested_adapter in {"auto", "fake"}:
        return False
    declared_mode = str(ctx.task.get("mode") or ctx.mode)
    expected = {
        "full_cloud": {"qoder_cloud", "hybrid"},
        "hybrid": {"hybrid"},
        "local_control": {"local_control", "qoder_cli"},
        "lan_control": {"lan"},
        "fake": {"fake"},
    }.get(declared_mode)
    return bool(expected and ctx.resolved_adapter not in expected)


def _uses_cloud_runtime(ctx: RunContext) -> bool:
    return ctx.resolved_adapter in {"qoder_cloud", "hybrid"}


def _uses_qoder_cloud(ctx: RunContext) -> bool:
    return ctx.resolved_adapter in {"qoder_cloud", "hybrid"}


def _qoder_config_error(ctx: RunContext) -> str | None:
    try:
        from ..executors.qoder_cloud import resolve_qoder_cloud_config

        resolve_qoder_cloud_config(ctx.project_root, ctx.project, ctx.task)
    except Exception as exc:
        return f"missing or invalid Qoder cloud config: {exc}"
    return None


def _local_ai_config_error(ctx: RunContext) -> str | None:
    try:
        from ..local_ai import resolve_local_ai_config

        resolve_local_ai_config(ctx.project)
    except Exception as exc:
        return f"missing or invalid local_ai config: {exc}"
    return None


def _lan_config_error(ctx: RunContext) -> str | None:
    lan: dict[str, Any] = {}
    if isinstance(ctx.project.get("lan"), dict):
        lan.update(ctx.project["lan"])
    for key in ["lan", "remote"]:
        if isinstance(ctx.task.get(key), dict):
            lan.update(ctx.task[key])
    if not _bool(lan.get("enabled"), False):
        return "LAN experiment requested but project/task LAN is disabled"
    if not str(lan.get("ssh_alias") or "").strip():
        return "LAN experiment requested but ssh_alias is missing"
    if not str(lan.get("project_root") or "").strip():
        return "LAN experiment requested but project_root is missing"
    return None


def _managed_agent_limit_error(ctx: RunContext) -> str | None:
    if ctx.resolved_adapter not in {"qoder_cloud", "hybrid"}:
        return None
    managed = _managed_agent_config(ctx)
    if not _bool(managed.get("enabled"), False):
        return None
    total_agents = _int(managed.get("total_agents"), 4)
    max_child_agents = _int(
        _policy(ctx.task).get("max_child_agents")
        or ((ctx.task.get("coordinator") or {}).get("max_child_agents") if isinstance(ctx.task.get("coordinator"), dict) else None)
        or managed.get("max_child_agents")
        or 4,
        4,
    )
    child_agents = max(0, total_agents - 1)
    if child_agents > max_child_agents:
        return f"managed_agents requests {child_agents} child agents, policy limit is {max_child_agents}"
    return None


def _managed_agent_config(ctx: RunContext) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    qoder = ctx.project.get("qoder") if isinstance(ctx.project.get("qoder"), dict) else {}
    if isinstance(qoder.get("managed_agents"), dict):
        merged.update(qoder["managed_agents"])
    coordinator = ctx.task.get("coordinator") if isinstance(ctx.task.get("coordinator"), dict) else {}
    if isinstance(coordinator.get("managed_agents"), dict):
        merged.update(coordinator["managed_agents"])
    if isinstance(ctx.task.get("managed_agents"), dict):
        merged.update(ctx.task["managed_agents"])
    return merged


def _private_paths(ctx: RunContext) -> list[str]:
    paths: list[str] = []
    for value in _declared_input_paths(ctx.task):
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = ctx.project_root / path
        if _is_relative_to(path, ctx.project_root):
            if "private" in str(path.relative_to(ctx.project_root)).lower():
                paths.append(str(path))
            continue
        paths.append(str(path))
    return paths


def _declared_input_paths(task: dict[str, Any]) -> list[str]:
    values: list[str] = []
    input_config = task.get("input") if isinstance(task.get("input"), dict) else {}
    for key in ("prompt_file", "file", "path"):
        value = input_config.get(key)
        if isinstance(value, str):
            values.append(value)
    files = input_config.get("files")
    if isinstance(files, list):
        values.extend(str(item) for item in files if item)
    data = task.get("data") if isinstance(task.get("data"), dict) else {}
    for key in ("paths", "private_paths"):
        raw_paths = data.get(key)
        if isinstance(raw_paths, list):
            values.extend(str(item) for item in raw_paths if item)
    return values


def _cloud_validators(task: dict[str, Any]) -> list[Any]:
    validators = task.get("validators")
    if not isinstance(validators, dict):
        return []
    cloud = validators.get("cloud") or []
    if isinstance(cloud, list):
        return cloud
    return [cloud] if cloud else []


def _policy(task: dict[str, Any]) -> dict[str, Any]:
    policy = task.get("policy")
    return policy if isinstance(policy, dict) else {}


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


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True
