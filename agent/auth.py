"""The admin session: who may make this deployment place a real phone call.

The public dashboard runs the whole incident in the visitor's browser and costs only OpenAI
minutes. Everything that spends Twilio money, or reveals an employee's mobile, sits behind one
shared password (ADMIN_PASSWORD) held by the team.

A login returns a signed token rather than a stored session, so a scaled-to-zero deployment with
no session table still recognises it: the token carries its own expiry and an HMAC over it, keyed
by ADMIN_SESSION_SECRET (or the password itself, so a deployment that sets only the password still
works). Nothing else is in the token; there is one admin.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

from fastapi import Header, HTTPException

from agent.config import settings

SESSION_SECONDS = 12 * 60 * 60


def admin_configured() -> bool:
    return bool(settings.admin_password)


def _key() -> bytes:
    secret = settings.admin_session_secret or settings.admin_password
    return hashlib.sha256(f"raqeeb-admin:{secret}".encode()).digest()


def _sign(payload: str) -> str:
    return base64.urlsafe_b64encode(hmac.new(_key(), payload.encode(), hashlib.sha256).digest()).decode().rstrip("=")


def issue_token(now: float | None = None) -> tuple[str, int]:
    """A token and the epoch second it stops working."""
    expires_at = int((now if now is not None else time.time()) + SESSION_SECONDS)
    payload = str(expires_at)
    return f"{payload}.{_sign(payload)}", expires_at


def token_is_valid(token: str, now: float | None = None) -> bool:
    if not admin_configured() or not token:
        return False
    payload, _, signature = token.partition(".")
    if not payload.isdigit() or not signature:
        return False
    if not hmac.compare_digest(_sign(payload), signature):
        return False
    return int(payload) > (now if now is not None else time.time())


def password_is_correct(password: str) -> bool:
    """Constant time, so a wrong guess tells an attacker nothing about how wrong it was."""
    return admin_configured() and secrets.compare_digest(password.encode(), settings.admin_password.encode())


def _bearer(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def is_admin(authorization: str | None) -> bool:
    """For routes that serve both audiences and only change what they do."""
    return token_is_valid(_bearer(authorization))


async def admin_required(authorization: str | None = Header(default=None)) -> None:
    """For routes only the team may call at all."""
    if not is_admin(authorization):
        raise HTTPException(status_code=401, detail="Admin sign-in required.")
