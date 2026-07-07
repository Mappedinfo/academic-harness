# Strict Validator Review

Review the selected Academic Harness run as an inspector, not as a replacement judge.

Use `academic_show_run` and `academic_read_trace` first. Then inspect artifacts and validators from the manifest. Treat `manifest.status`, `policy`, and `validators` as authoritative. If the run failed, explain the first actionable kernel-level cause and the smallest next step.

Do not mark a run passed based on prose quality alone. Do not run Qoder, LAN, or shell commands directly; use Academic Harness tools.
