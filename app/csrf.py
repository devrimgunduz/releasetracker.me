"""CSRF protection for state-changing (POST) requests.

The app already sets `same_site="lax"` on the session cookie, which stops
the cookie being sent on cross-site POSTs in modern browsers — but that's a
single layer of defense with no fallback. This adds an explicit synchronizer
token: a random value stored in the (server-signed) session and echoed back
by every form, checked before any POST handler runs.
"""
from __future__ import annotations

import secrets

from fastapi import Form, HTTPException, Request, status

SESSION_KEY = "_csrf_token"


def get_csrf_token(request: Request) -> str:
    """Return this session's CSRF token, generating one on first use.

    Works whether or not the user is logged in yet — SessionMiddleware
    manages the (signed, cookie-backed) session dict independently of
    authentication, so the token set here on a GET (e.g. the login page)
    is still present when the matching POST arrives."""
    token = request.session.get(SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[SESSION_KEY] = token
    return token


def csrf_context(request: Request) -> dict:
    """Jinja2Templates `context_processors` entry — makes `csrf_token`
    available in every template automatically, so individual views don't
    need to pass it explicitly."""
    return {"csrf_token": get_csrf_token(request)}


async def verify_csrf(request: Request, csrf_token: str = Form(...)) -> None:
    """FastAPI dependency for POST routes: add `Depends(verify_csrf)`
    alongside a route's other parameters.

    FastAPI merges Form() fields declared anywhere in a route's dependency
    tree into a single body parse, so this doesn't conflict with — or
    require reordering — the route's own `Form(...)` fields."""
    expected = request.session.get(SESSION_KEY)
    if not expected or not secrets.compare_digest(csrf_token, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your session expired or this form was submitted from "
            "somewhere unexpected. Please refresh the page and try again.",
        )
