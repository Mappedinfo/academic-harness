from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import PROJECT_FILE
from .yamlio import dump_yaml

DEFAULT_QODER_REPO_URL = "https://github.com/Mappedinfo/qoder-agent-runner.git"
REGISTRY_ENV = "MAPPEDINFO_QODER_RUNNER_REGISTRY"
INSTALL_ROOT_ENV = "MAPPEDINFO_QODER_RUNNER_HOME"
BIN_DIR_ENV = "MAPPEDINFO_BIN_DIR"
DISABLE_NEARBY_ENV = "MAPPEDINFO_QODER_DISABLE_NEARBY"


def default_registry_path() -> Path:
    override = os.environ.get(REGISTRY_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "mappedinfo" / "qoder-agent-runner.json"


def default_install_root() -> Path:
    override = os.environ.get(INSTALL_ROOT_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "share" / "mappedinfo" / "qoder-agent-runner"


def default_bin_dir() -> Path:
    override = os.environ.get(BIN_DIR_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "bin"


def discover_qoder_runner(
    project_root: Path | None = None,
    project: dict[str, Any] | None = None,
    *,
    check_help: bool = False,
) -> dict[str, Any]:
    project_root = project_root.resolve() if project_root else None
    project = project or {}
    qoder = project.get("qoder") or {}
    messages: list[str] = []
    best_failure: dict[str, Any] | None = None

    candidates = _qoder_candidates(project_root, qoder)
    for candidate in candidates:
        runner_path = _resolve_command(candidate.get("runner_command"))
        if runner_path is None:
            messages.append(f"{candidate['source']}: runner not found")
            continue

        config_path = _resolve_config_path(project_root, candidate.get("config"))
        profile = str(candidate.get("profile") or "default")
        help_ok = True
        help_message = None
        if check_help:
            help_ok, help_message = _check_runner_help(runner_path, project_root)

        config_ok = config_path is not None and config_path.exists()
        config_check_ok = True
        config_check_message = None
        if check_help and config_ok:
            config_check_ok, config_check_message = _check_runner_config(runner_path, config_path, profile, project_root)
        result = {
            "ok": bool(help_ok and config_ok and config_check_ok),
            "source": candidate["source"],
            "runner_command": str(candidate.get("runner_command") or ""),
            "runner_path": str(runner_path),
            "config": str(candidate.get("config") or ""),
            "config_path": str(config_path) if config_path else None,
            "profile": profile,
            "registry_path": str(default_registry_path()),
            "repo_path": candidate.get("repo_path"),
            "install_hint": "academic-harness qoder install --project PATH",
        }
        status_parts = [f"runner found from {candidate['source']}: {runner_path}"]
        status_parts.append("config found" if config_ok else "config missing")
        if help_message:
            status_parts.append(help_message)
        if config_check_message:
            status_parts.append(config_check_message)
        result["message"] = "; ".join(status_parts)
        if result["ok"]:
            return result
        if best_failure is None:
            best_failure = result

    if best_failure is not None:
        return best_failure
    return {
        "ok": False,
        "source": "missing",
        "runner_command": str(qoder.get("runner_command") or "qoder-run"),
        "runner_path": None,
        "config": str(qoder.get("config") or ""),
        "config_path": None,
        "profile": str(qoder.get("profile") or "default"),
        "registry_path": str(default_registry_path()),
        "repo_path": None,
        "install_hint": "academic-harness qoder install --project PATH",
        "message": "; ".join(messages) if messages else "qoder-run not found",
    }


def install_qoder_runner(
    *,
    project_root: Path | None = None,
    project: dict[str, Any] | None = None,
    repo_url: str = DEFAULT_QODER_REPO_URL,
    install_root: Path | None = None,
    local_repo: Path | None = None,
    bin_dir: Path | None = None,
    config: Path | None = None,
    profile: str = "default",
    update_project: bool = False,
) -> dict[str, Any]:
    project_root = project_root.resolve() if project_root else None
    repo_path = _select_repo(project_root, local_repo, install_root or default_install_root(), repo_url)
    bin_dir = (bin_dir or default_bin_dir()).expanduser()
    bin_dir.mkdir(parents=True, exist_ok=True)

    if not repo_path.exists():
        repo_path.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", repo_url, str(repo_path)], cwd=repo_path.parent)

    _run(["swift", "build", "-c", "release"], cwd=repo_path)
    built_runner = repo_path / ".build" / "release" / "qoder-run"
    if not built_runner.exists():
        raise RuntimeError(f"built qoder-run missing: {built_runner}")

    target_runner = bin_dir / "qoder-run"
    shutil.copyfile(built_runner, target_runner)
    target_runner.chmod(target_runner.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    config_path = config.expanduser() if config else _default_repo_config(repo_path)
    registry = register_qoder_runner(
        executable_path=target_runner,
        config_path=config_path,
        profile=profile,
        repo_path=repo_path,
        repo_url=repo_url,
        source="install",
    )

    if update_project and project_root and project is not None:
        qoder = dict(project.get("qoder") or {})
        qoder["runner_command"] = str(target_runner)
        if config_path:
            qoder["config"] = str(config_path)
        qoder["profile"] = profile
        project["qoder"] = qoder
        (project_root / PROJECT_FILE).write_text(dump_yaml(project), encoding="utf-8")

    discovery = discover_qoder_runner(project_root, project, check_help=True)
    return {
        "installed": True,
        "repo_path": str(repo_path),
        "runner_path": str(target_runner),
        "config_path": str(config_path) if config_path else None,
        "profile": profile,
        "registry": registry,
        "discovery": discovery,
    }


def register_qoder_runner(
    *,
    executable_path: Path,
    config_path: Path | None,
    profile: str,
    repo_path: Path | None,
    repo_url: str = DEFAULT_QODER_REPO_URL,
    source: str = "manual",
    registry_path: Path | None = None,
) -> dict[str, Any]:
    registry_path = registry_path or default_registry_path()
    executable_path = executable_path.expanduser().resolve()
    payload = {
        "schema_version": 1,
        "name": "qoder-agent-runner",
        "source": source,
        "repo_url": repo_url,
        "repo_path": str(repo_path.expanduser().resolve()) if repo_path else None,
        "executable_path": str(executable_path),
        "config_path": str(config_path.expanduser().resolve()) if config_path else None,
        "profile": profile or "default",
        "registered_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"path": str(registry_path), "payload": payload}


def _qoder_candidates(project_root: Path | None, qoder: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    registry = _load_registry()
    registry_config = (registry or {}).get("config_path")
    project_runner = str(qoder.get("runner_command") or "").strip()
    project_config = str(qoder.get("config") or "").strip()
    project_profile = str(qoder.get("profile") or "default").strip() or "default"
    if project_runner:
        candidates.append(
            {
                "source": "project",
                "runner_command": project_runner,
                "config": project_config or registry_config,
                "profile": project_profile,
            }
        )

    if registry:
        candidates.append(
            {
                "source": "registry",
                "runner_command": registry.get("executable_path"),
                "config": project_config or registry.get("config_path"),
                "profile": project_profile or registry.get("profile") or "default",
                "repo_path": registry.get("repo_path"),
            }
        )

    candidates.append(
        {
            "source": "path",
            "runner_command": "qoder-run",
            "config": project_config or (registry or {}).get("config_path"),
            "profile": project_profile,
        }
    )

    for repo_path in _nearby_repo_candidates(project_root):
        for build_name in ["release", "debug"]:
            runner = repo_path / ".build" / build_name / "qoder-run"
            candidates.append(
                {
                    "source": f"nearby_repo_{build_name}",
                    "runner_command": str(runner),
                    "config": project_config or str(_default_repo_config(repo_path) or ""),
                    "profile": project_profile,
                    "repo_path": str(repo_path),
                }
            )
    return candidates


def _select_repo(project_root: Path | None, local_repo: Path | None, install_root: Path, repo_url: str) -> Path:
    if local_repo:
        return local_repo.expanduser().resolve()
    for candidate in _nearby_repo_candidates(project_root):
        if candidate.exists():
            return candidate
    return install_root.expanduser().resolve() / _repo_slug(repo_url)


def _repo_slug(repo_url: str) -> str:
    slug = repo_url.rstrip("/").split("/")[-1]
    return slug[:-4] if slug.endswith(".git") else slug


def _nearby_repo_candidates(project_root: Path | None) -> list[Path]:
    if os.environ.get(DISABLE_NEARBY_ENV, "").strip() in {"1", "true", "yes"}:
        return []
    roots: list[Path] = []
    if project_root:
        roots.extend([project_root, *project_root.parents])
    package_root = Path(__file__).resolve().parents[2]
    roots.extend([package_root, *list(package_root.parents)[:3]])

    candidates: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        for path in [
            root / "qoder-agent-runner",
            root.parent / "qoder-agent-runner",
            root / "mappedinfo" / "qoder-agent-runner",
        ]:
            resolved = str(path)
            if resolved not in seen:
                seen.add(resolved)
                candidates.append(path)
    return candidates


def _default_repo_config(repo_path: Path) -> Path | None:
    config = repo_path / "config.local.json"
    return config if config.exists() else None


def _load_registry() -> dict[str, Any] | None:
    path = default_registry_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _resolve_config_path(project_root: Path | None, value: Any) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if path.is_absolute() or project_root is None:
        return path
    return project_root / path


def _resolve_command(command: Any) -> Path | None:
    raw = str(command or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if path.is_absolute() or "/" in raw:
        return path if path.exists() and os.access(path, os.X_OK) else None
    resolved = shutil.which(raw)
    return Path(resolved) if resolved else None


def _check_runner_help(runner_path: Path, cwd: Path | None) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            [str(runner_path), "--help"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except Exception as error:
        return False, f"runner --help error: {error}"
    if completed.returncode == 0:
        return True, "runner --help ok"
    return False, "runner --help failed"


def _check_runner_config(runner_path: Path, config_path: Path, profile: str, cwd: Path | None) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            [
                str(runner_path),
                "--check-config",
                "--config",
                str(config_path),
                "--profile",
                profile,
            ],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=8,
        )
    except Exception as error:
        return False, f"runner config check error: {error}"
    if completed.returncode == 0:
        return True, "runner config ok"
    detail = (completed.stderr.strip() or completed.stdout.strip()).splitlines()
    message = detail[0] if detail else "runner config check failed"
    return False, message


def _run(command: list[str], cwd: Path) -> None:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit={completed.returncode}"
        raise RuntimeError(f"{' '.join(command)} failed: {detail}")
