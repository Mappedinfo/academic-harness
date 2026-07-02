from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .paths import index_path


def init_index(project_root: Path) -> None:
    path = index_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            create table if not exists runs (
                run_id text primary key,
                project_id text not null,
                task_id text not null,
                status text not null,
                started_at text not null,
                finished_at text,
                manifest_path text not null,
                report_path text,
                summary_path text
            )
            """
        )
        conn.execute(
            """
            create table if not exists artifacts (
                id integer primary key autoincrement,
                run_id text not null,
                kind text not null,
                path text not null,
                size integer,
                foreign key(run_id) references runs(run_id)
            )
            """
        )
        conn.execute(
            """
            create table if not exists validations (
                id integer primary key autoincrement,
                run_id text not null,
                validator text not null,
                status text not null,
                report_path text,
                foreign key(run_id) references runs(run_id)
            )
            """
        )


def upsert_run(project_root: Path, manifest: dict[str, Any]) -> None:
    init_index(project_root)
    with sqlite3.connect(index_path(project_root)) as conn:
        conn.execute(
            """
            insert into runs (
                run_id, project_id, task_id, status, started_at, finished_at,
                manifest_path, report_path, summary_path
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(run_id) do update set
                status=excluded.status,
                finished_at=excluded.finished_at,
                manifest_path=excluded.manifest_path,
                report_path=excluded.report_path,
                summary_path=excluded.summary_path
            """,
            (
                manifest["run_id"],
                manifest["project_id"],
                manifest["task_id"],
                manifest["status"],
                manifest["started_at"],
                manifest.get("finished_at"),
                manifest["manifest_path"],
                manifest.get("report_path"),
                manifest.get("summary_path"),
            ),
        )
        conn.execute("delete from artifacts where run_id = ?", (manifest["run_id"],))
        for artifact in manifest.get("artifacts", []):
            conn.execute(
                "insert into artifacts (run_id, kind, path, size) values (?, ?, ?, ?)",
                (
                    manifest["run_id"],
                    artifact.get("kind", "artifact"),
                    artifact["path"],
                    artifact.get("size"),
                ),
            )
        conn.execute("delete from validations where run_id = ?", (manifest["run_id"],))
        for validation in manifest.get("validators", []):
            conn.execute(
                "insert into validations (run_id, validator, status, report_path) values (?, ?, ?, ?)",
                (
                    manifest["run_id"],
                    validation["validator"],
                    validation["status"],
                    validation.get("report_path"),
                ),
            )


def list_runs(project_root: Path) -> list[dict[str, Any]]:
    init_index(project_root)
    with sqlite3.connect(index_path(project_root)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            select run_id, project_id, task_id, status, started_at, finished_at,
                   manifest_path, report_path, summary_path
            from runs
            order by started_at desc
            """
        ).fetchall()
    return [dict(row) for row in rows]

