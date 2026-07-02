# Mappedinfo Academic Harness

Local-first research harness for project-scoped tasks, Qoder runs, artifacts, validators, and cloud experiment control.

V2 keeps the loop explicit:

```text
Project -> Task -> Executor -> Artifacts -> Validator Report
```

The Qoder domestic endpoint remains `https://api.qoder.com.cn/api/v1/cloud` in the runner config. Tokens stay in environment variables or ignored local config files and are never passed as CLI arguments.

`qoder-run` is the CLI product from [Mappedinfo/qoder-agent-runner](https://github.com/Mappedinfo/qoder-agent-runner). It remains the reusable Qoder adapter/config home. Normal projects should rely on the system registry instead of hard-coding local paths in `project.yaml`. Academic Harness discovers the runner/config in this order:

1. Project `qoder.runner_command`, only when explicitly set as an override
2. User registry `~/.config/mappedinfo/qoder-agent-runner.json`
3. `qoder-run` on `PATH`
4. Nearby local `qoder-agent-runner` build folders

## CLI

```bash
uv run academic-harness init /path/to/project
uv run academic-harness project status --project /path/to/project --json
uv run academic-harness qoder discover --project /path/to/project --json
uv run academic-harness qoder install --project /path/to/project
uv run academic-harness project reset-qoder --project /path/to/project
uv run academic-harness project set-lan --project /path/to/project --enabled true --server lab-gpu-01 --project-root /data/projects/demo --ssh-alias lab-gpu-01
uv run academic-harness task run /path/to/project/tasks/sample_task.yaml --adapter fake
uv run academic-harness task run /path/to/project/tasks/sample_local_control.yaml --adapter auto
uv run academic-harness task run /path/to/project/tasks/sample_cloud_experiment.yaml --adapter qoder_cloud
uv run academic-harness runs list --project /path/to/project
uv run academic-harness run show run_YYYYMMDD-HHMMSS --project /path/to/project
uv run academic-harness validate run_YYYYMMDD-HHMMSS --project /path/to/project
```

Executors:

- `fake`: offline fixture path for UI and validator checks.
- `local_control`: local control-plan run; no remote AI agent is started.
- `qoder`: compatibility path through the registered `qoder-run` CLI.
- `qoder_cloud`: native Qoder Cloud session path for full-cloud runs.
- `auto`: chooses from the task schema, for example `cloud_experiment + mode: full_cloud` uses `qoder_cloud`.

Default projects keep the `qoder` block minimal:

```yaml
qoder:
  profile: default
```

Only use project-level overrides when a project intentionally needs a non-default runner/config:

```yaml
qoder:
  runner_command: qoder-run
  config: /path/to/ignored/config.local.json
  profile: default
```

To install from the GitHub repo instead of a nearby local checkout, use:

```bash
uv run academic-harness qoder install --project /path/to/project --repo https://github.com/Mappedinfo/qoder-agent-runner.git
```

`qoder install` registers the runner by default and does not write machine-specific paths into `project.yaml`. Add `--write-project` only when you deliberately want project-local overrides.

Run outputs are written under `.workbench/runs/<run_id>/`. Qoder raw output is kept under `.workbench/runs/<run_id>/qoder/`; normalized `report.md`, `summary.md`, artifacts, raw events, and validator results are indexed in `manifest.json`.

## macOS App

The SwiftUI shell is in `macos/AcademicHarnessApp`. It reads project files and invokes a bundled `academic-harness` CLI launcher from the app resources; no web server or shell `PATH` setup is required for the packaged app.

```bash
./scripts/build-app.sh
```

The app supports project creation, project/Qoder/task/run/LAN status checks, task YAML editing, prompt Markdown editing, explicit `Fake 测试`, `本地把控`, `全云端`, and `Qoder CLI` actions, run file browsing, and LAN worker configuration. LAN worker execution is still configuration/check only.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests
```
