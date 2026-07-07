from __future__ import annotations

import io
import json
import os
import socket
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from academic_harness.local_ai import LocalAIClient, LocalAIConfig, LocalAIError, local_ai_status, resolve_local_ai_config
from academic_harness.project import init_project, set_local_ai_config
from academic_harness.yamlio import load_yaml


class FakeResponse:
    def __init__(self, body: str) -> None:
        self.body = body.encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class FakeOpener:
    def __init__(self, body: str | Exception) -> None:
        self.body = body
        self.last_request = None

    def open(self, request, timeout: int):
        self.last_request = request
        if isinstance(self.body, Exception):
            raise self.body
        return FakeResponse(self.body)


class LocalAITests(unittest.TestCase):
    def test_resolves_config_and_token_env_without_exposing_value(self) -> None:
        with patch.dict(os.environ, {"LOCAL_AI_TEST_KEY": "secret"}, clear=False):
            config = resolve_local_ai_config(
                {
                    "local_ai": {
                        "enabled": True,
                        "provider": "openai_compatible",
                        "base_url": "http://127.0.0.1:11434/v1",
                        "model": "qwen",
                        "api_key_env": "LOCAL_AI_TEST_KEY",
                    }
                }
            )

        self.assertEqual(config.api_key, "secret")
        self.assertTrue(config.safe_metadata()["api_key_present"])
        self.assertNotIn("secret", json.dumps(config.safe_metadata()))
        self.assertTrue(config.safe_metadata()["app_proxy_disabled"])

    def test_longcat_defaults_read_dotenv_and_use_openai_v1_chat_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / ".env").write_text(
                "\n".join(
                    [
                        "LONG_CAT_API_URL=https://api.longcat.chat/openai",
                        "LONG_CAT_API_" + "KEY=unit-test-longcat-key",
                        "LONG_CAT_MODEL=LongCat-2.0",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                config = resolve_local_ai_config({"local_ai": {"enabled": True}}, project_root=project)

        self.assertEqual(config.base_url, "https://api.longcat.chat/openai")
        self.assertEqual(config.model, "LongCat-2.0")
        self.assertEqual(config.api_key_env, "LONG_CAT_API_KEY")
        self.assertEqual(config.api_key, "unit-test-longcat-key")

        client = LocalAIClient(config)
        fake = FakeOpener('{"choices":[{"message":{"content":"ok"}}]}')
        client.opener = fake  # type: ignore[assignment]
        self.assertEqual(client.chat([{"role": "user", "content": "hi"}]), "ok")
        self.assertEqual(fake.last_request.full_url, "https://api.longcat.chat/openai/v1/chat/completions")
        self.assertEqual(fake.last_request.headers.get("Authorization"), "Bearer unit-test-longcat-key")

    def test_status_reports_missing_config_and_token_warning(self) -> None:
        status = local_ai_status(
            {
                "local_ai": {
                    "enabled": True,
                    "provider": "openai_compatible",
                    "base_url": "http://127.0.0.1:11434/v1",
                    "model": "qwen",
                    "api_key_env": "MISSING_LOCAL_AI_KEY",
                }
            }
        )

        self.assertTrue(status["ok"])
        self.assertFalse(status["api_key_present"])
        self.assertIn("token_warning", status)
        self.assertTrue(status["app_proxy_disabled"])

        disabled = local_ai_status({"local_ai": {"enabled": False}})
        self.assertFalse(disabled["ok"])
        self.assertIn("disabled", disabled["message"])

    def test_openai_compatible_chat_success_and_failures(self) -> None:
        config = LocalAIConfig(
            enabled=True,
            provider="openai_compatible",
            base_url="http://localhost:8000/v1",
            model="test-model",
            api_key_env="",
            api_key="",
            timeout_seconds=10,
            transport="urllib",
        )
        client = LocalAIClient(config)
        client.opener = FakeOpener('{"choices":[{"message":{"content":"ok"}}]}')  # type: ignore[assignment]

        self.assertEqual(client.chat([{"role": "user", "content": "hi"}]), "ok")

        client.opener = FakeOpener("not json")  # type: ignore[assignment]
        with self.assertRaises(LocalAIError):
            client.chat([{"role": "user", "content": "hi"}])

        error = urllib.error.HTTPError("http://local", 500, "server", {}, io.BytesIO(b"boom"))
        client.opener = FakeOpener(error)  # type: ignore[assignment]
        with self.assertRaises(LocalAIError):
            client.chat([{"role": "user", "content": "hi"}])

        dns_error = urllib.error.URLError(socket.gaierror(8, "nodename nor servname provided, or not known"))
        client.opener = FakeOpener(dns_error)  # type: ignore[assignment]
        with self.assertRaisesRegex(LocalAIError, "direct/no-proxy DNS failed"):
            client.chat([{"role": "user", "content": "hi"}])

    def test_set_local_ai_config_writes_project_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = init_project(Path(tmp) / "demo")
            status = set_local_ai_config(
                project,
                enabled=True,
                provider="ollama",
                base_url="http://127.0.0.1:11434/v1",
                model="qwen",
                api_key_env="",
                timeout_seconds=30,
                transport="curl",
                env_file="local-ai.env",
            )
            data = load_yaml(project / "project.yaml")

        self.assertTrue(data["local_ai"]["enabled"])
        self.assertEqual(data["local_ai"]["provider"], "ollama")
        self.assertEqual(data["local_ai"]["model"], "qwen")
        self.assertEqual(data["local_ai"]["transport"], "curl")
        self.assertEqual(data["local_ai"]["env_file"], "local-ai.env")
        self.assertTrue(status["checks"]["local_ai"]["ok"])


if __name__ == "__main__":
    unittest.main()
