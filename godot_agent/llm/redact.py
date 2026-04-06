"""Secret redaction helper for log output and error messages.

Use this whenever a string that *might* contain a provider response,
upstream error body, or raw HTTP fragment is about to be handed to the
logging system. It is defense-in-depth: our own code does not deliberately
log credentials, but proxies and custom providers can echo Authorization
headers or request bodies in error responses.
"""
from __future__ import annotations

import re

# Matches common credential shapes we might see in-flight:
#   - OpenAI-style keys:   sk-..., sk-proj-..., sk-live-...
#   - Anthropic keys:      sk-ant-...
#   - god-code platform:   gc_live_...
#   - Bearer tokens:       "Authorization: Bearer XYZ"
#   - Generic JWTs:        eyJ... (three base64url segments separated by dots)
# Order matters: Bearer is checked first so it swallows the whole token
# in one replacement (including tokens that contain `_` like gc_live_ keys),
# otherwise the inner token pattern matches first and leaves "Bearer [REDACTED]"
# plus a second replacement fragment.
_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"), "Bearer [REDACTED]"),
    (re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), "sk-[REDACTED]"),
    (re.compile(r"gc_live_[A-Za-z0-9]{20,}"), "gc_live_[REDACTED]"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"), "[REDACTED_JWT]"),
)


def redact_secrets(text: str) -> str:
    """Return *text* with any credential-shaped substrings replaced."""
    if not text:
        return text
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text
