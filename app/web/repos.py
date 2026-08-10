from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..crypto import encrypt
from ..csrf import verify_csrf
from ..db import get_session
from ..models import NotificationRoute, Release, Repository, TelegramBot
from ..providers import available_providers
from ..repo_url import RepoURLError, parse_repo_url
from ..ssrf import SSRFError, validate_public_url
from .deps import current_user, flash, redirect, render, require_admin
from .releases import dedupe_versions, release_sort_key

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

    releases = (await session.execute(select(Release))).scalars().all()
    by_repo: dict[int, list[Release]] = defaultdict(list)
    for rel in releases:
        by_repo[rel.repository_id].append(rel)

    # The single newest tracked version per repo, keyed by repository id, so the
    # table can show "what's latest" alongside when we first discovered it.
    latest_release: dict[int, Release] = {}
    for rid, rs in by_repo.items():
        deduped = dedupe_versions(rs)
        deduped.sort(key=release_sort_key, reverse=True)
        if deduped:
            latest_release[rid] = deduped[0]

    return render(
        request,
        "repos.html",
        user,
        repos=repos,
        providers=available_providers(),
        bots=bots,
        tag_forges={p.key for p in available_providers() if p.supports_tags},
        latest_release=latest_release,
    )


@router.post("/add")
async def add_repo(
    request: Request,
    forge_type: str = Form("github"),
    url: str = Form(...),
    token: str = Form(""),
    watch_releases: bool = Form(False),
    watch_tags: bool = Form(False),
    exclude_prereleases: bool = Form(False),
    bot_ids: list[int] = Form(default=[]),
    email_digest: bool = Form(False),
    user=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    _csrf=Depends(verify_csrf),
):
    # forge_type from the dropdown is only a hint; a known host in the URL wins.
    try:
        forge, base_url, owner, name = parse_repo_url(url, forge_type)
    except RepoURLError as exc:
        flash(request, str(exc), "error")
        return redirect("/repositories")

    # SECURITY: reject repos that resolve to internal/loopback/link-local
    # addresses before they're ever stored — the worker would otherwise poll
    # them forever (SSRF). Known-forge URLs (github.com, gitlab.com, ...) have
    # base_url=="" and are checked against the provider's own default_base_url
    # at fetch time instead, so only self-hosted / webindex URLs hit this.
    if base_url:
        try:
            validate_public_url(base_url)
        except SSRFError as exc:
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
        include_prereleases=not exclude_prereleases,
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
    _csrf=Depends(verify_csrf),
):
    repo = await session.get(Repository, repo_id)
    if repo:
        await session.delete(repo)
        await session.commit()
        flash(request, f"Stopped watching {repo.slug}.", "success")
    return redirect("/repositories")


@router.post("/{repo_id}/toggle-releases")
async def toggle_releases(
    repo_id: int,
    request: Request,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_session),
    _csrf=Depends(verify_csrf),
):
    repo = await session.get(Repository, repo_id)
    if repo:
        repo.watch_releases = not repo.watch_releases
        await session.commit()
        state = "watching" if repo.watch_releases else "not watching"
        flash(request, f"Now {state} releases for {repo.slug}.", "success")
    return redirect("/repositories")


@router.post("/{repo_id}/toggle-tags")
async def toggle_tags(
    repo_id: int,
    request: Request,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_session),
    _csrf=Depends(verify_csrf),
):
    repo = await session.get(Repository, repo_id)
    if repo:
        repo.watch_tags = not repo.watch_tags
        await session.commit()
        state = "watching" if repo.watch_tags else "not watching"
        flash(request, f"Now {state} tags for {repo.slug}.", "success")
    return redirect("/repositories")


@router.post("/{repo_id}/toggle-prereleases")
async def toggle_prereleases(
    repo_id: int,
    request: Request,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_session),
    _csrf=Depends(verify_csrf),
):
    repo = await session.get(Repository, repo_id)
    if repo:
        repo.include_prereleases = not repo.include_prereleases
        await session.commit()
        state = "including" if repo.include_prereleases else "excluding"
        flash(request, f"Now {state} pre-releases for {repo.slug}.", "success")
    return redirect("/repositories")


@router.get("/{repo_id}/notifications")
async def edit_notifications(
    repo_id: int,
    request: Request,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    repo = await session.get(Repository, repo_id)
    if repo is None:
        flash(request, "Repository not found.", "error")
        return redirect("/repositories")

    bots = (await session.execute(select(TelegramBot).order_by(TelegramBot.name))).scalars().all()
    routes = (
        await session.execute(
            select(NotificationRoute).where(NotificationRoute.repository_id == repo_id)
        )
    ).scalars().all()

    # A box is checked when a route to that bot / an email route exists at all,
    # regardless of paused state — so opening and saving never silently changes it.
    attached_bot_ids = {r.bot_id for r in routes if r.channel_type == "telegram" and r.bot_id}
    email_on = any(r.channel_type == "email" for r in routes)

    return render(
        request,
        "repo_notifications.html",
        user,
        repo=repo,
        bots=bots,
        attached_bot_ids=attached_bot_ids,
        email_on=email_on,
    )


@router.post("/{repo_id}/notifications")
async def save_notifications(
    repo_id: int,
    request: Request,
    bot_ids: list[int] = Form(default=[]),
    email_digest: bool = Form(False),
    user=Depends(current_user),
    session: AsyncSession = Depends(get_session),
    _csrf=Depends(verify_csrf),
):
    repo = await session.get(Repository, repo_id)
    if repo is None:
        flash(request, "Repository not found.", "error")
        return redirect("/repositories")

    valid_bot_ids = set((await session.execute(select(TelegramBot.id))).scalars().all())
    desired = {b for b in bot_ids if b in valid_bot_ids}

    routes = (
        await session.execute(
            select(NotificationRoute).where(NotificationRoute.repository_id == repo_id)
        )
    ).scalars().all()

    existing_by_bot: dict[int, list[NotificationRoute]] = {}
    existing_email: list[NotificationRoute] = []
    for r in routes:
        if r.channel_type == "telegram" and r.bot_id is not None:
            existing_by_bot.setdefault(r.bot_id, []).append(r)
        elif r.channel_type == "email":
            existing_email.append(r)

    # Reconcile by existence only: never touch enabled/paused or chat_id of a
    # route that stays. Unchecking a bot removes its route(s); checking a new
    # one creates a route to that bot's default chat.
    for bot_id, rs in existing_by_bot.items():
        if bot_id not in desired:
            for r in rs:
                await session.delete(r)
    for bot_id in desired:
        if bot_id not in existing_by_bot:
            session.add(
                NotificationRoute(
                    repository_id=repo_id, channel_type="telegram", bot_id=bot_id, enabled=True
                )
            )

    if email_digest and not existing_email:
        session.add(NotificationRoute(repository_id=repo_id, channel_type="email", enabled=True))
    elif not email_digest and existing_email:
        for r in existing_email:
            await session.delete(r)

    await session.commit()
    flash(request, f"Notifications updated for {repo.slug}.", "success")
    return redirect("/repositories")
