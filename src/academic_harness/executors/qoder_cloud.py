from __future__ import annotations

import json
import os
import signal
import hashlib
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ..kernel.trace_writer import write_qoder_thread_trace
from ..paths import WORKBENCH_DIR
from ..qoder_dependency import default_registry_path, discover_qoder_runner
from .qoder_cli import prompt_text_for_task


class QoderCloudError(RuntimeError):
    pass


class QoderCloudHTTPError(QoderCloudError):
    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"Qoder HTTP {status_code}: {body}")
        self.status_code = status_code
        self.body = body


class QoderCloudCancelled(RuntimeError):
    pass


class QoderManagedAgentModelError(QoderCloudError):
    pass


@dataclass(frozen=True)
class QoderCloudConfig:
    base_url: str
    agent_id: str
    environment_id: str
    token: str
    profile: str
    config_path: Path | None
    agent_version: str | None = None
    managed_agents: dict[str, Any] | None = None


@dataclass(frozen=True)
class ManagedAgentSettings:
    enabled: bool
    require_managed_agents: bool
    total_agents: int
    model: str
    requested_model: str | None
    model_source: str
    available_models: tuple[dict[str, Any], ...]
    mode: str
    agent_set_name: str
    agent_set_id: str
    delegation_strategy: str
    include_self: bool


@dataclass(frozen=True)
class MultiagentConfig:
    agents: tuple[dict[str, Any], ...]
    include_self: bool = False

    def to_payload(self) -> dict[str, Any]:
        entries = [dict(agent) for agent in self.agents]
        if self.include_self:
            entries.append({"type": "self"})
        return {"type": "coordinator", "agents": entries}


COORDINATOR_TOOLSET = {
    "type": "agent_toolset_20260401",
    "enabled_tools": ["Read", "Write", "WebFetch", "WebSearch", "DeliverArtifacts"],
}
WORKER_TOOLSET = {
    "type": "agent_toolset_20260401",
    "enabled_tools": ["Read", "Write", "WebFetch", "WebSearch", "DeliverArtifacts"],
}
QODER_RUNTIME_COORDINATOR_TOOLS = {"Agent", "create_agent", "send_to_agent", "list_agents"}
ROLE_LIBRARY: dict[str, dict[str, str]] = {
    "evidence_searcher": {
        "label": "Evidence Searcher",
        "description": "Collects current web evidence, source links, key claims, and contradictions for the research task.",
        "system": (
            "You are an academic evidence search worker. Search broadly, prefer primary or high-quality sources, "
            "record URLs, dates, claims, and uncertainty. When complete, call the injected send_to_parent tool "
            "with concise structured evidence notes for the coordinator. Finish in one response: return 8-12 "
            "high-signal findings, and send best-effort partial results rather than continuing to search indefinitely."
        ),
    },
    "method_synthesizer": {
        "label": "Method Synthesizer",
        "description": "Organizes evidence into methods, comparison axes, assumptions, and experiment-ready structure.",
        "system": (
            "You are an academic method synthesis worker. Turn evidence into comparison dimensions, assumptions, "
            "methodological risks, and validation ideas. Do not write the final report unless asked. When complete, "
            "call the injected send_to_parent tool with your structured synthesis. Finish in one response with "
            "bounded sections and send partial synthesis rather than waiting for exhaustive coverage."
        ),
    },
    "report_writer_reviewer": {
        "label": "Report Writer Reviewer",
        "description": "Drafts and reviews the final report for completeness, citations, limitations, and artifact quality.",
        "system": (
            "You are an academic report writing and review worker. Produce polished sections, check whether claims "
            "are supported, and flag missing citations or weak reasoning before final delivery. When complete, "
            "call the injected send_to_parent tool with the draft or review notes. Finish in one response and keep "
            "the result concise enough for the coordinator to synthesize immediately."
        ),
    },
    "critic_validator": {
        "label": "Critic Validator",
        "description": "Stress-tests the draft, finds missing counterevidence, and checks validator/readability requirements.",
        "system": (
            "You are a strict academic critic and validator. Look for overclaims, missing counterexamples, weak "
            "source support, reproducibility gaps, and artifact contract violations. When complete, call the injected "
            "send_to_parent tool with the critique and required fixes. Finish in one response and send partial "
            "findings rather than waiting for exhaustive validation."
        ),
    },
}


