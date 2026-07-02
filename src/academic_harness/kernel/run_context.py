from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..paths import MANIFEST_FILE, run_dir


@dataclass(frozen=True)
class RunContext:
    project_root: Path
    project: dict[str, Any]
    task: dict[str, Any]
    task_path: Path
    run_id: str
    requested_adapter: str
    resolved_adapter: str
    mode: str
    run_dir: Path
    manifest_path: Path

    @classmethod
    def create(
        cls,
        project_root: Path,
        project: dict[str, Any],
        task: dict[str, Any],
        task_path: Path,
        run_id: str,
        requested_adapter: str,
        resolved_adapter: str,
        mode: str,
    ) -> "RunContext":
        output_dir = run_dir(project_root, run_id)
        return cls(
            project_root=project_root,
            project=project,
            task=task,
            task_path=task_path,
            run_id=run_id,
            requested_adapter=requested_adapter,
            resolved_adapter=resolved_adapter,
            mode=mode,
            run_dir=output_dir,
            manifest_path=output_dir / MANIFEST_FILE,
        )
