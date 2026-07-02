# Mappedinfo Academic Harness

Local-first research harness for project-scoped tasks, Qoder runs, artifacts, and validators.

V1 keeps the loop small:

```text
Project -> Task -> Qoder/Fake Run -> Artifacts -> Validator Report
```

The Qoder domestic endpoint remains `https://api.qoder.com.cn/api/v1/cloud` in the runner config. This harness invokes a local `qoder-run` executable and never passes tokens in CLI arguments.

## CLI

```bash
uv run academic-harness init /path/to/project
uv run academic-harness project status --project /path/to/project --json
uv run academic-harness project set-lan --project /path/to/project --enabled true --server lab-gpu-01 --project-root /data/projects/demo --ssh-alias lab-gpu-01
uv run academic-harness task run /path/to/project/tasks/sample_task.yaml --adapter fake
uv run academic-harness runs list --project /path/to/project
uv run academic-harness run show run_YYYYMMDD-HHMMSS --project /path/to/project
uv run academic-harness validate run_YYYYMMDD-HHMMSS --project /path/to/project
```

Live Qoder runs use the project `qoder` block:

```yaml
qoder:
  runner_command: qoder-run
  config: ../qoder-agent-runner/config.local.json
  profile: default
```

Run outputs are written under `.workbench/runs/<run_id>/`.

## macOS App

The SwiftUI shell is in `macos/AcademicHarnessApp`. It reads project files and invokes a bundled `academic-harness` CLI launcher from the app resources; no web server or shell `PATH` setup is required for the packaged app.

```bash
./scripts/build-app.sh
```

The app supports project creation, project/Qoder/task/run/LAN status checks, task YAML editing, prompt Markdown editing, explicit `Run Fake` and `Run Qoder` actions, run file browsing, and LAN worker configuration. Qoder is still the only live AI execution backend in v1; LAN worker execution is configuration/check only.

## Tests

```bash
python -m unittest discover -s tests
```
