# Mappedinfo Academic Harness

Local-first research harness for project-scoped tasks, Qoder runs, artifacts, validators, and cloud experiment control.

Current scope is a v0.3 candidate harness: executors can run, policy can block, state is explicit, artifacts are registered, validators decide pass/fail, and trace files make each run inspectable.

```text
Project
-> Task
-> Policy Gate
-> State Machine
-> Executor
-> Artifact Registry
-> Artifact + Local Validators
-> Run Manifest + Trace
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
uv run academic-harness project set-local-ai --project /path/to/project --enabled true --provider openai_compatible --base-url https://api.longcat.chat/openai --model LongCat-2.0 --api-key-env LONG_CAT_API_KEY --env-file /path/to/ignored/.env --transport auto
uv run academic-harness project set-lan --project /path/to/project --enabled true --server lab-gpu-01 --project-root /data/projects/demo --ssh-alias lab-gpu-01
uv run academic-harness task list --project /path/to/project --json
uv run academic-harness task run /path/to/project/tasks/sample_task.yaml --adapter fake
uv run academic-harness task run /path/to/project/tasks/sample_task.yaml --adapter fake --json
uv run academic-harness task run /path/to/project/tasks/sample_local_control.yaml --adapter auto
uv run academic-harness task run /path/to/project/tasks/sample_lan_traffic_experiment.yaml --adapter lan
uv run academic-harness task run /path/to/project/tasks/sample_cloud_experiment.yaml --adapter qoder_cloud
uv run academic-harness task run /path/to/project/tasks/sample_cloud_experiment.yaml --adapter qoder_cloud --managed-agents on --managed-agent-count 4 --delegation-strategy agent_sync
uv run academic-harness task run /path/to/project/tasks/sample_cloud_experiment.yaml --adapter hybrid
uv run academic-harness runs list --project /path/to/project
uv run academic-harness run show run_YYYYMMDD-HHMMSS --project /path/to/project
uv run academic-harness run trace run_YYYYMMDD-HHMMSS --project /path/to/project --json
uv run academic-harness run link-pi run_YYYYMMDD-HHMMSS --project /path/to/project --pi-session-id SESSION --pi-entry-id ENTRY
uv run academic-harness validate run_YYYYMMDD-HHMMSS --project /path/to/project --json
```

Executors:

- `fake`: offline fixture path for UI and validator checks.
- `local_control`: local control-plan run; no remote AI agent is started.
- `lan`: SSH-based LAN experiment run; uploads only task specs, prompt text, and variable metadata, keeps source data remote, and collects reports plus lightweight registries.
- `hybrid`: local AI preflight and postflight around a Qoder Cloud execution.
- `qoder`: compatibility path through the registered `qoder-run` CLI.
- `qoder_cloud`: native Qoder Cloud session path for full-cloud runs.
- `auto`: chooses from the task schema, for example `cloud_experiment + mode: full_cloud` uses `qoder_cloud`.

Harness kernel:

- `policy_gate`: preflight blocks missing Qoder/local AI config, private path leakage into cloud mode, agent-count limit violations, and explicit artifact-delivery contract gaps. It returns `allow`, `deny`, or `ask`; non-interactive CLI runs stop at `blocked` or `awaiting_approval`.
- `state_machine`: each run records `created`, `policy_checking`, `approved`, `executing`, `streaming`, `collecting_artifacts`, `validating`, and final states in `manifest.json`.
- `trace_writer`: every state/policy transition is appended to `.workbench/runs/<run_id>/trace.jsonl`.
- `artifact_registry`: normalized files are written to `.workbench/runs/<run_id>/artifacts.json` and copied into the run manifest.
- `artifact_contract` validator: required outputs from `output.expected` and `expected_artifacts` are checked before local validator scripts run.

Full-cloud deep search uses Qoder managed agents by default for `cloud_experiment` and `deep_search` tasks. Academic Harness creates a persistent local roster under `.workbench/qoder_agents.json`: one coordinator plus 2-4 worker agents. The first run creates or updates the roster; later runs reuse it when the config has not changed.

Optional project-level defaults:

```yaml
qoder:
  profile: default
  network_mode: auto  # auto | direct | system
  managed_agents:
    enabled: true
    mode: persistent
    delegation_strategy: agent_sync  # agent_sync | child_threads
    include_self: false
    total_agents: 4
    model: ""  # leave empty to auto-select an enabled Qoder model for this account
    agent_set_name: deep_search
    require_managed_agents: false
```

Use `--managed-agents off` for a single-agent cloud run, `--delegation-strategy child_threads` for the older child-thread polling style, or `--require-managed-agents` when fallback to the base agent should be treated as a failure.

Hybrid AI adds a local controller/reviewer around the cloud run:

```yaml
local_ai:
  enabled: true
  provider: openai_compatible
  base_url: https://api.longcat.chat/openai
  model: LongCat-2.0
  api_key_env: LONG_CAT_API_KEY
  env_file: /path/to/ignored/.env
  timeout_seconds: 120
  transport: auto
qoder:
  profile: default
  network_mode: auto
  managed_agents:
    enabled: true
    delegation_strategy: agent_sync
    include_self: false
    total_agents: 4
    model: ""  # leave empty to auto-select an enabled Qoder model for this account
```

The default development local AI backend is LongCat's OpenAI-compatible API. Academic Harness reads `LONG_CAT_API_URL`, `LONG_CAT_API_KEY`, and `LONG_CAT_MODEL` from the process environment, `local_ai.env_file`, the project `.env`, or the repo `.env`; secret values are never written to metadata. If these variables are absent, the generic defaults are `https://api.longcat.chat/openai`, `LONG_CAT_API_KEY`, and `LongCat-2.0`.

