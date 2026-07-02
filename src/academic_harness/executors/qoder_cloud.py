from __future__ import annotations

import json
import os
import signal
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..qoder_dependency import default_registry_path, discover_qoder_runner
from .qoder_cli import prompt_text_for_task


class QoderCloudError(RuntimeError):
    pass


class QoderCloudCancelled(RuntimeError):
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


class QoderCloudClient:
    def __init__(self, config: QoderCloudConfig) -> None:
        self.config = config
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def create_session(self, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        agent: str | dict[str, str]
        if self.config.agent_version:
            agent = {
                "id": self.config.agent_id,
                "type": "agent",
                "version": self.config.agent_version,
            }
        else:
            agent = self.config.agent_id
        payload: dict[str, Any] = {
            "agent": agent,
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
            return self.opener.open(request, timeout=120)
        except urllib.error.URLError as exc:
            raise QoderCloudError(f"Qoder event stream failed: {exc}") from exc

    def cancel_session(self, session_id: str) -> dict[str, Any]:
        return self._request_json("POST", f"sessions/{session_id}/cancel", {})

    def _request_json(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self._url(path),
            data=data,
            headers={
                "Authorization": f"Bearer {self.config.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "academic-harness-qoder-cloud/0.2",
            },
            method=method,
        )
        try:
            with self.opener.open(request, timeout=120) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise QoderCloudError(f"Qoder HTTP {exc.code}: {error_body}") from exc
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
    prompt = _build_cloud_prompt(project_root, project, task, run_id)
    (qoder_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

    config = resolve_qoder_cloud_config(project_root, project, task)
    client = QoderCloudClient(config)
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
        stream_summary = _stream_and_extract(client, session_id, qoder_dir)
        status = "succeeded" if stream_summary["idle_seen"] else "failed"
        stop_reason = "session.status_idle" if stream_summary["idle_seen"] else "stream ended before idle"
    except QoderCloudCancelled as exc:
        status = "cancelled"
        stop_reason = str(exc)
        stream_summary = {"writes": [], "delivered": [], "summary_path": None, "report_path": None}
        _ensure_raw_event_files(qoder_dir)
    except Exception as exc:
        status = "failed"
        stop_reason = str(exc)
        stream_summary = {"writes": [], "delivered": [], "summary_path": None, "report_path": None}
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
        "report_path": str((qoder_dir / "report.md").resolve()) if (qoder_dir / "report.md").exists() else None,
        "summary_path": str((qoder_dir / "summary.md").resolve()) if (qoder_dir / "summary.md").exists() else None,
        "artifacts": stream_summary.get("writes", []),
        "delivered_artifacts": stream_summary.get("delivered", []),
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


def _build_cloud_prompt(project_root: Path, project: dict[str, Any], task: dict[str, Any], run_id: str) -> str:
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
        "project": {
            "id": project.get("project_id") or project.get("project", {}).get("id") or project.get("id"),
            "title": project.get("title") or project.get("project", {}).get("title"),
        },
    }
    instructions = (
        "You are the Qoder Cloud coordinator for an academic research harness run.\n"
        "Run the work in cloud. If managed child agents or tools are available, decompose the work, "
        "delegate subtasks, collect evidence, and deliver artifacts.\n"
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


def _string_metadata(values: dict[str, Any]) -> dict[str, str]:
    return {key: str(value) for key, value in values.items() if value is not None}


def _ensure_raw_event_files(qoder_dir: Path) -> None:
    if not (qoder_dir / "events.sse").exists():
        (qoder_dir / "events.sse").write_text("", encoding="utf-8")
    if not (qoder_dir / "events.jsonl").exists():
        (qoder_dir / "events.jsonl").write_text("", encoding="utf-8")


def _stream_and_extract(client: QoderCloudClient, session_id: str, qoder_dir: Path) -> dict[str, Any]:
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
                if extractor.is_idle(record):
                    idle_seen = True
                    break
    extractor.write_outputs()
    summary = extractor.summary()
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
        if event_type == "agent.tool_use":
            self._consume_tool_use(payload)
            return
        if event_type in {"agent.artifact_delivered", "artifact_delivered"}:
            delivered = _artifact_delivered_record(payload)
            if delivered:
                self.delivered.append(delivered)

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

    def write_outputs(self) -> None:
        report_content = self.primary_write_content or self.last_write_content or self.last_agent_message
        if report_content:
            (self.qoder_dir / "report.md").write_text(report_content, encoding="utf-8")
        if self.last_agent_message:
            (self.qoder_dir / "summary.md").write_text(self.last_agent_message, encoding="utf-8")

    def summary(self) -> dict[str, Any]:
        return {
            "writes": self.writes,
            "delivered": self.delivered,
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


def _artifact_delivered_record(payload: dict[str, Any]) -> dict[str, Any]:
    artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else payload
    keys = ["file_id", "original_filename", "content_type", "size", "name", "path"]
    return {key: artifact.get(key) for key in keys if artifact.get(key) is not None}


def _is_primary_report_name(value: str) -> bool:
    name = Path(value).name.lower()
    return name in {"report.md", "research_report.md", "final_report.md"} or (
        "report" in name and "summary" not in name and "readme" not in name
    )


def _is_secondary_artifact_name(value: str) -> bool:
    name = Path(value).name.lower()
    return name in {"summary.md", "readme.md", "index.md"} or "summary" in name or "readme" in name or "index" in name


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
