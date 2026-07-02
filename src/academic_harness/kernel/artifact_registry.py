from __future__ import annotations

from pathlib import Path
from typing import Any

from ..paths import project_relative
from ..yamlio import write_json


def collect_artifacts(project_root: Path, run_dir: Path, artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    registry: list[dict[str, Any]] = []
    seen: set[str] = set()
    for artifact in artifacts:
        path_value = artifact.get("path")
        if not path_value:
            continue
        path = Path(str(path_value))
        if not path.exists() or not path.is_file():
            continue
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        record = {
            "kind": str(artifact.get("kind") or "artifact"),
            "path": str(path),
            "project_relative_path": project_relative(project_root, path),
            "run_relative_path": project_relative(run_dir, path),
            "size": path.stat().st_size,
        }
        registry.append(record)
    write_json(run_dir / "artifacts.json", {"artifacts": registry})
    return registry
