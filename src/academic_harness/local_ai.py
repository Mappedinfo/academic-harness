from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


SUPPORTED_LOCAL_AI_PROVIDERS = {"openai_compatible", "ollama", "vllm"}


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

    def safe_metadata(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "api_key_env": self.api_key_env,
            "api_key_present": bool(self.api_key),
            "timeout_seconds": self.timeout_seconds,
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
            raise LocalAIError(f"Local AI request failed: {exc}") from exc
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise LocalAIError(f"Local AI returned non-JSON response: {body[:200]}") from exc
        return _extract_chat_content(parsed)


def resolve_local_ai_config(project: dict[str, Any]) -> LocalAIConfig:
    raw = project.get("local_ai") if isinstance(project.get("local_ai"), dict) else {}
    enabled = _bool_value(raw.get("enabled"), False)
    provider = str(raw.get("provider") or "openai_compatible")
    base_url = str(raw.get("base_url") or "").strip()
    model = str(raw.get("model") or "").strip()
    api_key_env = str(raw.get("api_key_env") or "").strip()
    timeout_seconds = _positive_int(raw.get("timeout_seconds"), 120)
    api_key = os.environ.get(api_key_env, "").strip() if api_key_env else ""

    if provider not in SUPPORTED_LOCAL_AI_PROVIDERS:
        raise LocalAIError(f"unsupported local_ai provider: {provider}")
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
    )


def local_ai_status(project: dict[str, Any], check_connection: bool = False) -> dict[str, Any]:
    raw = project.get("local_ai") if isinstance(project.get("local_ai"), dict) else {}
    enabled = _bool_value(raw.get("enabled"), False)
    provider = str(raw.get("provider") or "openai_compatible")
    base_url = str(raw.get("base_url") or "").strip()
    model = str(raw.get("model") or "").strip()
    api_key_env = str(raw.get("api_key_env") or "").strip()
    timeout_seconds = _positive_int(raw.get("timeout_seconds"), 120)
    token_present = bool(os.environ.get(api_key_env, "").strip()) if api_key_env else False

    errors: list[str] = []
    if not enabled:
        errors.append("disabled")
    if provider not in SUPPORTED_LOCAL_AI_PROVIDERS:
        errors.append("unsupported provider")
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
        "message": "Local AI configured" if not errors else f"Local AI {', '.join(errors)}",
    }
    if api_key_env and not token_present:
        result["token_warning"] = f"{api_key_env} not set"
    if check_connection and result["ok"]:
        try:
            config = resolve_local_ai_config({"local_ai": raw})
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
    return f"{base}/chat/completions"


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
