from __future__ import annotations

from typing import Any

from ..timeutil import utc_now_iso
from .trace_writer import TraceWriter


VALID_STATES = {
    "created",
    "policy_checking",
    "approved",
    "blocked",
    "awaiting_approval",
    "executing",
    "streaming",
    "collecting_artifacts",
    "validating",
    "passed",
    "failed",
    "cancelled",
}


class RunStateMachine:
    def __init__(self, trace: TraceWriter) -> None:
        self.trace = trace
        self.current = ""
        self.history: list[dict[str, Any]] = []

    def enter(self, state: str, reason: str | None = None, **data: Any) -> dict[str, Any]:
        if state not in VALID_STATES:
            raise ValueError(f"Unsupported run state: {state}")
        entry: dict[str, Any] = {
            "state": state,
            "entered_at": utc_now_iso(),
        }
        if reason:
            entry["reason"] = reason
        if data:
            entry["data"] = data
        self.current = state
        self.history.append(entry)
        self.trace.write("state.enter", entry)
        return entry

    def apply(self, manifest: dict[str, Any]) -> None:
        manifest["state"] = self.current
        manifest["state_history"] = list(self.history)
