from __future__ import annotations

import json
import time
from pathlib import Path

from godot_agent.llm.client import Message


def save_session(
    session_dir: str, session_id: str, messages: list[Message]
) -> Path:
    """Persist conversation messages to a JSON file on disk.

    Creates the session directory if it does not exist.  Returns the
    path to the written file.
    """
    dir_path = Path(session_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / f"{session_id}.json"
    data = {
        "session_id": session_id,
        "timestamp": time.time(),
        "messages": [m.to_dict() for m in messages],
    }
    file_path.write_text(json.dumps(data, indent=2))
    return file_path


def load_session(session_dir: str, session_id: str) -> list[dict] | None:
    """Load a previously saved session.  Returns ``None`` when the file
    does not exist."""
    file_path = Path(session_dir) / f"{session_id}.json"
    if not file_path.exists():
        return None
    data = json.loads(file_path.read_text())
    return data.get("messages", [])


def load_latest_session(session_dir: str) -> tuple[str, list[Message]] | None:
    """Load the most recent session. Returns (session_id, messages) or None."""
    dir_path = Path(session_dir)
    if not dir_path.exists():
        return None
    files = sorted(dir_path.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        return None
    data = json.loads(files[0].read_text())
    session_id = data.get("session_id", files[0].stem)
    raw_messages = data.get("messages", [])
    messages: list[Message] = []
    for m in raw_messages:
        messages.append(Message(
            role=m.get("role", "user"),
            content=m.get("content"),
            tool_call_id=m.get("tool_call_id"),
        ))
    return session_id, messages
