---
name: qoder-cloud-experiment
description: Prepare or run Qoder Cloud research and Academic Harness LAN experiment tasks without bypassing kernel policy.
---

# Qoder Cloud Experiment

Use this skill for cloud research, deep search, Qoder managed-agent tasks, or research that leads into LAN experiments.

Default routing:

- Non-experiment research or decision work: use `academic_run_task` with `adapter: "qoder_cloud"` unless the task already specifies another adapter.
- LAN experiment work: use the Academic Harness task schema and run through `adapter: "auto"` or the project-approved experiment adapter. Do not directly execute cloud-generated shell commands.

Cloud/LAN boundary:

- Qoder Cloud may generate research reports, task plans, and experiment specifications.
- Academic Harness validates policy, state, artifacts, and expected outputs.
- LAN execution must go through the Academic Harness executor so data download and compute happen inside the configured LAN worker/container.

Safety:

- Do not pass Qoder PAT, local AI keys, or SSH credentials as tool arguments.
- Do not replace Qoder managed agents with Pi subagents in P0.
