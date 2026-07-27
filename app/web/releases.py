from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Release, Repository
from ..poller import poll_all
from .deps import current_user, flash, redirect, render

router = APIRouter()


@router.get("/")
async def dashboard(
    request: Request,
    repo_id: int | None = Query(default=None),
    user=Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    repos = (
        await session.execute(select(Repository).order_by(Repository.owner, Repository.name))
    ).scalars().all()

    stmt = (
        select(Release, Repository)
        .join(Repository, Release.repository_id == Repository.id)
        .order_by(Release.discovered_at.desc())
        .limit(100)
    )
    if repo_id:
        stmt = stmt.where(Release.repository_id == repo_id)
    rows = (await session.execute(stmt)).all()

    total = (await session.execute(select(func.count()).select_from(Release))).scalar_one()

    return render(
        request,
        "dashboard.html",
        user,
        repos=repos,
        rows=rows,
        selected_repo=repo_id,
        total_releases=total,
    )


@router.post("/poll-now")
async def poll_now(request: Request, user=Depends(current_user)):
    # Fire and forget so the request returns immediately.
    asyncio.create_task(poll_all())
    flash(request, "Polling started — new items will appear shortly.", "success")
    return redirect("/")
