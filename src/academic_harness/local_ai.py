from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SUPPORTED_LOCAL_AI_PROVIDERS = {"openai_compatible", "ollama", "vllm"}
SUPPORTED_LOCAL_AI_TRANSPORTS = {"auto", "urllib", "curl"}
DEFAULT_LONGCAT_API_URL = "https://api.longcat.chat/openai"
DEFAULT_LONGCAT_MODEL = "LongCat-2.0"
DEFAULT_LONGCAT_API_KEY_ENV = "LONG_CAT_API_KEY"
DEFAULT_LONGCAT_API_URL_ENV = "LONG_CAT_API_URL"
DEFAULT_LONGCAT_MODEL_ENV = "LONG_CAT_MODEL"


class LocalAIError(RuntimeError):
    pass


@dataclass(frozen=True)
class LocalAIConfig:
    enabled: bool
    provider: str
    base_url: str
    model: str
    api_key_env: str
    api_key: str
    timeout_seconds: int
    transport: str

    def safe_metadata(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "api_key_env": self.api_key_env,
            "api_key_present": bool(self.api_key),
            "timeout_seconds": self.timeout_seconds,
            "transport": self.transport,
            "app_proxy_disabled": True,
        }


class LocalAIClient:
    def __init__(self, config: LocalAIConfig) -> None:
        self.config = config
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.2) -> str:
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "academic-harness-local-ai/0.1",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        if self.config.transport == "curl":
            return self._chat_with_curl(data, headers)
        request = urllib.request.Request(
            _chat_url(self.config.base_url),
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=self.config.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise LocalAIError(f"Local AI HTTP {exc.code}: {error_body}") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, socket.gaierror):
                dns_error = LocalAIError(
                    "Local AI direct/no-proxy DNS failed. "
                    "Configure system DNS or TUN direct rules for api.longcat.chat, or set a reachable base_url."
                )
                if self.config.transport == "auto":
                    return self._chat_with_curl(data, headers)
                raise dns_error from exc
            raise LocalAIError(f"Local AI request failed: {exc}") from exc
        return _parse_chat_body(body)

    def _chat_with_curl(self, data: bytes, headers: dict[str, str]) -> str:
        curl = shutil.which("curl")
        if not curl:
            raise LocalAIError("Local AI curl fallback requested but curl is not available")
        with tempfile.NamedTemporaryFile(prefix="academic-harness-local-ai-", suffix=".json", delete=False) as payload_file:
            payload_file.write(data)
            payload_path = payload_file.name
        try:
            config_lines = [
                f'url = "{_curl_config_value(_chat_url(self.config.base_url))}"',
                'request = "POST"',
                'silent',
                'show-error',
                'fail-with-body',
                f'connect-timeout = "{min(self.config.timeout_seconds, 30)}"',
                f'max-time = "{self.config.timeout_seconds}"',
                f'data-binary = "@{_curl_config_value(payload_path)}"',
            ]
            for key, value in headers.items():
                config_lines.append(f'header = "{_curl_config_value(f"{key}: {value}")}"')
            completed = subprocess.run(
                [curl, "--noproxy", "*", "--config", "-"],
                input="\n".join(config_lines) + "\n",
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds + 5,
                check=False,
            )
        finally:
            Path(payload_path).unlink(missing_ok=True)
        if completed.returncode != 0:
            detail = (completed.stdout or completed.stderr).strip()[:500]
            raise LocalAIError(f"Local AI curl direct/no-proxy request failed: {detail}")
        return _parse_chat_body(completed.stdout)


def resolve_local_ai_config(project: dict[str, Any], project_root: Path | None = None) -> LocalAIConfig:
    raw = project.get("local_ai") if isinstance(project.get("local_ai"), dict) else {}
    enabled = _bool_value(raw.get("enabled"), False)
    provider = str(raw.get("provider") or "openai_compatible")
    env_file = _configured_env_file(raw, project_root)
    base_url = str(raw.get("base_url") or _env_value(DEFAULT_LONGCAT_API_URL_ENV, project_root, env_file) or DEFAULT_LONGCAT_API_URL).strip()
    model = str(raw.get("model") or _env_value(DEFAULT_LONGCAT_MODEL_ENV, project_root, env_file) or DEFAULT_LONGCAT_MODEL).strip()
    api_key_env = str(raw.get("api_key_env") or DEFAULT_LONGCAT_API_KEY_ENV).strip()
    timeout_seconds = _positive_int(raw.get("timeout_seconds"), 120)
    transport = str(raw.get("transport") or "auto").strip()
    api_key = _env_value(api_key_env, project_root, env_file).strip() if api_key_env else ""

    if provider not in SUPPORTED_LOCAL_AI_PROVIDERS:
        raise LocalAIError(f"unsupported local_ai provider: {provider}")
    if transport not in SUPPORTED_LOCAL_AI_TRANSPORTS:
        raise LocalAIError(f"unsupported local_ai transport: {transport}")
    if not enabled:
        raise LocalAIError("local_ai is disabled")
    if not base_url:
        raise LocalAIError("local_ai.base_url is missing")
    if not model:
        raise LocalAIError("local_ai.model is missing")
    return LocalAIConfig(
        enabled=enabled,
        provider=provider,
        base_url=base_url,
        model=model,
        api_key_env=api_key_env,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
        transport=transport,
    )


