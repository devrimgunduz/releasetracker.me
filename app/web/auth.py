from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..csrf import verify_csrf
from ..db import get_session
from ..models import User
from ..rate_limit import SlidingWindowRateLimiter
from ..security import verify_password
from .deps import flash, pop_flashes, redirect, templates

router = APIRouter()

# 5 attempts per 5 minutes per source IP. See app/rate_limit.py for why this
# is in-process (fine for this project's single-worker deployment) and how
# it relates to the optional external fail2ban integration.
_login_limiter = SlidingWindowRateLimiter(max_attempts=5, window_seconds=300)

# Dedicated auth logger. Failed logins are logged at WARNING with the client IP
# in a fixed, greppable shape so fail2ban can match them (see deploy/fail2ban).
auth_log = logging.getLogger("radar.auth")


def client_ip(request: Request) -> str:
    """Real client IP for logging/banning.

    X-Forwarded-For is only honoured when the direct socket peer is a configured
    trusted proxy (TRUSTED_PROXY_IPS, default: the local Apache). Otherwise the
    peer address is used — so a client that reaches the app directly can't spoof
    XFF to evade the login rate limiter or get an arbitrary address banned by
    fail2ban. Behind the trusted proxy, Apache's mod_proxy_http *appends* the peer
    it saw to any XFF the client sent, so the LAST entry is the real client (using
    the first would reintroduce the spoof). Adjust TRUSTED_PROXY_IPS if you chain
    multiple proxies."""
    peer = request.client.host if request.client else "-"
    xff = request.headers.get("x-forwarded-for")
    if xff and peer in get_settings().trusted_proxies:
        return xff.split(",")[-1].strip()
    return peer


@router.get("/login")
async def login_form(request: Request):
    if request.session.get("user_id"):
        return redirect("/")
    return templates.TemplateResponse(
        request, "login.html", {"flashes": pop_flashes(request)}
    )


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
    _csrf=Depends(verify_csrf),
):
    ip = client_ip(request)
    if not _login_limiter.allow(ip):
        auth_log.warning("rate-limited: too many login attempts from %s", ip)
        flash(request, "Too many login attempts. Please wait a few minutes and try again.", "error")
        return redirect("/login")

    user = (
        await session.execute(select(User).where(User.username == username.strip()))
    ).scalar_one_or_none()

    if user is None or not verify_password(password, user.password_hash):
        auth_log.warning("failed login for %r from %s", username.strip(), client_ip(request))
        flash(request, "Wrong username or password.", "error")
        return redirect("/login")

    _login_limiter.reset(ip)  # a genuine user shouldn't be penalized by earlier typos
    auth_log.info("login ok for %r from %s", user.username, client_ip(request))
    request.session["user_id"] = user.id
    flash(request, f"Signed in as {user.username}.", "success")
    return redirect("/")


@router.post("/logout")
async def logout(request: Request, _csrf=Depends(verify_csrf)):
    request.session.clear()
    return redirect("/login")
