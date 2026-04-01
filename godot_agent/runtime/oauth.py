# godot_agent/runtime/oauth.py
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode, urlparse, parse_qs

import httpx

# OpenAI OAuth endpoints (from Codex CLI JWT analysis)
AUTH_URL = "https://auth.openai.com/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"  # Codex public client ID
REDIRECT_PORT = 8756
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"
SCOPES = "openid profile email offline_access"

AUTH_STORE_PATH = Path.home() / ".config" / "god-code" / "auth.json"


def _generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth callback."""
    authorization_code: str | None = None
    state_received: str | None = None

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/callback":
            code = params.get("code", [None])[0]
            state = params.get("state", [None])[0]
            error = params.get("error", [None])[0]

            if error:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f"Authentication failed: {error}".encode())
            elif code:
                _OAuthCallbackHandler.authorization_code = code
                _OAuthCallbackHandler.state_received = state
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"""<html><body style="font-family:monospace;text-align:center;padding:60px">
                    <h1>God Code - Login Successful</h1>
                    <p>You can close this window and return to the terminal.</p>
                    </body></html>""")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing authorization code")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress HTTP server logs


def login() -> dict:
    """Run the full OAuth + PKCE browser login flow. Returns token dict."""
    verifier, challenge = _generate_pkce()
    state = secrets.token_urlsafe(32)

    # Reset handler state
    _OAuthCallbackHandler.authorization_code = None
    _OAuthCallbackHandler.state_received = None

    # Start local callback server
    server = HTTPServer(("localhost", REDIRECT_PORT), _OAuthCallbackHandler)
    thread = Thread(target=server.handle_request, daemon=True)
    thread.start()

    # Build authorization URL
    auth_params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "audience": "https://api.openai.com/v1",
    }
    auth_url = f"{AUTH_URL}?{urlencode(auth_params)}"

    print(f"Opening browser for login...")
    print(f"If browser doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    # Wait for callback
    thread.join(timeout=120)
    server.server_close()

    code = _OAuthCallbackHandler.authorization_code
    if not code:
        raise RuntimeError("Login timed out or failed — no authorization code received.")

    if _OAuthCallbackHandler.state_received != state:
        raise RuntimeError("OAuth state mismatch — possible CSRF attack.")

    # Exchange code for tokens
    token_data = _exchange_code(code, verifier)
    _save_tokens(token_data)
    return token_data


def _exchange_code(code: str, verifier: str) -> dict:
    """Exchange authorization code for access + refresh tokens."""
    with httpx.Client(timeout=30) as client:
        resp = client.post(TOKEN_URL, data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        })
        resp.raise_for_status()
        return resp.json()


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
    """Save tokens to ~/.config/god-code/auth.json."""
    AUTH_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    store = {
        "access_token": token_data.get("access_token", ""),
        "refresh_token": token_data.get("refresh_token", ""),
        "id_token": token_data.get("id_token", ""),
        "expires_at": time.time() + token_data.get("expires_in", 3600),
        "last_refresh": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    AUTH_STORE_PATH.write_text(json.dumps(store, indent=2))
    # Secure the file
    AUTH_STORE_PATH.chmod(0o600)
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
        except Exception:
            return None

    return None


def load_codex_auth() -> str | None:
    """Fallback: try reading from Codex CLI cache at ~/.codex/auth.json."""
    codex_path = Path.home() / ".codex" / "auth.json"
    if not codex_path.exists():
        return None
    try:
        data = json.loads(codex_path.read_text())
        tokens = data.get("tokens", {})
        return tokens.get("access_token")
    except (json.JSONDecodeError, KeyError):
        return None
