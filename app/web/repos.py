from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..crypto import encrypt
from ..db import get_session
from ..models import NotificationRoute, Repository, TelegramBot
from ..providers import available_providers
from ..repo_url import RepoURLError, parse_repo_url
from .deps import current_user, flash, redirect, render

router = APIRouter(prefix="/repositories")


@router.get("")
async def list_repos(
    request: Request,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    repos = (
        await session.execute(select(Repository).order_by(Repository.owner, Repository.name))
    ).scalars().all()
    bots = (await session.execute(select(TelegramBot).order_by(TelegramBot.name))).scalars().all()
    return render(
        request,
        "repos.html",
        user,
        repos=repos,
        providers=available_providers(),
        bots=bots,
    )


@router.post("/add")
async def add_repo(
    request: Request,
    forge_type: str = Form("github"),
    url: str = Form(...),
    token: str = Form(""),
    watch_releases: bool = Form(False),
    watch_tags: bool = Form(False),
    bot_ids: list[int] = Form(default=[]),
    email_digest: bool = Form(False),
    user=Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    # forge_type from the dropdown is only a hint; a known host in the URL wins.
    try:
        forge, base_url, owner, name = parse_repo_url(url, forge_type)
    except RepoURLError as exc:
        flash(request, str(exc), "error")
        return redirect("/repositories")

    if not watch_releases and not watch_tags:
        watch_releases = True  # watching nothing is pointless; default to releases

    repo = Repository(
        forge_type=forge,
        base_url=base_url,
        owner=owner,
        name=name,
        token_enc=encrypt(token.strip()) if token.strip() else None,
        watch_releases=watch_releases,
        watch_tags=watch_tags,
    )
    session.add(repo)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        flash(request, "That repository is already registered.", "error")
        return redirect("/repositories")

    # Create the notification routes chosen on the form. Each checked bot becomes
    # a Telegram route delivering to that bot's default chat (edit the chat per
    # route later on the Notifications page). email_digest adds an email route.
    valid_bot_ids: set[int] = set(
        (await session.execute(select(TelegramBot.id))).scalars().all()
    )
    telegram_routes = 0
    for bot_id in bot_ids:
        if bot_id not in valid_bot_ids:
            continue  # ignore stale/forged ids
        session.add(
            NotificationRoute(
                repository_id=repo.id,
                channel_type="telegram",
                bot_id=bot_id,
                enabled=True,
            )
        )
        telegram_routes += 1
    if email_digest:
        session.add(
            NotificationRoute(repository_id=repo.id, channel_type="email", enabled=True)
        )
    if telegram_routes or email_digest:
        await session.commit()

    channels = []
    if telegram_routes:
        channels.append(f"{telegram_routes} Telegram route(s)")
    if email_digest:
        channels.append("the daily email")
    tail = f" Notifying via {' and '.join(channels)}." if channels else (
        " No notifications set yet — add some on the Notifications page."
    )
    flash(
        request,
        f"Now watching {repo.slug} on {forge}. Baseline captured on the first poll.{tail}",
        "success",
    )
    return redirect("/repositories")


@router.post("/{repo_id}/delete")
async def delete_repo(
    repo_id: int,
    request: Request,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    repo = await session.get(Repository, repo_id)
    if repo:
        await session.delete(repo)
        await session.commit()
        flash(request, f"Stopped watching {repo.slug}.", "success")
    return redirect("/repositories")
