from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..timeutil import utc_now_iso


class TraceWriter:
    def __init__(self, run_dir: Path, run_id: str) -> None:
        self.run_dir = run_dir
        self.run_id = run_id
        self.path = run_dir / "trace.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event_type: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        event = {
            "ts": utc_now_iso(),
            "run_id": self.run_id,
            "type": event_type,
            "data": data or {},
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        return event


def write_qoder_thread_trace(run_id: str, qoder_dir: Path, thread_events: list[dict[str, Any]]) -> dict[str, Any]:
    threads: dict[str, dict[str, Any]] = {}
    delegations: dict[str, dict[str, Any]] = {}

    for event in thread_events:
        event_type = str(event.get("type") or "")
        processed_at = event.get("processed_at")
        if event_type == "session.thread_created":
            thread_id = _thread_id(event)
            if thread_id:
                thread = threads.setdefault(thread_id, {"session_thread_id": thread_id})
                thread["agent_name"] = event.get("agent_name")
                thread["status"] = "created"
                thread["created_at"] = processed_at
            continue

        if event_type == "session.thread_status_running":
            thread_id = _thread_id(event)
            if thread_id:
                thread = threads.setdefault(thread_id, {"session_thread_id": thread_id})
                thread["agent_name"] = event.get("agent_name")
                thread["status"] = "running"
                thread["last_status_at"] = processed_at
            continue

        if event_type == "session.thread_status_idle":
            thread_id = _thread_id(event)
            if thread_id:
                thread = threads.setdefault(thread_id, {"session_thread_id": thread_id})
                thread["agent_name"] = event.get("agent_name")
                thread["status"] = "idle"
                thread["finished_at"] = processed_at
                delegation = delegations.get(thread_id)
                if delegation:
                    delegation["status"] = "idle"
                    delegation["finished_at"] = processed_at
            continue

        if event_type == "agent.thread_message_sent":
            thread_id = str(event.get("to_session_thread_id") or event.get("session_thread_id") or "")
            if thread_id:
                thread = threads.setdefault(thread_id, {"session_thread_id": thread_id})
                thread["agent_name"] = event.get("to_agent_name") or thread.get("agent_name")
                thread["status"] = thread.get("status") or "dispatched"
                delegation = delegations.setdefault(
                    thread_id,
                    {
                        "run_id": run_id,
                        "child_thread_id": thread_id,
                        "status": "dispatched",
                    },
                )
                delegation["agent_name"] = event.get("to_agent_name") or delegation.get("agent_name")
                delegation["task_excerpt"] = event.get("text_excerpt")
                delegation["started_at"] = processed_at
            continue

        if event_type == "agent.thread_message_received":
            thread_id = str(event.get("from_session_thread_id") or event.get("session_thread_id") or "")
            if thread_id:
                thread = threads.setdefault(thread_id, {"session_thread_id": thread_id})
                thread["agent_name"] = event.get("from_agent_name") or thread.get("agent_name")
                thread["last_reply_at"] = processed_at
                delegation = delegations.setdefault(
                    thread_id,
                    {
                        "run_id": run_id,
                        "child_thread_id": thread_id,
                    },
                )
                delegation["agent_name"] = event.get("from_agent_name") or delegation.get("agent_name")
                delegation["result_excerpt"] = event.get("text_excerpt")
                delegation["status"] = delegation.get("status") or "received"
                delegation["finished_at"] = processed_at

    threads_path = qoder_dir / "threads.json"
    delegations_path = qoder_dir / "delegations.jsonl"
    threads_payload = {
        "run_id": run_id,
        "threads": sorted(threads.values(), key=lambda item: str(item.get("session_thread_id") or "")),
    }
    threads_path.write_text(json.dumps(threads_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with delegations_path.open("w", encoding="utf-8") as stream:
        for delegation in sorted(delegations.values(), key=lambda item: str(item.get("child_thread_id") or "")):
            stream.write(json.dumps(delegation, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "threads_path": str(threads_path),
        "delegations_path": str(delegations_path),
        "thread_count": len(threads),
        "delegation_count": len(delegations),
    }


def _thread_id(event: dict[str, Any]) -> str:
    return str(event.get("session_thread_id") or event.get("thread_id") or event.get("id") or "")
