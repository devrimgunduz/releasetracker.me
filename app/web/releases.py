from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..csrf import verify_csrf
from ..db import get_session
from ..models import Release, Repository
from ..poller import poll_all
from ..providers import available_providers
from .deps import current_user, flash, redirect, render

router = APIRouter()

PER_REPO_LIMIT = 12
SORTS = {"updated", "added", "name"}
_OLDEST = datetime.min.replace(tzinfo=timezone.utc)


def dedupe_versions(releases: list[Release]) -> list[Release]:
    """Collapse a release and a tag for the same version into one entry, keeping
    the release (which carries a real published date; a bare tag often doesn't).
    Entries with no version string are all kept."""
    best: dict[str, Release] = {}
    extras: list[Release] = []
    for r in releases:
        key = r.tag_name or r.name
        if not key:
            extras.append(r)
            continue
        current = best.get(key)
        if current is None or (r.kind == "release" and current.kind != "release"):
            best[key] = r
    return list(best.values()) + extras


@router.get("/")
async def dashboard(
    request: Request,
    sort: str = Query(default="updated"),
    repo: int | None = Query(default=None),  # expand one repo (show all its releases)
    user=Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    if sort not in SORTS:
        sort = "updated"

    repos = (await session.execute(select(Repository))).scalars().all()

    rel_stmt = select(Release)
    if repo:
        rel_stmt = rel_stmt.where(Release.repository_id == repo)
    releases = (await session.execute(rel_stmt)).scalars().all()

    by_repo: dict[int, list[Release]] = defaultdict(list)
    for r in releases:
        by_repo[r.repository_id].append(r)
    for rid, rs in by_repo.items():
        deduped = dedupe_versions(rs)  # release wins over same-version tag
        # Sort by real publish date, newest first. Entries with no date (e.g.
        # GitHub tags, whose API carries none) sink to the bottom instead of
        # masquerading as "just now" via their poll time.
        deduped.sort(key=lambda r: r.published_at or _OLDEST, reverse=True)
        by_repo[rid] = deduped

    shown_repos = [r for r in repos if r.id == repo] if repo else repos

    def latest(r: Repository) -> datetime:
        rs = by_repo.get(r.id) or []
        dated = [x.published_at for x in rs if x.published_at]
        if dated:
            return max(dated)  # rank by newest real release, not poll time
        return max((x.discovered_at for x in rs), default=_OLDEST)

    if sort == "name":
        shown_repos.sort(key=lambda r: r.slug.lower())
    elif sort == "added":
        shown_repos.sort(key=lambda r: r.created_at or _OLDEST, reverse=True)
    else:  # updated
        shown_repos.sort(key=latest, reverse=True)

    items = []
    for r in shown_repos:
        rs = by_repo.get(r.id, [])
        shown = rs if repo else rs[:PER_REPO_LIMIT]
        items.append(
            {"repo": r, "releases": shown, "more": 0 if repo else max(0, len(rs) - PER_REPO_LIMIT)}
        )

    total = (await session.execute(select(func.count()).select_from(Release))).scalar_one()

    return render(
        request,
        "dashboard.html",
        user,
        items=items,
        repo_count=len(repos),
        total_releases=total,
        sort=sort,
        expanded=repo,
        forge_labels={p.key: p.label for p in available_providers()},
    )


@router.post("/poll-now")
async def poll_now(request: Request, user=Depends(current_user), _csrf=Depends(verify_csrf)):
    # Fire and forget so the request returns immediately.
    asyncio.create_task(poll_all())
    flash(request, "Polling started — new items will appear shortly.", "success")
    return redirect("/")
