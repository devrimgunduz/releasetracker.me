"""Create (or promote) an admin user.

    python -m scripts.create_admin <username> [password]

If password is omitted, it's prompted for interactively (not echoed) via
getpass — preferred over passing it as an argument, since argv is visible to
other local users via `ps`/`/proc/<pid>/cmdline` and tends to land in shell
history.
"""
from __future__ import annotations

import asyncio
import getpass
import sys

from sqlalchemy import select

from app.db import SessionFactory
from app.models import User
from app.security import hash_password


async def main(username: str, password: str) -> None:
    if len(password) < 8:
        sys.exit("Password must be at least 8 characters.")
    async with SessionFactory() as session:
        existing = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if existing:
            existing.password_hash = hash_password(password)
            existing.role = "admin"
            action = "updated"
        else:
            session.add(
                User(username=username, password_hash=hash_password(password), role="admin")
            )
            action = "created"
        await session.commit()
    print(f"Admin user {username!r} {action}.")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit("Usage: python -m scripts.create_admin <username> [password]")
    username = sys.argv[1]
    password = sys.argv[2] if len(sys.argv) == 3 else getpass.getpass("Password: ")
    asyncio.run(main(username, password))