def local_ai_status(project: dict[str, Any], check_connection: bool = False, project_root: Path | None = None) -> dict[str, Any]:
    raw = project.get("local_ai") if isinstance(project.get("local_ai"), dict) else {}
    enabled = _bool_value(raw.get("enabled"), False)
    provider = str(raw.get("provider") or "openai_compatible")
    env_file = _configured_env_file(raw, project_root)
    base_url = str(raw.get("base_url") or _env_value(DEFAULT_LONGCAT_API_URL_ENV, project_root, env_file) or DEFAULT_LONGCAT_API_URL).strip()
    model = str(raw.get("model") or _env_value(DEFAULT_LONGCAT_MODEL_ENV, project_root, env_file) or DEFAULT_LONGCAT_MODEL).strip()
    api_key_env = str(raw.get("api_key_env") or DEFAULT_LONGCAT_API_KEY_ENV).strip()
    timeout_seconds = _positive_int(raw.get("timeout_seconds"), 120)
    transport = str(raw.get("transport") or "auto").strip()
    token_present = bool(_env_value(api_key_env, project_root, env_file).strip()) if api_key_env else False

    errors: list[str] = []
    if not enabled:
        errors.append("disabled")
    if provider not in SUPPORTED_LOCAL_AI_PROVIDERS:
        errors.append("unsupported provider")
    if transport not in SUPPORTED_LOCAL_AI_TRANSPORTS:
        errors.append("unsupported transport")
    if not base_url:
        errors.append("base_url missing")
    if not model:
        errors.append("model missing")

    result: dict[str, Any] = {
        "ok": not errors,
        "enabled": enabled,
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "api_key_env": api_key_env,
        "api_key_present": token_present,
        "timeout_seconds": timeout_seconds,
        "transport": transport,
        "env_file": str(env_file) if env_file is not None else "",
        "app_proxy_disabled": True,
        "message": "Local AI configured" if not errors else f"Local AI {', '.join(errors)}",
    }
    if api_key_env and not token_present:
        result["token_warning"] = f"{api_key_env} not set"
    if check_connection and result["ok"]:
        try:
            config = resolve_local_ai_config({"local_ai": raw}, project_root=project_root)
            LocalAIClient(config).chat(
                [
                    {"role": "system", "content": "Return exactly: ok"},
                    {"role": "user", "content": "Health check."},
                ],
                temperature=0,
            )
            result["connection_ok"] = True
            result["message"] = "Local AI configured; connection ok"
        except Exception as exc:
            result["ok"] = False
            result["connection_ok"] = False
            result["message"] = f"Local AI connection failed: {exc}"
    return result


def parse_json_or_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        return {}
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return {"text": text}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _parse_chat_body(body: str) -> str:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise LocalAIError(f"Local AI returned non-JSON response: {body[:200]}") from exc
    return _extract_chat_content(parsed)


def _extract_chat_content(parsed: dict[str, Any]) -> str:
    choices = parsed.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
            if isinstance(first.get("text"), str):
                return first["text"]
    raise LocalAIError("Local AI response did not include choices[0].message.content")


def _chat_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base == DEFAULT_LONGCAT_API_URL:
        return f"{base}/v1/chat/completions"
    return f"{base}/chat/completions"


def _curl_config_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _configured_env_file(raw: dict[str, Any], project_root: Path | None) -> Path | None:
    env_file = str(raw.get("env_file") or "").strip()
    if not env_file:
        return None
    path = Path(env_file).expanduser()
    if path.is_absolute():
        return path
    if project_root is not None:
        return project_root / path
    return Path.cwd() / path


def _env_value(name: str, project_root: Path | None, env_file: Path | None = None) -> str:
    direct = os.environ.get(name, "").strip()
    if direct:
        return direct
    for path in _candidate_env_files(project_root, env_file):
        value = _read_env_value(path, name)
        if value:
            return value
    return ""


def _candidate_env_files(project_root: Path | None, env_file: Path | None) -> list[Path]:
    candidates: list[Path] = []
    if env_file is not None:
        candidates.append(env_file)
    if project_root is not None:
        candidates.append(project_root / ".env")
    candidates.append(Path.cwd() / ".env")
    repo_root = Path(__file__).resolve().parents[2]
    candidates.append(repo_root / ".env")

    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path.expanduser().resolve()) if path.exists() else str(path.expanduser())
        if key not in seen:
            seen.add(key)
            unique.append(path.expanduser())
    return unique


def _read_env_value(path: Path, name: str) -> str:
    if not path.exists() or not path.is_file():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip().removeprefix("export ").strip() != name:
            continue
        return _clean_env_value(value)
    return ""


def _clean_env_value(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1]
    return cleaned.strip()


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _bool_value(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