The packaged macOS app runs the bundled CLI from inside `AcademicHarness.app`, so it cannot infer the source-repo `.env` unless `local_ai.env_file` is set or the project has its own `.env`. The UI exposes this as `Settings -> 本地 AI Backend -> Env File`; this field stores only a file path, not the API key.

The Qoder and local AI HTTP clients default to direct-first networking. Qoder uses `qoder.network_mode: auto`: it first disables app-level proxies; if direct hostname resolution/connectivity fails, it falls back to system networking so a run can still complete. Set `direct` for strict no-proxy behavior, or `system` when you intentionally want macOS proxy/VPN/TUN routing.

The local AI HTTP client uses `local_ai.transport: auto`: it first uses native `urllib` with an empty proxy handler; if the Python resolver cannot resolve the direct target, it falls back to `curl` with `noproxy=*`. `HTTP_PROXY`, `HTTPS_PROXY`, and `ALL_PROXY` are ignored by the direct paths. None of this can bypass a system-level transparent TUN/VPN route when macOS itself captures traffic; configure direct rules in Clash/Sing-box/etc. for `api.longcat.chat` and `qoder.com.cn` if needed.

Typical direct-rule intent:

```text
DOMAIN,api.longcat.chat,DIRECT
DOMAIN-SUFFIX,longcat.chat,DIRECT
DOMAIN-SUFFIX,qoder.com.cn,DIRECT
```

Strict direct mode also needs a DNS path that can resolve these domains outside the proxy. If `project status --check-local-ai` reports `direct/no-proxy DNS failed`, the harness is already bypassing app-level proxies and the remaining fix belongs in the TUN/DNS client. If Qoder metadata shows `network_mode=auto` and `network_mode_effective=system`, direct networking failed and the runner used the system network fallback.

The local AI backend uses the OpenAI-compatible chat-completions shape for `openai_compatible`, `ollama`, and `vllm`. LongCat's base URL is `https://api.longcat.chat/openai`; the direct HTTP endpoint used by the harness is `https://api.longcat.chat/openai/v1/chat/completions`, matching LongCat's cURL example. If `api_key_env` is set and the environment variable is absent, status reports a warning but no secret value is written to metadata. In `hybrid` mode, local AI first writes advisory preflight outputs under `local_ai/`: `preflight.json`, `prompt_review.md`, `cloud_prompt.md`, `risk_report.md`, `prompt_patch.md`, and `policy_warnings.json`. Qoder then writes raw cloud outputs under `qoder/`. Local AI postflight writes advisory review outputs: `review.md`, `audit_report.md`, `artifact_summary.md`, `suspected_issues.json`, `final_report.md`, and top-level `report.md`. Final pass/fail still comes from artifact/local validators plus policy, not from the local AI text.

Default projects keep the `qoder` block non-secret and portable:

```yaml
qoder:
  profile: default
  network_mode: auto
  managed_agents:
    enabled: true
    delegation_strategy: agent_sync
    include_self: false
    total_agents: 4
    model: ""
    require_managed_agents: false
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

Run outputs are written under `.workbench/runs/<run_id>/`. Qoder raw output is kept under `.workbench/runs/<run_id>/qoder/`; normalized `report.md`, `summary.md`, artifacts, raw events, and validator results are indexed in `manifest.json`. Managed-agent cloud runs also write `qoder/threads.json` and `qoder/delegations.jsonl` when thread events are present.

## macOS App

The SwiftUI shell is in `macos/AcademicHarnessApp`. It reads project files and invokes a bundled `academic-harness` CLI launcher from the app resources; no web server or shell `PATH` setup is required for the packaged app.

```bash
./scripts/build-app.sh
```

The app remains a local project/run browser and report launcher. Pi is the preferred local agent conversation shell for task selection, run explanation, and validator review. LAN worker execution is remote-data-only by default: local runs collect reports and lightweight registries, not raw datasets.

## Pi Integration

`integrations/pi/` contains a local Pi package named `@mappedinfo/pi-academic-harness`. It exposes Academic Harness as Pi tools and commands while keeping policy, state, executors, artifacts, validators, and traces in the Python kernel.

```bash
cd integrations/pi
npm install
npm run pi:install
# or for development without installing
npm run pi:dev
```

The Pi CLI is provided by the package dependency `@earendil-works/pi-coding-agent`, so a global `pi` command is not required. If a global `pi` command already exists, `pi install ./integrations/pi` also works.

Tools:

- `academic_project_status`
- `academic_list_tasks`
- `academic_run_task`
- `academic_show_run`
- `academic_validate_run`
- `academic_read_trace`

Commands:

- `/ah-status`
- `/ah-run`
- `/ah-show`
- `/ah-validate`
- `/ah-trace`
- `/ah-qoder-cloud`

The Pi extension calls the CLI with argument arrays and never passes Qoder PAT or local AI API key values in command arguments.

Pi TUI integration:

- Tool results and slash-command messages use a custom renderer that shows run id, state, policy decisions, validator statuses, and artifact paths.
- Run-producing commands/tools automatically call `academic-harness run link-pi ...` so `manifest.json` records:

```json
{
  "pi": {
    "run_id": "...",
    "pi_session_id": "...",
    "pi_entry_id": "...",
    "pi_session_file": "...",
    "linked_at": "..."
  }
}
```

The link is audit metadata only. Kernel pass/fail remains controlled by policy and validators.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests
cd integrations/pi && npm run typecheck
```
