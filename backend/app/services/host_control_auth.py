from __future__ import annotations

import secrets
import threading

_LOCK = threading.RLock()
_TOKENS: dict[str, str] = {}


def issue_host_token(debate_id: str) -> str:
    token = secrets.token_urlsafe(24)
    with _LOCK:
        _TOKENS[debate_id] = token
    return token


def verify_host_token(debate_id: str, token: str | None) -> bool:
    if not token:
        return False
    with _LOCK:
        expected = _TOKENS.get(debate_id)
    return bool(expected) and secrets.compare_digest(expected, token)
