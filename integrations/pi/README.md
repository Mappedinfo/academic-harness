# Pi Academic Harness Integration

This package makes Pi a local agent shell for Academic Harness. Pi owns the conversation, commands, and tool surface. Academic Harness remains the kernel for policy, state, executors, artifact registry, validators, manifests, and traces.

## Install Locally

If `pi` is not installed globally, use the package-local CLI installed through `npm install`:

```bash
cd integrations/pi
npm install
npm run pi:help
```

To register this package in the current user's Pi config:

```bash
cd integrations/pi
npm run pi:install
```

For project-local registration from `integrations/pi/.pi/settings.json`:

```bash
cd integrations/pi
npm run pi:install-local
```

For development without installing, run the extension file directly:

```bash
cd integrations/pi
npm run pi:dev
```

If a global `pi` command is available, this is equivalent:

```bash
pi install ./integrations/pi
pi -e ./integrations/pi/extensions/academic-harness.ts
```

If the `academic-harness` CLI is not on `PATH`, set:

```bash
export ACADEMIC_HARNESS_CLI=/absolute/path/to/academic-harness
```

When this package is used from the source repository, the extension also tries:

```bash
uv run --project <repo-root> academic-harness ...
```

## Tools

- `academic_project_status(project)`
- `academic_list_tasks(project)`
- `academic_run_task(project, task, adapter?)`
- `academic_show_run(project, run_id)`
- `academic_validate_run(project, run_id)`
- `academic_read_trace(project, run_id)`

All tools call Academic Harness CLI commands with argument arrays. They do not pass tokens or local AI API keys through command arguments.

## Boundary

Do not move kernel decisions into Pi. Pi may explain a run, but pass/fail remains the result of Academic Harness policy, artifact contracts, and validators.
