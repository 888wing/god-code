# godot_agent/runtime/oauth.py
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import httpx

import logging
import os

log = logging.getLogger(__name__)

TOKEN_URL = os.environ.get("GODOT_AGENT_OAUTH_TOKEN_URL", "https://auth.openai.com/oauth/token")
CLIENT_ID = os.environ.get("GODOT_AGENT_OAUTH_CLIENT_ID", "app_EMoamEEZ73f0CkXaXp7hrann")
CODEX_AUTH_PATH = Path.home() / ".codex" / "auth.json"
AUTH_STORE_PATH = Path.home() / ".config" / "god-code" / "auth.json"


def login() -> dict:
    """Login by refreshing the Codex CLI's refresh_token.

    Requires: user has previously run `codex login` in their terminal.
    We borrow the refresh_token from ~/.codex/auth.json and exchange it
    for a fresh access_token via OpenAI's token endpoint.
    """
    refresh_token = _read_codex_refresh_token()
    if not refresh_token:
        raise RuntimeError(
            "No Codex credentials found. Run 'codex login' in your terminal first, "
            "then retry 'god-code login'."
        )

    token_data = refresh_access_token(refresh_token)
    # Preserve refresh_token for future use
    if "refresh_token" not in token_data:
        token_data["refresh_token"] = refresh_token
    _save_tokens(token_data)
    return token_data


def _read_codex_refresh_token() -> str | None:
    """Read refresh_token from Codex CLI's auth cache."""
    if not CODEX_AUTH_PATH.exists():
        return None
    try:
        data = json.loads(CODEX_AUTH_PATH.read_text())
        return data.get("tokens", {}).get("refresh_token")
    except (json.JSONDecodeError, KeyError):
        return None


def refresh_access_token(refresh_token: str) -> dict:
    """Use refresh token to get a new access token."""
    with httpx.Client(timeout=30) as client:
        resp = client.post(TOKEN_URL, data={
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "refresh_token": refresh_token,
        })
        resp.raise_for_status()
        return resp.json()


def _save_tokens(token_data: dict) -> Path:
    """Save tokens to ~/.config/god-code/auth.json atomically with 0o600."""
    AUTH_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    store = {
        "access_token": token_data.get("access_token", ""),
        "refresh_token": token_data.get("refresh_token", ""),
        "id_token": token_data.get("id_token", ""),
        "expires_at": time.time() + token_data.get("expires_in", 3600),
        "last_refresh": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    # Atomic write: tempfile + fchmod + rename so the file never exists on
    # disk with umask-default permissions, even briefly.
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=f".{AUTH_STORE_PATH.name}.",
        suffix=".tmp",
        dir=str(AUTH_STORE_PATH.parent),
    )
    try:
        os.fchmod(tmp_fd, 0o600)
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(store, f, indent=2)
        os.replace(tmp_name, AUTH_STORE_PATH)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return AUTH_STORE_PATH


def load_stored_token() -> str | None:
    """Load access token from store, auto-refresh if expired."""
    if not AUTH_STORE_PATH.exists():
        return None
    try:
        store = json.loads(AUTH_STORE_PATH.read_text())
    except (json.JSONDecodeError, KeyError):
        return None

    access_token = store.get("access_token")
    refresh_token = store.get("refresh_token")
    expires_at = store.get("expires_at", 0)

    # If token is still valid (with 60s buffer), use it
    if access_token and time.time() < expires_at - 60:
        return access_token

    # Try to refresh
    if refresh_token:
        try:
            new_tokens = refresh_access_token(refresh_token)
            # Preserve existing refresh_token if not returned
            if "refresh_token" not in new_tokens:
                new_tokens["refresh_token"] = refresh_token
            _save_tokens(new_tokens)
            return new_tokens.get("access_token")
        except Exception as e:
            log.warning("Token refresh failed: %s", e)
            return None

    return None


def load_codex_auth() -> str | None:
    """Fallback: refresh from Codex CLI's refresh_token at ~/.codex/auth.json."""
    refresh_token = _read_codex_refresh_token()
    if not refresh_token:
        return None
    try:
        token_data = refresh_access_token(refresh_token)
        if "refresh_token" not in token_data:
            token_data["refresh_token"] = refresh_token
        _save_tokens(token_data)
        return token_data.get("access_token")
    except Exception as e:
        log.warning("Codex token refresh failed: %s", e)
        return None
