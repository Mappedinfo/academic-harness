from __future__ import annotations

import zipfile
from pathlib import Path

NAME = "academic-harness"
VERSION = "0.1.0"
PACKAGE = "academic_harness"
DIST_INFO = f"{PACKAGE}-{VERSION}.dist-info"
WHEEL_NAME = f"{PACKAGE}-{VERSION}-py3-none-any.whl"


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    wheel_path = Path(wheel_directory) / WHEEL_NAME
    root = Path(__file__).parent
    records: list[str] = []

    with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as wheel:
        for source in sorted((root / "src" / PACKAGE).rglob("*.py")):
            target = f"{PACKAGE}/{source.relative_to(root / 'src' / PACKAGE)}"
            wheel.write(source, target)
            records.append(f"{target},,")

        dist_files = {
            f"{DIST_INFO}/METADATA": _metadata(),
            f"{DIST_INFO}/WHEEL": _wheel(),
            f"{DIST_INFO}/entry_points.txt": _entry_points(),
        }
        for target, content in dist_files.items():
            wheel.writestr(target, content)
            records.append(f"{target},,")

        records.append(f"{DIST_INFO}/RECORD,,")
        wheel.writestr(f"{DIST_INFO}/RECORD", "\n".join(records) + "\n")

    return WHEEL_NAME


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    return build_wheel(wheel_directory, config_settings, metadata_directory)


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    dist = Path(metadata_directory) / DIST_INFO
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "METADATA").write_text(_metadata(), encoding="utf-8")
    (dist / "WHEEL").write_text(_wheel(), encoding="utf-8")
    (dist / "entry_points.txt").write_text(_entry_points(), encoding="utf-8")
    return DIST_INFO


def _metadata() -> str:
    return (
        "Metadata-Version: 2.3\n"
        f"Name: {NAME}\n"
        f"Version: {VERSION}\n"
        "Summary: Local-first academic harness for project tasks, Qoder runs, artifacts, and validators.\n"
        "Requires-Python: >=3.11\n"
    )


def _wheel() -> str:
    return (
        "Wheel-Version: 1.0\n"
        "Generator: academic-harness-build\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
    )


def _entry_points() -> str:
    return "[console_scripts]\nacademic-harness = academic_harness.cli:main\n"
