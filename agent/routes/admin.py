"""Signing in as the team, and the employee picker both audiences share.

There is one admin password for the whole team (see agent/auth.py). Signing in unlocks the parts
of the dashboard that spend Twilio money: placing the dispatch call to a real mobile, and placing
it again after nobody answered.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from agent.auth import admin_configured, is_admin, issue_token, password_is_correct
from agent.employees import roster

router = APIRouter(prefix="/api", tags=["admin"])


class LoginInput(BaseModel):
    password: str = Field(max_length=200)


@router.post("/admin/login")
async def login(credentials: LoginInput):
    if not admin_configured():
        raise HTTPException(status_code=503, detail="No admin password is configured on this deployment.")
    if not password_is_correct(credentials.password):
        # A wrong password costs a second, which a person never notices and a script does.
        await asyncio.sleep(1)
        raise HTTPException(status_code=401, detail="Wrong password.")
    token, expires_at = issue_token()
    return {"token": token, "expires_at": expires_at}


@router.get("/admin/session")
async def session(authorization: str | None = Header(default=None)):
    """Whether the browser's stored token still works, so the dashboard can drop a stale one."""
    return {"admin": is_admin(authorization), "available": admin_configured()}


@router.get("/employees")
async def employees(authorization: str | None = Header(default=None)):
    """The on-duty employees the dashboard offers. Signed in, each carries the mobile configured
    for it, which the dashboard prefills into an editable field. Anonymously, names and staff
    numbers only: this reply is readable by anyone who opens the site."""
    return {"employees": roster(with_numbers=is_admin(authorization))}
