"""Force a poll of one repository right now, bypassing the schedule and the
rest of a full sweep.

    python -m scripts.poll_repo <id>

Note: this only checks the forge for *new* releases/tags on that repo — it
does not retry a previously-recorded release whose notification failed earlier
(e.g. a bad token that's since been fixed). For that, run a full sweep instead
(`radarctl poll`), which retries every pending release across all repos.
"""
from __future__ import annotations

import asyncio
import sys

import httpx

from app.config import get_settings
from app.db import SessionFactory
from app.models import Repository
from app.poller import HTTP_TIMEOUT, REPO_POLL_TIMEOUT, _poll_repo
from app.ssrf import SSRFGuardTransport


async def _run(repo_id: int) -> int:
    async with SessionFactory() as session:
        repo = await session.get(Repository, repo_id)
        if repo is None:
            print(f"No repository with id {repo_id}.")
            return 1
        slug = repo.slug

    settings = get_settings()
    async with httpx.AsyncClient(
        timeout=HTTP_TIMEOUT,
        follow_redirects=False,
        transport=SSRFGuardTransport(httpx.AsyncHTTPTransport()),
    ) as client:
        try:
            await asyncio.wait_for(_poll_repo(client, repo_id, settings), timeout=REPO_POLL_TIMEOUT)
        except asyncio.TimeoutError:
            print(f"Poll timed out for {slug} after {REPO_POLL_TIMEOUT:.0f}s.")
            return 1

    print(f"Polled {slug}.")
    return 0


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Usage: python -m scripts.poll_repo <id>")
    try:
        repo_id = int(sys.argv[1])
    except ValueError:
        sys.exit("Repository id must be an integer.")
    sys.exit(asyncio.run(_run(repo_id)))


if __name__ == "__main__":
    main()
