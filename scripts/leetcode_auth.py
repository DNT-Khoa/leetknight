"""
Shared LeetCode auth helpers used by test_leetcode.py and submit_leetcode.py.

Two responsibilities:
  1. Read LEETCODE_SESSION + LEETCODE_CSRF from env, fail fast with a clear
     message if either is missing or the session JWT is already expired.
  2. Classify HTTP errors from LeetCode into (session-expired / csrf-rejected /
     rate-limited / other) so the calling script can print a precise message
     telling the user exactly which cookie to refresh.

LeetCode does not publish an API; this module mirrors what the leetcode.com
JavaScript does when authenticating its own requests (set cookies + echo the
csrftoken value as the x-csrftoken header).
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Optional

BASE = "https://leetcode.com"
HTTP_TIMEOUT_SECONDS = 30


class AuthError(Exception):
    """Raised when cookies are missing, expired, or rejected.

    .reason is one of: 'missing', 'expired', 'session', 'csrf', 'rate_limit',
    'other'.  Callers should print a tailored message based on .reason.
    """

    def __init__(self, message: str, reason: str):
        super().__init__(message)
        self.reason = reason


@dataclass
class Session:
    leetcode_session: str
    csrf_token: str


def _decode_jwt_exp(jwt: str) -> Optional[int]:
    try:
        parts = jwt.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = claims.get("exp")
        return int(exp) if exp is not None else None
    except Exception:
        return None


def load_session_from_env() -> Session:
    session = os.environ.get("LEETCODE_SESSION", "").strip()
    csrf = os.environ.get("LEETCODE_CSRF", "").strip()

    missing = []
    if not session:
        missing.append("LEETCODE_SESSION")
    if not csrf:
        missing.append("LEETCODE_CSRF")
    if missing:
        raise AuthError(
            f"missing LeetCode cookies: {', '.join(missing)}.\n"
            f"Run 'leet.io: Set LeetCode Cookies' to paste fresh values from "
            f"your browser DevTools (Application > Cookies > leetcode.com).",
            reason="missing",
        )

    exp = _decode_jwt_exp(session)
    if exp is not None and exp < time.time():
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(exp))
        raise AuthError(
            f"LEETCODE_SESSION expired on {when}.\n"
            f"Run 'leet.io: Set LeetCode Cookies' to paste a fresh value.",
            reason="expired",
        )

    return Session(leetcode_session=session, csrf_token=csrf)


def make_requests_session(s: Session, referer_path: str = "/"):
    """Build a requests.Session preloaded with the LeetCode auth headers."""
    import requests

    rs = requests.Session()
    rs.cookies.set("LEETCODE_SESSION", s.leetcode_session, domain="leetcode.com")
    rs.cookies.set("csrftoken", s.csrf_token, domain="leetcode.com")
    rs.headers.update({
        "User-Agent": "leet-io/1.0",
        "Referer": f"{BASE}{referer_path}",
        "x-csrftoken": s.csrf_token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    return rs


def classify_response_error(status_code: int, body_text: str, retry_after: Optional[str]) -> AuthError:
    """Turn a failed HTTP response into a typed AuthError.

    Django's CSRF middleware runs before auth, so a CSRF rejection has a
    distinctive 403 + 'CSRF' substring. A bare 401/403 with no CSRF text means
    the session was rejected — usually a server-side revocation (logout
    elsewhere, password change) since the JWT exp check ran clean.
    """
    if status_code == 429:
        wait = f" (Retry-After: {retry_after})" if retry_after else ""
        return AuthError(
            f"LeetCode is rate-limiting{wait}. Wait a few seconds and try again.",
            reason="rate_limit",
        )
    if status_code == 403 and "CSRF" in body_text:
        return AuthError(
            "LeetCode rejected the csrftoken (request blocked by CSRF middleware).\n"
            "Run 'leet.io: Set LeetCode Cookies' and paste a fresh csrftoken "
            "(while you're there, refresh LEETCODE_SESSION too — they're usually rotated together).",
            reason="csrf",
        )
    if status_code in (401, 403):
        return AuthError(
            "LeetCode rejected the LEETCODE_SESSION (server-side invalidated — "
            "maybe you logged out elsewhere, changed your password, or the account "
            "was flagged).\n"
            "Run 'leet.io: Set LeetCode Cookies' to paste a fresh value.",
            reason="session",
        )
    return AuthError(
        f"unexpected LeetCode response (HTTP {status_code}): {body_text[:200]}",
        reason="other",
    )


def fail(err: AuthError, exit_code: int = 2) -> None:
    """Print a tagged, user-facing message and exit."""
    tag = {
        "missing": "[auth] ",
        "expired": "[auth] ",
        "session": "[auth] ",
        "csrf":    "[auth] ",
        "rate_limit": "[rate-limit] ",
        "other":   "[error] ",
    }.get(err.reason, "[error] ")
    print(f"{tag}{err}", file=sys.stderr)
    sys.exit(exit_code)
