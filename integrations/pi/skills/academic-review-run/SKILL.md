---
name: academic-review-run
description: Diagnose an existing Academic Harness run from manifest, trace, artifacts, and validators.
---

# Academic Review Run

Use this skill when the user asks why a run failed, what it produced, or whether its output is trustworthy.

Workflow:

1. Call `academic_show_run` for the run.
2. Call `academic_read_trace` for state and policy transitions.
3. Inspect `policy.preflight`, `policy.post_artifact`, `executor`, `artifacts`, and `validators`.
4. If validators failed, identify the failing validator and its report path.
5. If Qoder or LAN failed, report the executor `stop_reason` or `error`.

Review standard:

- The manifest and validators are authoritative.
- Explain only evidence present in manifest, trace, artifacts, or validator output.
- Recommend the smallest concrete fix: config, task YAML, prompt, expected artifacts, LAN settings, or Qoder config.
