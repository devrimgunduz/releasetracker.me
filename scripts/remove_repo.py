"""Remove a watched repository by id, after a confirmation prompt.

    python -m scripts.remove_repo <id>

Deleting the repository cascades to its recorded releases and notification
routes (same as the Delete button in the web UI).
"""
from __future__ import annotations

import asyncio
import sys

from app.db import SessionFactory
from app.models import Repository


async def _run(repo_id: int) -> int:
    # Load first so we can show what will be deleted. Everything runs on one
    # event loop, so the shared engine's pooled connection stays on its loop.
    async with SessionFactory() as session:
        repo = await session.get(Repository, repo_id)
        if repo is None:
            print(f"No repository with id {repo_id}.")
            return 1
        slug, forge = repo.slug, repo.forge_type

    try:
        answer = input(
            f"Delete repository #{repo_id}  {slug} ({forge}) and its release history? [y/N] "
        )
    except EOFError:
        answer = ""
    if answer.strip().lower() not in ("y", "yes"):
        print("Aborted — nothing deleted.")
        return 0

    async with SessionFactory() as session:
        repo = await session.get(Repository, repo_id)
        if repo is not None:
            await session.delete(repo)  # cascades to releases + notification routes
            await session.commit()
    print(f"Removed #{repo_id} {slug}.")
    return 0


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Usage: python -m scripts.remove_repo <id>")
    try:
        repo_id = int(sys.argv[1])
    except ValueError:
        sys.exit("Repository id must be an integer.")
    sys.exit(asyncio.run(_run(repo_id)))


if __name__ == "__main__":
    main()
