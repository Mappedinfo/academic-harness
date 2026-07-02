from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .project import init_project
from .runs import list_project_runs, rerun_validators, run_task, show_run


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as error:
        print(f"error={error}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="academic-harness")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create a research harness project")
    init_parser.add_argument("project_dir", type=Path)
    init_parser.add_argument("--force", action="store_true", help="overwrite template files")
    init_parser.set_defaults(func=_cmd_init)

    task_parser = subparsers.add_parser("task", help="task commands")
    task_subparsers = task_parser.add_subparsers(dest="task_command", required=True)
    task_run = task_subparsers.add_parser("run", help="run a task")
    task_run.add_argument("task_yaml", type=Path)
    task_run.add_argument("--project", type=Path, help="project root; defaults to nearest project.yaml")
    task_run.add_argument("--adapter", choices=["qoder", "fake"], default="qoder")
    task_run.add_argument("--run-id")
    task_run.set_defaults(func=_cmd_task_run)

    runs_parser = subparsers.add_parser("runs", help="run history commands")
    runs_subparsers = runs_parser.add_subparsers(dest="runs_command", required=True)
    runs_list = runs_subparsers.add_parser("list", help="list runs")
    runs_list.add_argument("--project", required=True, type=Path)
    runs_list.add_argument("--json", action="store_true")
    runs_list.set_defaults(func=_cmd_runs_list)

    run_parser = subparsers.add_parser("run", help="single-run commands")
    run_subparsers = run_parser.add_subparsers(dest="run_command", required=True)
    run_show = run_subparsers.add_parser("show", help="show a run manifest")
    run_show.add_argument("run_id")
    run_show.add_argument("--project", required=True, type=Path)
    run_show.set_defaults(func=_cmd_run_show)

    validate_parser = subparsers.add_parser("validate", help="rerun validators for a run")
    validate_parser.add_argument("run_id")
    validate_parser.add_argument("--project", required=True, type=Path)
    validate_parser.set_defaults(func=_cmd_validate)

    return parser


def _cmd_init(args: argparse.Namespace) -> int:
    project_root = init_project(args.project_dir, force=args.force)
    print(f"project={project_root}")
    print(f"config={project_root / 'project.yaml'}")
    print(f"sample_task={project_root / 'tasks' / 'sample_task.yaml'}")
    return 0


def _cmd_task_run(args: argparse.Namespace) -> int:
    manifest = run_task(args.task_yaml, adapter=args.adapter, run_id=args.run_id, project_root=args.project)
    _print_run_summary(manifest)
    return 0 if manifest["status"] == "passed" else 1


def _cmd_runs_list(args: argparse.Namespace) -> int:
    runs = list_project_runs(args.project)
    if args.json:
        print(json.dumps(runs, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if not runs:
        print("No runs")
        return 0
    print("run_id\tstatus\ttask_id\tstarted_at\treport")
    for run in runs:
        print(
            "\t".join(
                [
                    str(run["run_id"]),
                    str(run["status"]),
                    str(run["task_id"]),
                    str(run["started_at"]),
                    str(run.get("report_path") or ""),
                ]
            )
        )
    return 0


def _cmd_run_show(args: argparse.Namespace) -> int:
    print(json.dumps(show_run(args.run_id, args.project), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    manifest = rerun_validators(args.run_id, args.project)
    _print_run_summary(manifest)
    return 0 if manifest["status"] == "passed" else 1


def _print_run_summary(manifest: dict[str, Any]) -> None:
    print(f"run_id={manifest['run_id']}")
    print(f"status={manifest['status']}")
    print(f"run_dir={manifest['run_dir']}")
    if manifest.get("report_path"):
        print(f"report={manifest['report_path']}")
    if manifest.get("summary_path"):
        print(f"summary={manifest['summary_path']}")
    print(f"manifest={manifest['manifest_path']}")


if __name__ == "__main__":
    raise SystemExit(main())
