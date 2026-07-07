---
name: academic-run-task
description: Run Academic Harness tasks through the kernel, then inspect manifest, artifacts, validators, and trace.
---

# Academic Run Task

Use this skill when the user wants to run an Academic Harness task, check whether a project is ready, or understand a run result.

Workflow:

1. Call `academic_project_status` for the project.
2. Call `academic_list_tasks` if the task path or task id is unclear.
3. Call `academic_run_task` with the selected task and adapter. Default to `auto` unless the user explicitly asks for `fake`, `qoder_cloud`, `lan`, `hybrid`, or another supported adapter.
4. If the run is not `passed`, call `academic_read_trace` and summarize the kernel reason.
5. If the run passed, call `academic_show_run` and report the main `report.md`, `summary.md`, artifact count, and validator state.

Rules:

- Never bypass Academic Harness policy by calling Qoder, SSH, Python experiment commands, or validators directly.
- `blocked`, `awaiting_approval`, `failed`, and validator failures are kernel outcomes. Explain them; do not reinterpret them as success.
- Do not print secrets, token values, or local API keys.
