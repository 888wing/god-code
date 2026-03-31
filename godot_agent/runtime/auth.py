from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AuthContext:
    api_key: str | None = None
    oauth_token: str | None = None

    @property
    def bearer_token(self) -> str:
        return self.oauth_token or self.api_key or ""

    @property
    def is_authenticated(self) -> bool:
        return bool(self.bearer_token)


def resolve_auth(api_key: str = "", oauth_token: str | None = None) -> AuthContext:
    return AuthContext(api_key=api_key, oauth_token=oauth_token)
