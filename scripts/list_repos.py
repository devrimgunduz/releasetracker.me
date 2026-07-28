"""List watched repositories with their ids (to find one to remove).

    python -m scripts.list_repos
"""
from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from app.db import SessionFactory
from app.models import Release, Repository


async def main() -> None:
    async with SessionFactory() as session:
        repos = (
            await session.execute(select(Repository).order_by(Repository.id))
        ).scalars().all()
        counts = {
            rid: n
            for rid, n in (
                await session.execute(
                    select(Release.repository_id, func.count()).group_by(Release.repository_id)
                )
            ).all()
        }

    if not repos:
        print("No repositories.")
        return

    print(f"{'ID':>4}  {'FORGE':11} {'RELEASES':>8}  REPOSITORY")
    for r in repos:
        print(f"{r.id:>4}  {r.forge_type:11} {counts.get(r.id, 0):>8}  {r.slug}")


if __name__ == "__main__":
    asyncio.run(main())
