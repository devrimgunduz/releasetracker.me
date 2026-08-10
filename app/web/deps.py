from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from ..csrf import csrf_context
from ..db import get_session
from ..models import User

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR), context_processors=[csrf_context])


def reltime(dt: datetime | None) -> str:
    """Human relative time, e.g. '15 hours ago', '7 days ago', 'a month ago'."""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    secs = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())
    mins, hours, days = secs / 60, secs / 3600, secs / 86400
    if secs < 45:
        return "just now"
    if mins < 45:
        n = round(mins)
        return "a minute ago" if n == 1 else f"{n} minutes ago"
    if hours < 22:
        n = round(hours)
        return "an hour ago" if n == 1 else f"{n} hours ago"
    if days < 1.5:
        return "a day ago"
    if days < 26:
        return f"{round(days)} days ago"
    months = days / 30.44
    if months < 1.5:
        return "a month ago"
    if months < 11:
        return f"{round(months)} months ago"
    years = days / 365.25
    return "a year ago" if round(years) == 1 else f"{round(years)} years ago"


templates.env.filters["reltime"] = reltime


def external_url(value: str | None) -> str:
    """Render-time guard: blank any URL that isn't http(s). Release/repo URLs can
    originate from scraped pages or self-hosted forges, so a `javascript:` (or
    other) scheme must never reach an href even though autoescaping wouldn't stop
    it from executing on click."""
    if not value:
        return ""
    v = str(value).strip()
    return v if v.lower().startswith(("http://", "https://")) else ""


templates.env.filters["external_url"] = external_url


def flash(request: Request, message: str, category: str = "info") -> None:
    request.session.setdefault("_flashes", []).append({"message": message, "category": category})


def pop_flashes(request: Request) -> list[dict]:
    return request.session.pop("_flashes", [])


class LoginRequired(Exception):
    pass


async def current_user(
    request: Request, session: AsyncSession = Depends(get_session)
) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise LoginRequired()
    user = await session.get(User, user_id)
    if user is None:
        request.session.clear()
        raise LoginRequired()
    return user


async def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")
    return user


def render(request: Request, template: str, user: User, **ctx):
    return templates.TemplateResponse(
        request,
        template,
        {"user": user, "flashes": pop_flashes(request), **ctx},
    )


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)
