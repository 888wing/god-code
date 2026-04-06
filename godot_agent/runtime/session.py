from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from godot_agent.llm.client import Message


@dataclass
class SessionRecord:
    session_id: str
    timestamp: float
    messages: list[Message]
    message_count: int
    project_path: str | None = None
    project_name: str | None = None
    model: str | None = None
    mode: str | None = None
    skill_mode: str | None = None
    enabled_skills: list[str] = field(default_factory=list)
    disabled_skills: list[str] = field(default_factory=list)
    active_skills: list[str] = field(default_factory=list)
    gameplay_intent: dict[str, Any] = field(default_factory=dict)
    title: str = ""
    summary: str = ""
    changeset_read: list[str] = field(default_factory=list)
    changeset_modified: list[str] = field(default_factory=list)
    completed_steps: list[str] = field(default_factory=list)
    last_plan: dict[str, Any] | None = None


def _session_title(messages: list[Message]) -> str:
    for message in messages:
        if message.role == "user" and isinstance(message.content, str) and not message.content.startswith("[SYSTEM]"):
            return message.content.strip().splitlines()[0][:80]
    return "Untitled session"


def _session_summary(messages: list[Message]) -> str:
    for message in reversed(messages):
        if message.role == "assistant" and isinstance(message.content, str) and message.content.strip():
            return message.content.strip().splitlines()[0][:120]
    return ""


def save_session(
    session_dir: str,
    session_id: str,
    messages: list[Message],
    *,
    project_path: str | None = None,
    project_name: str | None = None,
    model: str | None = None,
    mode: str | None = None,
    skill_mode: str | None = None,
    enabled_skills: list[str] | None = None,
    disabled_skills: list[str] | None = None,
    active_skills: list[str] | None = None,
    gameplay_intent: dict[str, Any] | None = None,
    changeset_read: list[str] | None = None,
    changeset_modified: list[str] | None = None,
    completed_steps: list[str] | None = None,
    last_plan: dict[str, Any] | None = None,
) -> Path:
    """Persist conversation messages to a JSON file on disk.

    Creates the session directory if it does not exist.  Returns the
    path to the written file.
    """
    dir_path = Path(session_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / f"{session_id}.json"
    timestamp = time.time()
    data = {
        "session_id": session_id,
        "timestamp": timestamp,
        "project_path": project_path,
        "project_name": project_name,
        "model": model,
        "mode": mode,
        "skill_mode": skill_mode,
        "enabled_skills": list(enabled_skills or []),
        "disabled_skills": list(disabled_skills or []),
        "active_skills": list(active_skills or []),
        "gameplay_intent": dict(gameplay_intent or {}),
        "changeset_read": list(changeset_read or []),
        "changeset_modified": list(changeset_modified or []),
        "completed_steps": list(completed_steps or []),
        "last_plan": last_plan,
        "message_count": len(messages),
        "title": _session_title(messages),
        "summary": _session_summary(messages),
        "messages": [m.to_dict() for m in messages],
    }
    file_path.write_text(json.dumps(data, indent=2))
    return file_path


def _record_from_data(data: dict, fallback_session_id: str = "") -> SessionRecord:
    session_id = data.get("session_id", fallback_session_id)
    raw_messages = data.get("messages", [])
    messages = [Message.from_dict(m) for m in raw_messages]
    return SessionRecord(
        session_id=session_id,
        timestamp=float(data.get("timestamp", 0)),
        messages=messages,
        message_count=int(data.get("message_count", len(messages))),
        project_path=data.get("project_path"),
        project_name=data.get("project_name"),
        model=data.get("model"),
        mode=data.get("mode"),
        skill_mode=data.get("skill_mode"),
        enabled_skills=list(data.get("enabled_skills") or []),
        disabled_skills=list(data.get("disabled_skills") or []),
        active_skills=list(data.get("active_skills") or []),
        gameplay_intent=dict(data.get("gameplay_intent") or {}),
        title=data.get("title") or _session_title(messages),
        summary=data.get("summary") or _session_summary(messages),
        changeset_read=list(data.get("changeset_read") or []),
        changeset_modified=list(data.get("changeset_modified") or []),
        completed_steps=list(data.get("completed_steps") or []),
        last_plan=data.get("last_plan"),
    )


def load_session(session_dir: str, session_id: str) -> SessionRecord | None:
    """Load a previously saved session. Returns None when the file does not exist."""
    file_path = Path(session_dir) / f"{session_id}.json"
    if not file_path.exists():
        return None
    data = json.loads(file_path.read_text())
    return _record_from_data(data, fallback_session_id=session_id)


def load_latest_session(session_dir: str, project_path: str | None = None) -> SessionRecord | None:
    """Load the most recent session, optionally filtered to a project path."""
    sessions = list_sessions(session_dir, project_path=project_path, limit=1)
    if not sessions:
        return None
    return sessions[0]


def list_sessions(
    session_dir: str,
    *,
    project_path: str | None = None,
    limit: int = 20,
) -> list[SessionRecord]:
    """List recent sessions sorted by most recent first."""
    dir_path = Path(session_dir)
    if not dir_path.exists():
        return []
    files = sorted(dir_path.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    records: list[SessionRecord] = []
    for file_path in files:
        try:
            data = json.loads(file_path.read_text())
            record = _record_from_data(data, fallback_session_id=file_path.stem)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
        if project_path and record.project_path != project_path:
            continue
        records.append(record)
        if len(records) >= limit:
            break
    return records
