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

The SwiftUI shell is in `macos/AcademicHarnessApp`. It reads project files and invokes the installed `academic-harness` CLI; no web server is required.

```bash
./scripts/build-app.sh
```

## Tests

```bash
python -m unittest discover -s tests
```

