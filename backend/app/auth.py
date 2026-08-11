"""Shared-password gate for public deployments (D15).

One password guards the whole app; everyone who gets in shares the single-user
data, exactly as with the D14 tunnel. This is *not* multi-user auth — it stops
strangers who stumble onto the URL from editing the inventory or spending the
owner's Anthropic credits, nothing more.

Disabled entirely when FORKCAST_PASSWORD is unset, so local dev is unchanged.
"""

import base64
import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict

COOKIE = "forkcast_session"
MAX_AGE = 30 * 24 * 3600  # 30 days: this is a convenience gate, not a bank

# Brute-force blunting. In-memory, so it resets when the instance spins down —
# enough against a script hammering a random URL, which is the actual threat.
_MAX_ATTEMPTS = 10
_WINDOW = 300  # seconds
_attempts: dict[str, list[float]] = defaultdict(list)


def password() -> str | None:
    """The configured shared password, or None when the gate is off."""
    return os.environ.get("FORKCAST_PASSWORD") or None


def required() -> bool:
    return password() is not None


def _secret() -> bytes:
    """Key for signing session cookies.

    FORKCAST_SECRET_KEY keeps sessions valid across restarts — important on
    hosts that spin the instance down when idle. Without it we derive a key
    from the password, which still survives restarts but invalidates every
    session when the password is rotated (a feature).
    """
    configured = os.environ.get("FORKCAST_SECRET_KEY")
    if configured:
        return configured.encode()
    return hashlib.sha256(f"forkcast:{password()}".encode()).digest()


def _sign(payload: str) -> str:
    mac = hmac.new(_secret(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")


def issue_token() -> str:
    """A signed 'logged in at <ts>' cookie value. Stateless: nothing to store."""
    payload = str(int(time.time()))
    return f"{payload}.{_sign(payload)}"


def valid_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    payload, _, signature = token.rpartition(".")
    if not hmac.compare_digest(signature, _sign(payload)):
        return False
    try:
        issued = int(payload)
    except ValueError:
        return False
    return 0 <= time.time() - issued <= MAX_AGE


def check_password(candidate: str) -> bool:
    expected = password()
    if expected is None:
        return True
    return hmac.compare_digest(candidate, expected)


def rate_limited(client: str) -> bool:
    """True when this client has burned its login attempts for the window."""
    now = time.time()
    recent = [t for t in _attempts[client] if now - t < _WINDOW]
    _attempts[client] = recent
    return len(recent) >= _MAX_ATTEMPTS


def record_attempt(client: str) -> None:
    _attempts[client].append(time.time())


def clear_attempts(client: str) -> None:
    _attempts.pop(client, None)


def cookie_kwargs() -> dict:
    """Cookie flags. Secure is off when FORKCAST_INSECURE_COOKIE is set, which
    is what lets a plain-HTTP LAN test work; hosts terminate TLS so the default
    is the safe one."""
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": not os.environ.get("FORKCAST_INSECURE_COOKIE"),
        "max_age": MAX_AGE,
        "path": "/",
    }


def new_secret_key() -> str:
    """Helper for generating a FORKCAST_SECRET_KEY value."""
    return secrets.token_urlsafe(32)
