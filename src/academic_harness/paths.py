from __future__ import annotations

from pathlib import Path


PROJECT_FILE = "project.yaml"
WORKBENCH_DIR = ".workbench"
RUNS_DIR = "runs"
INDEX_FILE = "index.sqlite"
MANIFEST_FILE = "manifest.json"


def find_project_root(start: Path) -> Path:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / PROJECT_FILE).exists():
            return candidate
    raise FileNotFoundError(f"Could not find {PROJECT_FILE} from {start}")


def workbench_dir(project_root: Path) -> Path:
    return project_root / WORKBENCH_DIR


def runs_dir(project_root: Path) -> Path:
    return workbench_dir(project_root) / RUNS_DIR


def index_path(project_root: Path) -> Path:
    return workbench_dir(project_root) / INDEX_FILE


def run_dir(project_root: Path, run_id: str) -> Path:
    return runs_dir(project_root) / safe_name(run_id)


def safe_name(value: str) -> str:
    cleaned = value.strip().replace("/", "_").replace("\\", "_").replace(":", "_")
    if not cleaned:
        raise ValueError("Name cannot be empty")
    return cleaned


def project_relative(project_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root.resolve()))
    except ValueError:
        return str(path)