class QoderCloudClient:
    def __init__(self, config: QoderCloudConfig, request_timeout: int = 120) -> None:
        self.config = config
        self.request_timeout = request_timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def create_session(self, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "agent": self.config.agent_id,
            "environment_id": self.config.environment_id,
        }
        if metadata:
            payload["metadata"] = metadata
        return self._request_json("POST", "sessions", payload)

    def send_message(self, session_id: str, text: str) -> dict[str, Any]:
        payload = {
            "events": [
                {
                    "type": "user.message",
                    "content": [{"type": "text", "text": text}],
                }
            ]
        }
        return self._request_json("POST", f"sessions/{session_id}/events", payload)

    def stream_events(self, session_id: str):
        request = urllib.request.Request(
            self._url(f"sessions/{session_id}/events/stream"),
            headers={
                "Authorization": f"Bearer {self.config.token}",
                "Accept": "text/event-stream",
                "User-Agent": "academic-harness-qoder-cloud/0.2",
            },
            method="GET",
        )
        try:
            return self.opener.open(request, timeout=self.request_timeout)
        except urllib.error.URLError as exc:
            raise QoderCloudError(f"Qoder event stream failed: {exc}") from exc

    def cancel_session(self, session_id: str) -> dict[str, Any]:
        return self._request_json("POST", f"sessions/{session_id}/cancel", {})

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        return self._request_json("GET", f"agents/{agent_id}", None)

    def list_models(self) -> dict[str, Any]:
        return self._request_json("GET", "models", None)

    def create_agent(self, payload: dict[str, Any], idempotency_key: str | None = None) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self._request_json("POST", "agents", payload, extra_headers=headers)

    def update_agent(self, agent_id: str, version: int, payload: dict[str, Any]) -> dict[str, Any]:
        body = dict(payload)
        body["version"] = version
        return self._request_json("POST", f"agents/{agent_id}", body)

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.config.token}",
            "Accept": "application/json",
            "User-Agent": "academic-harness-qoder-cloud/0.2",
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if extra_headers:
            headers.update(extra_headers)
        request = urllib.request.Request(
            self._url(path),
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with self.opener.open(request, timeout=self.request_timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise QoderCloudHTTPError(exc.code, error_body) from exc
        except urllib.error.URLError as exc:
            raise QoderCloudError(f"Qoder request failed: {exc}") from exc
        if not body.strip():
            return {}
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise QoderCloudError(f"Qoder returned non-JSON response: {body[:200]}") from exc
        if not isinstance(parsed, dict):
            return {"value": parsed}
        return parsed

    def _url(self, path: str) -> str:
        return f"{self.config.base_url.rstrip('/')}/{path.lstrip('/')}"


def run_qoder_cloud(
    project_root: Path,
    project: dict[str, Any],
    task: dict[str, Any],
    run_id: str,
    run_dir: Path,
) -> dict[str, Any]:
    qoder_dir = run_dir / "qoder"
    qoder_dir.mkdir(parents=True, exist_ok=True)

    config = resolve_qoder_cloud_config(project_root, project, task)
    client = QoderCloudClient(config)
    managed_runtime = ensure_managed_agent_set(project_root, project, task, client, config)
    if managed_runtime.get("active") and isinstance(managed_runtime.get("coordinator"), dict):
        coordinator = managed_runtime["coordinator"]
        config = replace(
            config,
            agent_id=str(coordinator["id"]),
            agent_version=str(coordinator.get("version")) if coordinator.get("version") is not None else None,
        )
        client = QoderCloudClient(config)
    (qoder_dir / "agent_roster.json").write_text(
        json.dumps(managed_runtime, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    prompt = _build_cloud_prompt(project_root, project, task, run_id, managed_runtime)
    (qoder_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    metadata = _string_metadata(
        {
            "run_id": run_id,
            "project_id": project.get("project_id") or project.get("project", {}).get("id") or project.get("id"),
            "task_id": task.get("task_id"),
            "task_type": task.get("type"),
            "mode": "full_cloud",
            "profile": config.profile,
        }
    )

    status = "running"
    stop_reason = "unknown"
    session_id = ""
    cancel_detail = "cancelled"
    previous_handlers: dict[int, Any] = {}

    def cancel_handler(signum: int, frame: Any) -> None:
        nonlocal cancel_detail
        if session_id:
            try:
                client.cancel_session(session_id)
                cancel_detail = f"cancelled; remote cancel requested for {session_id}"
            except Exception as exc:
                cancel_detail = f"cancelled; remote cancel failed: {exc}"
        raise QoderCloudCancelled(cancel_detail)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            previous_handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, cancel_handler)
        except (ValueError, OSError):
            pass

    try:
        session = client.create_session(metadata=metadata)
        (qoder_dir / "session.json").write_text(
            json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        session_id = _extract_session_id(session)
        if not session_id:
            raise QoderCloudError("Qoder create session response did not include a session id")
        client.send_message(session_id, prompt)
        stream_summary = _stream_and_extract(client, session_id, qoder_dir, run_id)
        stream_errors = stream_summary.get("errors", [])
        if stream_errors:
            status = "failed"
            stop_reason = _stream_error_reason(stream_errors)
        else:
            status = "succeeded" if stream_summary["idle_seen"] else "failed"
            stop_reason = "session.status_idle" if stream_summary["idle_seen"] else "stream ended before idle"
    except QoderCloudCancelled as exc:
        status = "cancelled"
        stop_reason = str(exc)
        stream_summary = _empty_stream_summary()
        _ensure_raw_event_files(qoder_dir)
    except Exception as exc:
        status = "failed"
        stop_reason = str(exc)
        stream_summary = _empty_stream_summary(errors=[{"type": "exception", "message": str(exc)}])
        _ensure_raw_event_files(qoder_dir)
    finally:
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
    finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    output_metadata = {
        "run_id": run_id,
        "status": status,
        "stop_reason": stop_reason,
        "started_at": started_at,
        "finished_at": finished_at,
        "mode": "full_cloud",
        "adapter": "qoder_cloud",
        "profile": config.profile,
        "base_url": config.base_url,
        "config_path": str(config.config_path) if config.config_path else None,
        "session_id": session_id or None,
        "managed_agents": managed_runtime,
        "report_path": str((qoder_dir / "report.md").resolve()) if (qoder_dir / "report.md").exists() else None,
        "summary_path": str((qoder_dir / "summary.md").resolve()) if (qoder_dir / "summary.md").exists() else None,
        "artifacts": stream_summary.get("writes", []),
        "delivered_artifacts": stream_summary.get("delivered", []),
        "thread_events": stream_summary.get("thread_events", []),
        "thread_trace": stream_summary.get("thread_trace"),
        "errors": stream_summary.get("errors", []),
    }
    (qoder_dir / "metadata.json").write_text(
        json.dumps(output_metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "adapter": "qoder_cloud",
        "mode": "full_cloud",
        "status": status,
        "stop_reason": stop_reason,
        "qoder_dir": str(qoder_dir),
        "run_dir": str(qoder_dir),
        "session_id": session_id or None,
        "managed_agents": managed_runtime,
        "metadata_path": str(qoder_dir / "metadata.json"),
    }


def resolve_qoder_cloud_config(
    project_root: Path,
    project: dict[str, Any],
    task: dict[str, Any] | None = None,
) -> QoderCloudConfig:
    config_path, profile = _discover_qoder_config(project_root, project)
    raw_config = _read_json(config_path) if config_path else {}
    profile_config = _profile_config(raw_config, profile)
    qoder_project = project.get("qoder", {}) if isinstance(project.get("qoder"), dict) else {}
    coordinator = task.get("coordinator", {}) if task and isinstance(task.get("coordinator"), dict) else {}

    base_url = (
        coordinator.get("base_url")
        or profile_config.get("base_url")
        or qoder_project.get("base_url")
        or "https://api.qoder.com.cn/api/v1/cloud"
    )
    agent_id = coordinator.get("agent_id") or profile_config.get("agent_id") or profile_config.get("agent")
    environment_id = (
        coordinator.get("environment_id")
        or profile_config.get("environment_id")
        or profile_config.get("environment")
    )
    agent_version = coordinator.get("agent_version") or profile_config.get("agent_version")
    token_env = str(profile_config.get("token_env") or qoder_project.get("token_env") or "QODER_PAT")
    env_file = profile_config.get("env_file") or qoder_project.get("env_file")
    token = _resolve_token(token_env, config_path, env_file)
    managed_agents = _merged_managed_agent_config(profile_config, qoder_project, task)
    missing = []
    if not agent_id:
        missing.append("agent_id")
    if not environment_id:
        missing.append("environment_id")
    if not token:
        missing.append(token_env)
    if missing:
        raise QoderCloudError(f"missing Qoder cloud config: {', '.join(missing)}")
    return QoderCloudConfig(
        base_url=str(base_url),
        agent_id=str(agent_id),
        environment_id=str(environment_id),
        agent_version=str(agent_version) if agent_version else None,
        token=token,
        profile=profile,
        config_path=config_path,
        managed_agents=managed_agents,
    )


def _discover_qoder_config(project_root: Path, project: dict[str, Any]) -> tuple[Path | None, str]:
    qoder = project.get("qoder") if isinstance(project.get("qoder"), dict) else {}
    profile = str(qoder.get("profile") or "default")
    configured_path = str(qoder.get("config") or "").strip()
    if configured_path:
        path = Path(configured_path).expanduser()
        return (path if path.is_absolute() else project_root / path), profile

    registry = _read_registry()
    registry_config = str((registry or {}).get("config_path") or "").strip()
    if registry_config:
        return Path(registry_config).expanduser(), profile or str((registry or {}).get("profile") or "default")

    discovery = discover_qoder_runner(project_root, project, check_help=False)
    config_path_value = discovery.get("config_path")
    config_path = Path(config_path_value).expanduser() if config_path_value else None
    return config_path, str(discovery.get("profile") or profile or "default")


def _read_registry() -> dict[str, Any] | None:
    path = default_registry_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def ensure_managed_agent_set(
    project_root: Path,
    project: dict[str, Any],
    task: dict[str, Any],
    client: QoderCloudClient,
    config: QoderCloudConfig,
) -> dict[str, Any]:
    settings = _managed_agent_settings(project, task, config)
    if not settings.enabled:
        return {
            "enabled": False,
            "active": False,
            "mode": settings.mode,
            "total_agents": settings.total_agents,
            "agent_count": settings.total_agents,
            "delegation_strategy": settings.delegation_strategy,
            "include_self": settings.include_self,
            "schema_ok": True,
            "message": "managed agents disabled for this task",
        }

    state_path = _managed_agent_state_path(project_root)
    state = _read_managed_agent_state(project_root)
    try:
        settings = _resolve_managed_agent_model(client, settings)
    except Exception as exc:
        if settings.require_managed_agents or isinstance(exc, QoderManagedAgentModelError):
            raise
        return {
            "enabled": True,
            "active": False,
            "fallback": "single_agent",
            "mode": settings.mode,
            "total_agents": settings.total_agents,
            "agent_count": settings.total_agents,
            "delegation_strategy": settings.delegation_strategy,
            "include_self": settings.include_self,
            "schema_ok": True,
            "requested_model": settings.requested_model,
            "resolved_model": None,
            "state_path": str(state_path),
            "error": str(exc),
            "message": "managed agents unavailable; falling back to single configured agent",
        }

    desired = _desired_agent_set(project, task, settings)
    if _state_matches(state, settings, desired):
        runtime = _runtime_from_state(state, state_path, reused=True)
        runtime["message"] = "managed agents reused from local state"
        return runtime

    try:
        workers: list[dict[str, Any]] = []
        state_workers = {
            str(worker.get("role")): worker
            for worker in state.get("workers", [])
            if isinstance(worker, dict)
        }
        for worker_spec in desired["workers"]:
            previous = state_workers.get(worker_spec["role"])
            agent = _ensure_agent(client, worker_spec, previous, settings, desired["config_hash"])
            workers.append(_agent_summary(agent, role=worker_spec["role"]))

        coordinator_spec = _coordinator_spec(desired, workers)
        previous_coordinator = state.get("coordinator") if isinstance(state.get("coordinator"), dict) else None
        coordinator = _ensure_agent(client, coordinator_spec, previous_coordinator, settings, desired["config_hash"])

        new_state = {
            "schema_version": 6,
            "profile": config.profile,
            "agent_set_name": settings.agent_set_name,
            "agent_set_id": settings.agent_set_id,
            "mode": settings.mode,
            "model": settings.model,
            "requested_model": settings.requested_model,
            "resolved_model": settings.model,
            "model_source": settings.model_source,
            "available_models": list(settings.available_models),
            "total_agents": settings.total_agents,
            "agent_count": settings.total_agents,
            "delegation_strategy": settings.delegation_strategy,
            "include_self": settings.include_self,
            "config_hash": desired["config_hash"],
            "coordinator": _agent_summary(coordinator, role="coordinator"),
            "workers": workers,
            "multiagent": coordinator_spec["multiagent"],
            "schema_ok": _multiagent_schema_ok(coordinator_spec["multiagent"], workers),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        _write_managed_agent_state(project_root, new_state)
        runtime = _runtime_from_state(new_state, state_path, reused=False)
        runtime["message"] = "managed agents created or updated"
        return runtime
    except Exception as exc:
        if settings.require_managed_agents:
            raise
        return {
            "enabled": True,
            "active": False,
            "fallback": "single_agent",
            "mode": settings.mode,
            "total_agents": settings.total_agents,
            "agent_count": settings.total_agents,
            "delegation_strategy": settings.delegation_strategy,
            "include_self": settings.include_self,
            "schema_ok": True,
            "requested_model": settings.requested_model,
            "resolved_model": settings.model,
            "model_source": settings.model_source,
            "available_models": list(settings.available_models),
            "state_path": str(state_path),
            "error": str(exc),
            "message": "managed agents unavailable; falling back to single configured agent",
        }


def qoder_models_status(project_root: Path, project: dict[str, Any]) -> dict[str, Any]:
    try:
        config = resolve_qoder_cloud_config(project_root, project, task={})
        models = _model_summaries_from_response(QoderCloudClient(config, request_timeout=15).list_models())
    except Exception as exc:
        return {
            "ok": False,
            "available_models": [],
            "ids": [],
            "message": f"models unavailable: {exc}",
        }
    ids = _model_ids(models)
    if not ids:
        return {
            "ok": False,
            "available_models": models,
            "ids": [],
            "message": "no enabled Qoder models returned for this account",
        }
    return {
        "ok": True,
        "available_models": models,
        "ids": ids,
        "message": f"available models: {', '.join(ids)}",
    }


def managed_agents_status(
    project_root: Path,
    project: dict[str, Any],
    models_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    qoder_project = project.get("qoder", {}) if isinstance(project.get("qoder"), dict) else {}
    raw = qoder_project.get("managed_agents") if isinstance(qoder_project.get("managed_agents"), dict) else {}
    enabled = _bool_value(raw.get("enabled"), True)
    total_agents = _clamp_total_agents(raw.get("total_agents", 4))
    delegation_strategy = _delegation_strategy(raw.get("delegation_strategy"))
    include_self = _bool_value(raw.get("include_self"), False)
    requested_model = _configured_model(raw)
    state_path = _managed_agent_state_path(project_root)
    state = _read_managed_agent_state(project_root)
    active_state = bool(state.get("coordinator") and state.get("workers"))
    workers = state.get("workers") if isinstance(state.get("workers"), list) else []
    schema_ok = True if not active_state else _multiagent_schema_ok(state.get("multiagent"), workers)
    agent_count = int(state.get("agent_count") or (1 + len(workers) if active_state else total_agents))
    model_status = models_status or {"ok": False, "available_models": [], "ids": [], "message": "models not checked"}
    model_resolution = _resolve_model_from_status(requested_model, model_status)
    if not enabled:
        message = "深度搜索多 Agent 未启用"
    elif not model_resolution["ok"]:
        message = f"深度搜索多 Agent 模型不可用: {model_resolution['message']}"
    elif active_state and not schema_ok:
        message = "深度搜索多 Agent schema 错误: 将在下次运行时自动更新 coordinator roster"
    elif active_state:
        message = (
            f"深度搜索多 Agent schema OK: {agent_count} agents, "
            f"model {model_resolution['resolved_model']}"
        )
    else:
        message = f"深度搜索多 Agent 待创建: {total_agents} agents, model {model_resolution['resolved_model']}"
    return {
        "enabled": enabled,
        "ready": active_state,
        "model_ok": bool(model_resolution["ok"]),
        "schema_ok": schema_ok,
        "requested_model": requested_model,
        "resolved_model": model_resolution.get("resolved_model"),
        "model_source": model_resolution.get("model_source"),
        "available_models": model_status.get("available_models", []),
        "total_agents": total_agents,
        "agent_count": agent_count,
        "delegation_strategy": state.get("delegation_strategy") or delegation_strategy,
        "include_self": bool(state.get("include_self")) if active_state else include_self,
        "state_path": str(state_path),
        "message": message,
    }


def _merged_managed_agent_config(
    profile_config: dict[str, Any],
    qoder_project: dict[str, Any],
    task: dict[str, Any] | None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for source in [
        profile_config.get("managed_agents") if isinstance(profile_config.get("managed_agents"), dict) else {},
        qoder_project.get("managed_agents") if isinstance(qoder_project.get("managed_agents"), dict) else {},
    ]:
        merged.update(source)
    if task:
        coordinator = task.get("coordinator") if isinstance(task.get("coordinator"), dict) else {}
        for source in [
            coordinator.get("managed_agents") if isinstance(coordinator.get("managed_agents"), dict) else {},
            task.get("managed_agents") if isinstance(task.get("managed_agents"), dict) else {},
        ]:
            merged.update(source)
    return merged


def _resolve_managed_agent_model(
    client: QoderCloudClient,
    settings: ManagedAgentSettings,
) -> ManagedAgentSettings:
    models = _model_summaries_from_response(client.list_models())
    model_status = {
        "ok": bool(_model_ids(models)),
        "available_models": models,
        "ids": _model_ids(models),
    }
    resolution = _resolve_model_from_status(settings.requested_model, model_status)
    if not resolution["ok"]:
        error = str(resolution["message"])
        if settings.requested_model:
            raise QoderManagedAgentModelError(error)
        raise QoderCloudError(error)
    return replace(
        settings,
        model=str(resolution["resolved_model"]),
        model_source=str(resolution["model_source"]),
        available_models=tuple(models),
    )


def _resolve_model_from_status(requested_model: str | None, model_status: dict[str, Any]) -> dict[str, Any]:
    ids = [str(model_id) for model_id in model_status.get("ids", []) if str(model_id)]
    if not model_status.get("ok") or not ids:
        return {
            "ok": False,
            "resolved_model": None,
            "model_source": "unavailable",
            "message": model_status.get("message") or "no enabled Qoder models are available",
        }
    if requested_model:
        if requested_model in ids:
            return {
                "ok": True,
                "resolved_model": requested_model,
                "model_source": "configured",
                "message": f"configured model available: {requested_model}",
            }
        return {
            "ok": False,
            "resolved_model": None,
            "model_source": "configured_missing",
            "message": (
                f"configured Qoder managed-agent model '{requested_model}' is not available; "
                f"available models: {', '.join(ids)}"
            ),
        }
    for preferred in ["ultimate", "qmodel_latest", "qmodel"]:
        if preferred in ids:
            return {
                "ok": True,
                "resolved_model": preferred,
                "model_source": "auto_preferred",
                "message": f"auto-selected preferred model: {preferred}",
            }
    concrete_ids = [model_id for model_id in ids if model_id != "auto"]
    if concrete_ids:
        return {
            "ok": True,
            "resolved_model": concrete_ids[0],
            "model_source": "auto_first_concrete",
            "message": f"auto-selected first concrete model: {concrete_ids[0]}",
        }
    return {
        "ok": True,
        "resolved_model": ids[0],
        "model_source": "auto_first_available",
        "message": f"auto-selected first available model: {ids[0]}",
    }


def _model_summaries_from_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    raw_models = response.get("data")
    if not isinstance(raw_models, list):
        raw_models = response.get("value") if isinstance(response.get("value"), list) else []
    models: list[dict[str, Any]] = []
    for item in raw_models:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        if not model_id:
            continue
        if item.get("is_enabled") is False:
            continue
        models.append(
            {
                "id": model_id,
                "display_name": str(item.get("display_name") or model_id),
                "is_enabled": item.get("is_enabled", True),
            }
        )
    return models


def _model_ids(models: list[dict[str, Any]]) -> list[str]:
    return [str(model.get("id")) for model in models if model.get("id")]


def _configured_model(raw: dict[str, Any]) -> str | None:
    value = raw.get("model")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _managed_agent_settings(project: dict[str, Any], task: dict[str, Any], config: QoderCloudConfig) -> ManagedAgentSettings:
    raw = dict(config.managed_agents or {})
    default_enabled = task.get("type") in {"cloud_experiment", "deep_search"} or task.get("mode") == "full_cloud"
    project_id = str(project.get("project_id") or project.get("id") or "academic-project")
    profile = _safe_slug(config.profile or "default")
    agent_set_name = _safe_slug(str(raw.get("agent_set_name") or "deep_search"))
    requested_model = _configured_model(raw)
    delegation_strategy = _delegation_strategy(raw.get("delegation_strategy"))
    return ManagedAgentSettings(
        enabled=_bool_value(raw.get("enabled"), default_enabled),
        require_managed_agents=_bool_value(raw.get("require_managed_agents"), False),
        total_agents=_clamp_total_agents(raw.get("total_agents", 4)),
        model=requested_model or "auto",
        requested_model=requested_model,
        model_source="configured" if requested_model else "auto",
        available_models=(),
        mode=str(raw.get("mode") or "persistent"),
        agent_set_name=agent_set_name,
        agent_set_id=f"academic-harness:{_safe_slug(project_id)}:{profile}:{agent_set_name}:v1",
        delegation_strategy=delegation_strategy,
        include_self=_bool_value(raw.get("include_self"), False),
    )


def _desired_agent_set(project: dict[str, Any], task: dict[str, Any], settings: ManagedAgentSettings) -> dict[str, Any]:
    project_id = str(project.get("project_id") or project.get("id") or "academic-project")
    title = str(project.get("title") or project_id)
    workers = [_worker_spec(project_id, title, settings, role) for role in _worker_roles(settings.total_agents)]
    desired = {
        "agent_set_id": settings.agent_set_id,
        "agent_set_name": settings.agent_set_name,
        "model": settings.model,
        "requested_model": settings.requested_model,
        "model_source": settings.model_source,
        "available_models": list(settings.available_models),
        "total_agents": settings.total_agents,
        "delegation_strategy": settings.delegation_strategy,
        "include_self": settings.include_self,
        "multiagent_schema_version": 6,
        "project_id": project_id,
        "task_type": task.get("type"),
        "workers": workers,
    }
    desired["config_hash"] = _stable_hash(desired)
    return desired


def _worker_roles(total_agents: int) -> list[str]:
    if total_agents <= 3:
        return ["evidence_searcher", "report_writer_reviewer"]
    if total_agents >= 5:
        return ["evidence_searcher", "method_synthesizer", "report_writer_reviewer", "critic_validator"]
    return ["evidence_searcher", "method_synthesizer", "report_writer_reviewer"]


def _worker_spec(project_id: str, title: str, settings: ManagedAgentSettings, role: str) -> dict[str, Any]:
    role_info = ROLE_LIBRARY[role]
    label = role_info["label"]
    return {
        "role": role,
        "name": _agent_name(project_id, label),
        "model": settings.model,
        "description": f"Academic Harness {label} for {title}",
        "system": role_info["system"],
        "tools": [WORKER_TOOLSET],
        "metadata": _agent_metadata(settings, role),
    }


def _coordinator_spec(desired: dict[str, Any], workers: list[dict[str, Any]]) -> dict[str, Any]:
    project_id = str(desired["project_id"])
    worker_lines = "\n".join(
        f"- {worker['role']}: {worker.get('name') or worker.get('id')}" for worker in workers
    )
    multiagent_config = _build_multiagent_config(workers, include_self=bool(desired.get("include_self")))
    delegation_strategy = _delegation_strategy(desired.get("delegation_strategy"))
    return {
        "role": "coordinator",
        "name": _agent_name(project_id, "Deep Search Coordinator"),
        "model": desired["model"],
        "description": "Academic Harness deep search coordinator that delegates evidence, synthesis, writing, and review.",
        "system": _coordinator_system_prompt(worker_lines, delegation_strategy),
        "tools": [COORDINATOR_TOOLSET],
        "metadata": {
            **_agent_metadata(
                ManagedAgentSettings(
                    enabled=True,
                    require_managed_agents=False,
                    total_agents=int(desired["total_agents"]),
                    model=str(desired["model"]),
                    requested_model=desired.get("requested_model"),
                    model_source=str(desired.get("model_source") or "auto"),
                    available_models=tuple(desired.get("available_models") or ()),
                    mode="persistent",
                    agent_set_name=str(desired["agent_set_name"]),
                    agent_set_id=str(desired["agent_set_id"]),
                    delegation_strategy=delegation_strategy,
                    include_self=bool(desired.get("include_self")),
                ),
                "coordinator",
            ),
            "worker_count": str(len(workers)),
            "delegation_strategy": delegation_strategy,
        },
        "multiagent": multiagent_config.to_payload(),
    }


def _coordinator_system_prompt(worker_lines: str, delegation_strategy: str) -> str:
    if delegation_strategy == "child_threads":
        delegation = (
            "Use the injected create_agent tool to create one child thread per worker role, then use list_agents "
            "only to monitor child thread status and send_to_agent only when a follow-up is required. Wait for "
            "worker results from send_to_parent before synthesis."
        )
    else:
        delegation = (
            "Before any WebSearch, WebFetch, Write, or final synthesis, delegate every worker role. First use "
            "the injected tool named exactly Agent once for each worker role and wait for each worker to return "
            "via send_to_parent. If the Agent tool is not available in your actual tool list, immediately fall "
            "back to create_agent for every worker role, then call list_agents until each worker has returned via "
            "send_to_parent. Do not end the turn after dispatching workers. It is a contract violation to research "
            "or write by yourself before delegation."
        )
    return (
        "You are the Academic Harness deep search coordinator. For each run, delegate evidence search, method "
        "synthesis, writing, and review to the configured worker roster, then synthesize one final report. "
        f"{delegation} Give each worker a bounded one-response task: ask for 8-12 high-signal findings or compact "
        "sections, explicitly require best-effort partial results via send_to_parent, and do not ask for exhaustive "
        "open-ended research. Always write the main document with the Write tool as report.md, deliver artifacts "
        "with DeliverArtifacts when available, and keep the final assistant message concise.\n\n"
        f"Available worker roles:\n{worker_lines}\n"
    )


def _build_multiagent_config(workers: list[dict[str, Any]], include_self: bool = False) -> MultiagentConfig:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for worker in workers:
        agent_id = str(worker.get("id") or "").strip()
        if not agent_id:
            raise QoderCloudError("managed agent worker is missing id")
        if agent_id in seen:
            raise QoderCloudError(f"duplicate managed agent id in multiagent roster: {agent_id}")
        seen.add(agent_id)
        try:
            version = int(worker["version"])
        except (KeyError, TypeError, ValueError) as exc:
            raise QoderCloudError(f"managed agent worker {agent_id} is missing a positive integer version") from exc
        if version <= 0:
            raise QoderCloudError(f"managed agent worker {agent_id} has invalid version: {version}")
        entries.append(
            {
                "type": "agent",
                "id": agent_id,
                "version": version,
                "name": str(worker.get("name") or worker.get("role") or agent_id),
            }
        )
    config = MultiagentConfig(agents=tuple(entries), include_self=include_self)
    _validate_multiagent_payload(config.to_payload())
    return config


def _validate_multiagent_payload(payload: dict[str, Any]) -> None:
    if payload.get("type") != "coordinator":
        raise QoderCloudError("multiagent.type must be coordinator")
    agents = payload.get("agents")
    if not isinstance(agents, list) or not 1 <= len(agents) <= 20:
        raise QoderCloudError("multiagent.agents must contain 1-20 entries")
    seen: set[str] = set()
    for entry in agents:
        if not isinstance(entry, dict):
            raise QoderCloudError("multiagent agent entries must use object format")
        entry_type = entry.get("type")
        if entry_type == "self":
            key = "self"
        elif entry_type == "agent":
            agent_id = str(entry.get("id") or "")
            if not agent_id:
                raise QoderCloudError("multiagent agent entry missing id")
            version = entry.get("version")
            if version is not None and (not isinstance(version, int) or version <= 0):
                raise QoderCloudError(f"multiagent agent entry has invalid version for {agent_id}")
            key = agent_id
        else:
            raise QoderCloudError(f"unsupported multiagent agent entry type: {entry_type}")
        if key in seen:
            raise QoderCloudError(f"duplicate multiagent agent entry: {key}")
        seen.add(key)


def _agent_metadata(settings: ManagedAgentSettings, role: str) -> dict[str, str]:
    return {
        "managed_by": "academic-harness",
        "schema_version": "6",
        "agent_set_id": settings.agent_set_id,
        "agent_set_name": settings.agent_set_name,
        "role": role,
        "delegation_strategy": settings.delegation_strategy,
        "include_self": str(settings.include_self).lower(),
    }


def _ensure_agent(
    client: QoderCloudClient,
    spec: dict[str, Any],
    previous: dict[str, Any] | None,
    settings: ManagedAgentSettings,
    config_hash: str,
) -> dict[str, Any]:
    payload = {key: value for key, value in spec.items() if key not in {"role"}}
    metadata = dict(payload.get("metadata") or {})
    metadata["config_hash"] = config_hash
    payload["metadata"] = metadata
    _validate_agent_payload_for_qoder_runtime(payload)
    if previous and previous.get("id"):
        agent_id = str(previous["id"])
        current = client.get_agent(agent_id)
        try:
            return client.update_agent(agent_id, int(current["version"]), payload)
        except QoderCloudHTTPError as exc:
            if exc.status_code != 409:
                raise
            current = client.get_agent(agent_id)
            return client.update_agent(agent_id, int(current["version"]), payload)
    key = _stable_hash({"agent_set": settings.agent_set_id, "role": spec["role"], "config": config_hash})
    return client.create_agent(payload, idempotency_key=f"academic-harness-{key}")


def _validate_agent_payload_for_qoder_runtime(payload: dict[str, Any]) -> None:
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "agent_toolset_20260401":
            continue
        enabled_tools = tool.get("enabled_tools") or []
        if not isinstance(enabled_tools, list):
            continue
        forbidden = sorted(QODER_RUNTIME_COORDINATOR_TOOLS.intersection({str(name) for name in enabled_tools}))
        if forbidden:
            raise QoderCloudError(
                "Qoder runtime-injected coordinator tools must not be listed in enabled_tools: "
                + ", ".join(forbidden)
            )
    if "multiagent" in payload:
        _validate_multiagent_payload(payload["multiagent"])


def _state_matches(state: dict[str, Any], settings: ManagedAgentSettings, desired: dict[str, Any]) -> bool:
    if not state:
        return False
    if state.get("agent_set_id") != settings.agent_set_id:
        return False
    if state.get("config_hash") != desired.get("config_hash"):
        return False
    workers = state.get("workers")
    if not _multiagent_schema_ok(state.get("multiagent"), workers):
        return False
    return bool(
        isinstance(state.get("coordinator"), dict)
        and isinstance(workers, list)
        and len(workers) == settings.total_agents - 1
        and all(isinstance(worker, dict) and worker.get("id") and worker.get("version") for worker in workers)
    )


def _multiagent_schema_ok(multiagent: Any, workers: list[dict[str, Any]] | Any) -> bool:
    if not isinstance(multiagent, dict):
        return False
    if not isinstance(workers, list):
        return False
    try:
        _validate_multiagent_payload(multiagent)
    except QoderCloudError:
        return False
    agent_entries = [entry for entry in multiagent.get("agents", []) if isinstance(entry, dict) and entry.get("type") == "agent"]
    worker_ids = {str(worker.get("id")) for worker in workers if isinstance(worker, dict) and worker.get("id")}
    entry_ids = {str(entry.get("id")) for entry in agent_entries if entry.get("id")}
    return bool(worker_ids) and worker_ids == entry_ids


def _runtime_from_state(state: dict[str, Any], state_path: Path, reused: bool) -> dict[str, Any]:
    workers = state.get("workers", [])
    agent_count = int(state.get("agent_count") or (1 + len(workers) if isinstance(workers, list) else 1))
    schema_ok = bool(state.get("schema_ok"))
    if not schema_ok:
        schema_ok = _multiagent_schema_ok(state.get("multiagent"), workers)
    return {
        "enabled": True,
        "active": bool(state.get("coordinator")),
        "mode": state.get("mode") or "persistent",
        "reused": reused,
        "agent_set_name": state.get("agent_set_name"),
        "agent_set_id": state.get("agent_set_id"),
        "total_agents": state.get("total_agents"),
        "model": state.get("model"),
        "requested_model": state.get("requested_model"),
        "resolved_model": state.get("resolved_model") or state.get("model"),
        "model_source": state.get("model_source"),
        "available_models": state.get("available_models", []),
        "agent_count": agent_count,
        "delegation_strategy": state.get("delegation_strategy") or "agent_sync",
        "include_self": bool(state.get("include_self")),
        "schema_ok": schema_ok,
        "multiagent": state.get("multiagent"),
        "state_path": str(state_path),
        "coordinator": state.get("coordinator"),
        "workers": workers if isinstance(workers, list) else [],
    }


def _agent_summary(agent: dict[str, Any], role: str) -> dict[str, Any]:
    return {
        "role": role,
        "id": agent.get("id"),
        "version": agent.get("version"),
        "name": agent.get("name"),
        "model": agent.get("model"),
    }


def _managed_agent_state_path(project_root: Path) -> Path:
    return project_root / WORKBENCH_DIR / "qoder_agents.json"


def _read_managed_agent_state(project_root: Path) -> dict[str, Any]:
    path = _managed_agent_state_path(project_root)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_managed_agent_state(project_root: Path, state: dict[str, Any]) -> None:
    path = _managed_agent_state_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _clamp_total_agents(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 4
    return max(3, min(5, parsed))


def _bool_value(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _delegation_strategy(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"child_threads", "thread", "threads", "create_agent"}:
        return "child_threads"
    return "agent_sync"


def _agent_name(project_id: str, label: str) -> str:
    base = f"AH {project_id} {label}"
    return base[:256]


def _safe_slug(value: str) -> str:
    lowered = value.strip().lower()
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in lowered)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "default"


def _stable_hash(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _build_cloud_prompt(
    project_root: Path,
    project: dict[str, Any],
    task: dict[str, Any],
    run_id: str,
    managed_agents: dict[str, Any] | None = None,
) -> str:
    prompt = prompt_text_for_task(project_root, task)
    if not prompt:
        raise QoderCloudError("cloud task requires input.prompt_file or plan.objective")
    cloud_context = {
        "run_id": run_id,
        "task_id": task.get("task_id"),
        "task_type": task.get("type"),
        "mode": task.get("mode") or "full_cloud",
        "expected_artifacts": task.get("expected_artifacts", []),
        "validators": task.get("validators", []),
        "policy": task.get("policy", {}),
        "coordinator": task.get("coordinator", {}),
        "managed_agents": _prompt_managed_agent_context(managed_agents),
        "project": {
            "id": project.get("project_id") or project.get("project", {}).get("id") or project.get("id"),
            "title": project.get("title") or project.get("project", {}).get("title"),
        },
    }
    managed_instruction = ""
    if managed_agents and managed_agents.get("active"):
        workers = managed_agents.get("workers") if isinstance(managed_agents.get("workers"), list) else []
        worker_lines = "\n".join(
            f"- {worker.get('role')}: {worker.get('name') or worker.get('id')}" for worker in workers if isinstance(worker, dict)
        )
        delegation_strategy = _delegation_strategy(managed_agents.get("delegation_strategy"))
        if delegation_strategy == "child_threads":
            delegation = (
                "Use create_agent to create one child thread per worker role, monitor with list_agents, and wait "
                "for send_to_parent results before synthesis."
            )
        else:
            delegation = (
                "Before any WebSearch, WebFetch, Write, or final synthesis, delegate every worker role. First "
                "use the injected tool named exactly Agent once for each worker role and wait for each worker "
                "to return via send_to_parent. If the Agent tool is not available in your actual tool list, "
                "immediately fall back to create_agent for every worker role, then call list_agents until each "
                "worker has returned via send_to_parent. Do not end the turn after dispatching workers. It is a "
                "contract violation to research or write by yourself before delegation."
            )
        managed_instruction = (
            "Managed child agents are configured for this run using Qoder multiagent schema. "
            f"Delegation strategy: {delegation_strategy}. {delegation} Delegate bounded one-response tasks only: "
            "ask each worker for compact best-effort partial results via send_to_parent, not exhaustive open-ended research.\n"
            f"Worker roster:\n{worker_lines}\n"
        )
    elif managed_agents and managed_agents.get("fallback"):
        managed_instruction = (
            "Managed child agents were requested but could not be prepared. Continue as a single agent and explicitly note the fallback.\n"
        )
    instructions = (
        "You are the Qoder Cloud coordinator for an academic research harness run.\n"
        "Run the work in cloud. Decompose the work, collect evidence, synthesize results, and deliver artifacts.\n"
        f"{managed_instruction}"
        "Produce the primary document via a Write tool call when possible so the harness can save report.md. "
        "Use the final assistant message only as a concise summary.\n"
        "Preserve citations, assumptions, methods, limitations, and artifact filenames.\n"
    )
    return (
        f"{instructions}\n"
        "Harness context JSON:\n"
        f"{json.dumps(cloud_context, ensure_ascii=False, indent=2)}\n\n"
        "User task:\n"
        f"{prompt.strip()}\n"
    )


def _prompt_managed_agent_context(managed_agents: dict[str, Any] | None) -> dict[str, Any]:
    if not managed_agents:
        return {"enabled": False, "active": False}
    return {
        "enabled": bool(managed_agents.get("enabled")),
        "active": bool(managed_agents.get("active")),
        "fallback": managed_agents.get("fallback"),
        "error": managed_agents.get("error"),
        "agent_set_name": managed_agents.get("agent_set_name"),
        "total_agents": managed_agents.get("total_agents"),
        "agent_count": managed_agents.get("agent_count"),
        "delegation_strategy": managed_agents.get("delegation_strategy"),
        "include_self": managed_agents.get("include_self"),
        "schema_ok": managed_agents.get("schema_ok"),
        "coordinator": managed_agents.get("coordinator"),
        "workers": managed_agents.get("workers", []),
        "multiagent": managed_agents.get("multiagent"),
    }


def _string_metadata(values: dict[str, Any]) -> dict[str, str]:
    return {key: str(value) for key, value in values.items() if value is not None}


def _ensure_raw_event_files(qoder_dir: Path) -> None:
    if not (qoder_dir / "events.sse").exists():
        (qoder_dir / "events.sse").write_text("", encoding="utf-8")
    if not (qoder_dir / "events.jsonl").exists():
        (qoder_dir / "events.jsonl").write_text("", encoding="utf-8")


def _empty_stream_summary(errors: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "writes": [],
        "delivered": [],
        "summary_path": None,
        "report_path": None,
        "thread_events": [],
        "errors": errors or [],
        "idle_seen": False,
    }


def _stream_error_reason(errors: list[dict[str, Any]]) -> str:
    for error in errors:
        message = error.get("message") if isinstance(error, dict) else None
        if isinstance(message, str) and message.strip():
            return message.strip()
    return "Qoder stream emitted an error event"


def _stream_and_extract(client: QoderCloudClient, session_id: str, qoder_dir: Path, run_id: str) -> dict[str, Any]:
    sse_path = qoder_dir / "events.sse"
    jsonl_path = qoder_dir / "events.jsonl"
    artifacts_dir = qoder_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    extractor = _EventExtractor(qoder_dir, artifacts_dir)
    current_event = "message"
    current_id = None
    idle_seen = False
    with client.stream_events(session_id) as response:
        with sse_path.open("w", encoding="utf-8") as sse_file, jsonl_path.open("w", encoding="utf-8") as jsonl_file:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                sse_file.write(line + "\n")
                sse_file.flush()
                if not line:
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    current_event = line.split(":", 1)[1].strip() or "message"
                    continue
                if line.startswith("id:"):
                    current_id = line.split(":", 1)[1].strip() or None
                    continue
                if not line.startswith("data:"):
                    continue
                data = line.split(":", 1)[1].lstrip()
                record = _decode_sse_data(current_event, current_id, data)
                jsonl_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                jsonl_file.flush()
                extractor.consume(record)
                if extractor.is_terminal_error(record):
                    break
                if extractor.is_idle(record):
                    idle_seen = True
                    break
    extractor.write_outputs()
    summary = extractor.summary()
    summary["thread_trace"] = write_qoder_thread_trace(run_id, qoder_dir, summary.get("thread_events", []))
    summary["idle_seen"] = idle_seen
    return summary


class _EventExtractor:
    def __init__(self, qoder_dir: Path, artifacts_dir: Path) -> None:
        self.qoder_dir = qoder_dir
        self.artifacts_dir = artifacts_dir
        self.last_agent_message = ""
        self.last_write_content = ""
        self.primary_write_content = ""
        self.writes: list[dict[str, Any]] = []
        self.delivered: list[dict[str, Any]] = []
        self.thread_events: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []

    def consume(self, record: dict[str, Any]) -> None:
        payload = record.get("data")
        if not isinstance(payload, dict):
            return
        event_type = _event_type(record, payload)
        if event_type == "agent.message":
            text = _extract_text(payload)
            if text:
                self.last_agent_message = text
            return
        if event_type == "session.error":
            self.errors.append(_error_event_record(event_type, payload, record))
            return
        if event_type in {"agent.thread_message_received", "agent.thread_message_sent"}:
            self.thread_events.append(_thread_event_record(event_type, payload, record))
            error_message = _thread_error_message(payload)
            if error_message:
                self.errors.append(_error_event_record(event_type, payload, record, message=error_message))
            return
        if event_type == "agent.tool_use":
            self._consume_tool_use(payload)
            return
        if event_type in {"agent.artifact_delivered", "artifact_delivered"}:
            delivered = _artifact_delivered_record(payload)
            if delivered:
                self.delivered.append(delivered)
            return
        if event_type.startswith("session.thread_") or event_type.startswith("agent.thread_"):
            self.thread_events.append(_thread_event_record(event_type, payload, record))

    def _consume_tool_use(self, payload: dict[str, Any]) -> None:
        tool_payload = payload.get("tool_use") if isinstance(payload.get("tool_use"), dict) else payload
        name = tool_payload.get("name") or tool_payload.get("tool_name")
        if name != "Write":
            return
        input_data = tool_payload.get("input")
        if isinstance(input_data, str):
            try:
                input_data = json.loads(input_data)
            except json.JSONDecodeError:
                input_data = {}
        if not isinstance(input_data, dict):
            return
        content = input_data.get("content")
        if not isinstance(content, str) or not content:
            return
        source_path = str(input_data.get("file_path") or input_data.get("path") or "artifact.md")
        output_name = _unique_artifact_name(self.artifacts_dir, Path(source_path).name or "artifact.md")
        artifact_path = self.artifacts_dir / output_name
        artifact_path.write_text(content, encoding="utf-8")
        self.last_write_content = content
        if _is_primary_report_name(source_path) or _is_primary_report_name(output_name):
            self.primary_write_content = content
        elif not self.primary_write_content and not _is_secondary_artifact_name(output_name):
            self.primary_write_content = content
        self.writes.append(
            {
                "source_path": source_path,
                "local_path": str(artifact_path.resolve()),
                "filename": output_name,
                "size": len(content.encode("utf-8")),
                "content_type": _content_type_for(output_name),
            }
        )

    def is_idle(self, record: dict[str, Any]) -> bool:
        payload = record.get("data")
        event_type = _event_type(record, payload if isinstance(payload, dict) else {})
        return event_type == "session.status_idle"

    def is_terminal_error(self, record: dict[str, Any]) -> bool:
        payload = record.get("data")
        event_type = _event_type(record, payload if isinstance(payload, dict) else {})
        return event_type == "session.error"

    def write_outputs(self) -> None:
        fallback_message = None if _is_non_report_agent_message(self.last_agent_message) else self.last_agent_message
        report_content = self.primary_write_content or self.last_write_content or fallback_message
        if report_content:
            (self.qoder_dir / "report.md").write_text(report_content, encoding="utf-8")
        if self.last_agent_message:
            (self.qoder_dir / "summary.md").write_text(self.last_agent_message, encoding="utf-8")

    def summary(self) -> dict[str, Any]:
        return {
            "writes": self.writes,
            "delivered": self.delivered,
            "thread_events": self.thread_events,
            "errors": self.errors,
            "report_path": str((self.qoder_dir / "report.md").resolve()) if (self.qoder_dir / "report.md").exists() else None,
            "summary_path": str((self.qoder_dir / "summary.md").resolve()) if (self.qoder_dir / "summary.md").exists() else None,
        }


def _decode_sse_data(event_name: str, event_id: str | None, data: str) -> dict[str, Any]:
    try:
        decoded: Any = json.loads(data)
    except json.JSONDecodeError:
        decoded = data
    return {"sse_event": event_name, "id": event_id, "data": decoded}


def _event_type(record: dict[str, Any], payload: dict[str, Any]) -> str:
    candidates = [
        payload.get("type"),
        payload.get("event"),
        payload.get("name") if str(payload.get("name", "")).startswith(("agent.", "session.")) else None,
        record.get("sse_event"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate:
            return candidate
    return ""


def _extract_text(payload: dict[str, Any]) -> str:
    content = payload.get("content") or payload.get("message") or payload.get("text")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces = []
        for part in content:
            if isinstance(part, str):
                pieces.append(part)
            elif isinstance(part, dict):
                text = part.get("text") or part.get("content")
                if isinstance(text, str):
                    pieces.append(text)
        return "\n".join(piece for piece in pieces if piece).strip()
    if isinstance(content, dict):
        text = content.get("text") or content.get("content")
        if isinstance(text, str):
            return text
    return ""


def _error_event_record(
    event_type: str,
    payload: dict[str, Any],
    record: dict[str, Any],
    message: str | None = None,
) -> dict[str, Any]:
    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    text = message or error.get("message") or payload.get("message") or payload.get("text") or _extract_text(payload)
    event: dict[str, Any] = {
        "type": event_type,
        "message": str(text or event_type),
    }
    if record.get("id") is not None:
        event["id"] = record["id"]
    if isinstance(error, dict):
        for key in ("type", "code", "retry_status"):
            if key in error:
                event[f"error_{key}"] = error[key]
    for key in ("from_agent_name", "from_session_thread_id", "session_thread_id", "processed_at"):
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            event[key] = value
    return event


def _thread_error_message(payload: dict[str, Any]) -> str | None:
    text = _extract_text(payload).strip()
    if not text:
        return None
    lowered = text.lower()
    markers = [
        "model provider error",
        "billing daily count exceeded",
        "forbidden",
        "unknown_error",
        "retry_status",
    ]
    if any(marker in lowered for marker in markers):
        return text
    return None


def _artifact_delivered_record(payload: dict[str, Any]) -> dict[str, Any]:
    artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else payload
    keys = ["file_id", "original_filename", "content_type", "size", "name", "path"]
    return {key: artifact.get(key) for key in keys if artifact.get(key) is not None}


def _thread_event_record(event_type: str, payload: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    event: dict[str, Any] = {"type": event_type}
    if record.get("id") is not None:
        event["id"] = record["id"]
    excluded = {"content", "message", "text", "input", "output"}
    for key, value in payload.items():
        if key in excluded:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            event[key] = value
    text = _extract_text(payload)
    if text:
        event["text_excerpt"] = text[:2000]
    return event


def _is_primary_report_name(value: str) -> bool:
    name = Path(value).name.lower()
    return name in {"report.md", "research_report.md", "final_report.md"} or (
        "report" in name and "summary" not in name and "readme" not in name
    )


def _is_secondary_artifact_name(value: str) -> bool:
    name = Path(value).name.lower()
    return name in {"summary.md", "readme.md", "index.md"} or "summary" in name or "readme" in name or "index" in name


def _is_non_report_agent_message(value: str) -> bool:
    text = value.strip().lower()
    if not text:
        return True
    waiting_markers = [
        "waiting for results",
        "waiting for all workers",
        "waiting for all worker",
        "worker agents have been dispatched",
        "all three worker agents have been dispatched",
        "polling for their responses",
        "polling for worker responses",
        "still waiting",
        "has been dispatched",
        "have been dispatched",
    ]
    return any(marker in text for marker in waiting_markers)


def _extract_session_id(session: dict[str, Any]) -> str:
    for key in ("id", "session_id"):
        value = session.get(key)
        if isinstance(value, str):
            return value
    nested = session.get("session")
    if isinstance(nested, dict):
        return _extract_session_id(nested)
    return ""


def _read_json(path: Path | None) -> dict[str, Any]:
    if not path:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise QoderCloudError(f"Qoder config not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise QoderCloudError(f"Qoder config is not valid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise QoderCloudError(f"Qoder config root must be an object: {path}")
    return data


def _profile_config(raw_config: dict[str, Any], profile: str) -> dict[str, Any]:
    profiles = raw_config.get("profiles")
    if isinstance(profiles, dict):
        selected = profiles.get(profile)
        if isinstance(selected, dict):
            return selected
    return raw_config


def _resolve_token(token_env: str, config_path: Path | None, env_file: str | None) -> str:
    token = os.environ.get(token_env, "")
    if token:
        return token.strip()
    candidates: list[Path] = []
    if env_file:
        env_path = Path(env_file).expanduser()
        if not env_path.is_absolute() and config_path:
            env_path = config_path.parent / env_path
        candidates.append(env_path)
    if config_path:
        candidates.append(config_path.parent / ".env")
    for candidate in candidates:
        values = _read_env_file(candidate)
        token = values.get(token_env, "")
        if token:
            return token.strip()
    return ""


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _unique_artifact_name(directory: Path, filename: str) -> str:
    safe = Path(filename).name or "artifact.md"
    candidate = safe
    stem = Path(safe).stem or "artifact"
    suffix = Path(safe).suffix or ".md"
    counter = 2
    while (directory / candidate).exists():
        candidate = f"{stem}-{counter}{suffix}"
        counter += 1
    return candidate


def _content_type_for(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".md":
        return "text/markdown"
    if suffix == ".json":
        return "application/json"
    if suffix in {".txt", ".log"}:
        return "text/plain"
    return "application/octet-stream"
