"""The engine. Run poll_all() on a schedule to detect and dispatch; run
send_daily_summary() once a day to email everything discovered since the last one.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .crypto import decrypt
from .db import SessionFactory
from .models import NotificationRoute, Release, Repository, TelegramBot, utcnow
from .notifiers.email import build_digest_html, send_digest
from .notifiers.telegram import format_message, send_telegram
from .providers import RateLimited, RepoRef, get_provider

log = logging.getLogger("radar.poller")

HTTP_TIMEOUT = httpx.Timeout(20.0)
_OLDEST = datetime.min.replace(tzinfo=timezone.utc)

TEST_MESSAGE = "\U0001f514 Release Radar test — if you can read this, Telegram delivery works."


async def send_test_notifications() -> None:
    """Send a test message down every configured Telegram path, without touching
    releases or the poller. Exercises token decryption, bot lookup, and chat-ID
    resolution exactly as a real notification would. Prints a per-target report."""
    async with SessionFactory() as session:
        routes = (
            await session.execute(
                select(NotificationRoute, Repository, TelegramBot)
                .join(Repository, NotificationRoute.repository_id == Repository.id)
                .outerjoin(TelegramBot, NotificationRoute.bot_id == TelegramBot.id)
                .where(
                    NotificationRoute.channel_type == "telegram",
                    NotificationRoute.enabled.is_(True),
                )
            )
        ).all()
        bots = (await session.execute(select(TelegramBot))).scalars().all()

    # Prefer testing actual routes (mirrors real delivery). If none exist yet,
    # fall back to each bot's default chat so a freshly added bot can be verified.
    targets: list[tuple[str, str, str]] = []  # (label, token, chat_id)
    for route, repo, bot in routes:
        if bot is None:
            print(f"route {route.id}: referenced bot was deleted — skipping")
            continue
        chat_id = route.chat_id or bot.default_chat_id
        token = decrypt(bot.token_enc)
        if not chat_id or not token:
            print(f"route {route.id} ({repo.slug} via {bot.name}): no chat_id/token — skipping")
            continue
        targets.append((f"{repo.slug} → {bot.name} (chat {chat_id})", token, chat_id))

    if not targets:
        for bot in bots:
            token = decrypt(bot.token_enc)
            if bot.default_chat_id and token:
                targets.append((f"{bot.name} default (chat {bot.default_chat_id})", token, bot.default_chat_id))

    if not targets:
        print("Nothing to test: no enabled Telegram routes and no bot has a default chat ID.")
        return

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        for label, token, chat_id in targets:
            try:
                await send_telegram(client, token, chat_id, TEST_MESSAGE)
                print(f"OK    {label}")
            except Exception as exc:
                print(f"FAIL  {label}: {exc}")


async def poll_all() -> None:
    """One full sweep. Polls least-recently-polled repositories first, honours an
    optional per-sweep cap, and backs off a host for the rest of the sweep once it
    signals its rate limit is exhausted."""
    settings = get_settings()
    async with SessionFactory() as session:
        repos = (await session.execute(select(Repository))).scalars().all()

    if not repos:
        log.info("poll: no repositories registered")
        return

    repos.sort(key=lambda r: r.last_polled_at or _OLDEST)  # fair rotation
    if settings.max_repos_per_sweep:
        repos = repos[: settings.max_repos_per_sweep]

    limited: set[tuple[str, str]] = set()  # (forge_type, base_url) buckets to skip

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        for repo in repos:
            bucket = (repo.forge_type, repo.base_url)
            if bucket in limited:
                continue  # this host is already exhausted this sweep
            try:
                await _poll_repo(client, repo.id, settings)
            except RateLimited as rl:
                limited.add(bucket)
                until = f" until {rl.reset_at:%H:%M UTC}" if rl.reset_at else ""
                log.warning(
                    "rate limited by %s%s — skipping remaining %s repos this sweep",
                    rl.host, until, repo.forge_type,
                )
                await _record_error(repo.id, f"rate limited{until}; will retry next sweep")
            except Exception as exc:  # one bad repo must not stop the sweep
                log.exception("poll failed for repo id=%s", repo.id)
                await _record_error(repo.id, str(exc))

            if settings.request_delay_seconds:
                await asyncio.sleep(settings.request_delay_seconds)


async def _poll_repo(client: httpx.AsyncClient, repo_id: int, settings: Settings) -> None:
    async with SessionFactory() as session:
        repo = await session.get(Repository, repo_id)
        if repo is None:
            return

        provider = get_provider(repo.forge_type, client)
        token = decrypt(repo.token_enc)
        if not token and repo.forge_type == "github":
            token = settings.default_github_token or None  # shared fallback token
        ref = RepoRef(owner=repo.owner, name=repo.name, base_url=repo.base_url, token=token)

        # Conditional fetches. A 304 (not_modified) means nothing changed — and,
        # when authenticated, doesn't even count against the rate limit.
        fetched = []
        changed = False
        if repo.watch_releases and provider.supports_releases:
            res = await provider.list_releases(ref, repo.etag_releases)
            if not res.not_modified:
                fetched += res.items
                repo.etag_releases = res.etag
                changed = True
        if repo.watch_tags and provider.supports_tags:
            res = await provider.list_tags(ref, repo.etag_tags)
            if not res.not_modified:
                fetched += res.items
                repo.etag_tags = res.etag
                changed = True

        first_run = not repo.seeded

        if not changed and not first_run:
            # Everything returned 304 — record the poll and move on cheaply.
            repo.last_polled_at = utcnow()
            repo.last_error = None
            await session.commit()
            return

        # What have we already seen for this repo?
        seen_rows = (
            await session.execute(
                select(Release.kind, Release.external_key).where(
                    Release.repository_id == repo.id
                )
            )
        ).all()
        seen = {(k, key) for k, key in seen_rows}

        new_items = [it for it in fetched if (it.kind, it.external_key) not in seen]

        created: list[Release] = []
        for it in new_items:
            # Excluded pre-releases are still recorded (visible on the dashboard)
            # but pre-marked handled so they never notify or enter the digest.
            exclude = (not repo.include_prereleases) and it.prerelease
            row = Release(
                repository_id=repo.id,
                kind=it.kind,
                external_key=it.external_key,
                name=it.name,
                tag_name=it.tag_name,
                url=it.url,
                published_at=it.published_at,
                prerelease=it.prerelease,
                # On first run we baseline silently; excluded pre-releases are
                # likewise marked done so they stay quiet.
                notified=first_run or exclude,
                summarized=first_run or exclude,
            )
            session.add(row)
            created.append(row)

        repo.seeded = True
        repo.last_polled_at = utcnow()
        repo.last_error = None
        await session.commit()

        if first_run:
            log.info("seeded %s with %d existing item(s)", repo.slug, len(created))
            return

        for row in created:
            await session.refresh(row)

    # Dispatch Telegram outside the write transaction.
    for row in created:
        await _dispatch_telegram(client, row.id)


async def _dispatch_telegram(client: httpx.AsyncClient, release_id: int) -> None:
    async with SessionFactory() as session:
        row = await session.get(Release, release_id)
        if row is None or row.notified:
            return
        repo = await session.get(Repository, row.repository_id)

        routes = (
            await session.execute(
                select(NotificationRoute).where(
                    NotificationRoute.repository_id == row.repository_id,
                    NotificationRoute.channel_type == "telegram",
                    NotificationRoute.enabled.is_(True),
                )
            )
        ).scalars().all()

        if not routes:
            row.notified = True  # nothing to send; don't keep re-checking
            await session.commit()
            return

        text = format_message(
            repo.slug, repo.forge_type, row.kind, row.name, row.tag_name, row.url
        )

        all_ok = True
        for route in routes:
            bot = await session.get(TelegramBot, route.bot_id) if route.bot_id else None
            if bot is None:
                all_ok = False
                continue
            chat_id = route.chat_id or bot.default_chat_id
            token = decrypt(bot.token_enc)
            if not chat_id or not token:
                all_ok = False
                continue
            try:
                await send_telegram(client, token, chat_id, text)
            except Exception:
                log.exception("telegram send failed (route id=%s)", route.id)
                all_ok = False

        # Only mark notified if every route succeeded, so failures retry next sweep.
        row.notified = all_ok
        await session.commit()


async def _record_error(repo_id: int, message: str) -> None:
    async with SessionFactory() as session:
        repo = await session.get(Repository, repo_id)
        if repo:
            repo.last_error = message[:1000]
            repo.last_polled_at = utcnow()
            await session.commit()


async def send_daily_summary(settings: Settings | None = None) -> None:
    """Email one digest of everything discovered for email-routed repos since the
    last summary, then mark those items summarized."""
    settings = settings or get_settings()
    if not settings.email_enabled:
        log.info("summary: email disabled (no SMTP_HOST / recipients)")
        return

    async with SessionFactory() as session:
        rows = (
            await session.execute(
                select(Release, Repository)
                .join(Repository, Release.repository_id == Repository.id)
                .join(NotificationRoute, NotificationRoute.repository_id == Repository.id)
                .where(
                    Release.summarized.is_(False),
                    NotificationRoute.channel_type == "email",
                    NotificationRoute.enabled.is_(True),
                )
                .order_by(Release.discovered_at)
            )
        ).all()

        # Deduplicate (a repo may match once per email route) and collect payload.
        seen_ids: set[int] = set()
        items = []
        release_objs = []
        for release, repo in rows:
            if release.id in seen_ids:
                continue
            seen_ids.add(release.id)
            release_objs.append(release)
            items.append(
                {
                    "repo_slug": repo.slug,
                    "kind": release.kind,
                    "name": release.name or release.tag_name,
                    "url": release.url,
                    "published_at": release.published_at,
                }
            )

        if not items:
            log.info("summary: nothing new to report")
            return

        today = datetime.now().strftime("%Y-%m-%d")
        await send_digest(
            settings,
            subject=f"Release Radar — {len(items)} new item(s) — {today}",
            html_body=build_digest_html(items),
        )

        for release in release_objs:
            release.summarized = True
        await session.commit()
        log.info("summary: emailed %d item(s)", len(items))
