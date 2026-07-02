from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .project import init_project, project_status, set_lan_config, set_qoder_config
from .qoder_dependency import DEFAULT_QODER_REPO_URL, discover_qoder_runner, install_qoder_runner
from .paths import PROJECT_FILE
from .runs import list_project_runs, rerun_validators, run_task, show_run
from .yamlio import load_yaml


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

    project_parser = subparsers.add_parser("project", help="project commands")
    project_subparsers = project_parser.add_subparsers(dest="project_command", required=True)
    project_status_parser = project_subparsers.add_parser("status", help="check project configuration")
    project_status_parser.add_argument("--project", required=True, type=Path)
    project_status_parser.add_argument("--json", action="store_true")
    project_status_parser.add_argument("--check-lan", action="store_true")
    project_status_parser.set_defaults(func=_cmd_project_status)

    project_lan = project_subparsers.add_parser("set-lan", help="write LAN worker config")
    project_lan.add_argument("--project", required=True, type=Path)
    project_lan.add_argument("--server")
    project_lan.add_argument("--project-root")
    project_lan.add_argument("--ssh-alias")
    project_lan.add_argument("--enabled", choices=["true", "false"])
    project_lan.set_defaults(func=_cmd_project_set_lan)

    project_qoder = project_subparsers.add_parser("set-qoder", help="write Qoder runner config")
    project_qoder.add_argument("--project", required=True, type=Path)
    project_qoder.add_argument("--runner-command")
    project_qoder.add_argument("--config")
    project_qoder.add_argument("--profile")
    project_qoder.set_defaults(func=_cmd_project_set_qoder)

    qoder_parser = subparsers.add_parser("qoder", help="Qoder runner dependency commands")
    qoder_subparsers = qoder_parser.add_subparsers(dest="qoder_command", required=True)
    qoder_discover = qoder_subparsers.add_parser("discover", help="discover registered qoder-run")
    qoder_discover.add_argument("--project", type=Path)
    qoder_discover.add_argument("--json", action="store_true")
    qoder_discover.set_defaults(func=_cmd_qoder_discover)

    qoder_install = qoder_subparsers.add_parser("install", help="install and register qoder-agent-runner")
    qoder_install.add_argument("--project", type=Path)
    qoder_install.add_argument("--repo", default=DEFAULT_QODER_REPO_URL)
    qoder_install.add_argument("--install-root", type=Path)
    qoder_install.add_argument("--local-repo", type=Path)
    qoder_install.add_argument("--bin-dir", type=Path)
    qoder_install.add_argument("--config", type=Path)
    qoder_install.add_argument("--profile", default="default")
    qoder_install.add_argument("--no-project-update", action="store_true")
    qoder_install.set_defaults(func=_cmd_qoder_install)

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


def _cmd_project_status(args: argparse.Namespace) -> int:
    status = project_status(args.project, check_lan=args.check_lan)
    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"project={status['project_root']}")
        for name, check in status["checks"].items():
            mark = "ok" if check.get("ok") else "fail"
            print(f"{name}={mark} {check.get('message', '')}")
    return 0


def _cmd_project_set_lan(args: argparse.Namespace) -> int:
    enabled = None if args.enabled is None else args.enabled == "true"
    status = set_lan_config(
        args.project,
        server=args.server,
        project_root=args.project_root,
        ssh_alias=args.ssh_alias,
        enabled=enabled,
    )
    print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _cmd_project_set_qoder(args: argparse.Namespace) -> int:
    status = set_qoder_config(
        args.project,
        runner_command=args.runner_command,
        config=args.config,
        profile=args.profile,
    )
    print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _cmd_qoder_discover(args: argparse.Namespace) -> int:
    project_root, project = _load_project_if_present(args.project)
    discovery = discover_qoder_runner(project_root, project, check_help=True)
    if args.json:
        print(json.dumps(discovery, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"ok={str(discovery['ok']).lower()}")
        print(f"source={discovery.get('source')}")
        print(f"runner={discovery.get('runner_path') or ''}")
        print(f"config={discovery.get('config_path') or ''}")
        print(f"profile={discovery.get('profile') or ''}")
        print(f"message={discovery.get('message') or ''}")
    return 0 if discovery.get("runner_path") else 1


def _cmd_qoder_install(args: argparse.Namespace) -> int:
    project_root, project = _load_project_if_present(args.project)
    result = install_qoder_runner(
        project_root=project_root,
        project=project,
        repo_url=args.repo,
        install_root=args.install_root,
        local_repo=args.local_repo,
        bin_dir=args.bin_dir,
        config=args.config,
        profile=args.profile,
        update_project=not args.no_project_update,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
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


def _load_project_if_present(project_path: Path | None) -> tuple[Path | None, dict[str, Any] | None]:
    if project_path is None:
        return None, None
    project_root = project_path.resolve()
    project_file = project_root / PROJECT_FILE
    if not project_file.exists():
        return project_root, None
    return project_root, load_yaml(project_file)


if __name__ == "__main__":
    raise SystemExit(main())
