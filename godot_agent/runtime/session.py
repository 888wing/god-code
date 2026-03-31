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
