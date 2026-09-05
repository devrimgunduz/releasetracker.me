"""File a GitHub issue when a watched repository shows a new release/tag.

Unlike Telegram (many bots, many chats) or email (one shared digest), this
channel has a single global target — GITHUB_ISSUE_REPO — since the use case is
a packaging tracker or similar single inbox (e.g. pgdg-packaging/pgdg-rpms)
that should hear about new releases across many watched repos, not a
per-repository destination.
"""
from __future__ import annotations

import httpx


def _md_safe(text: str) -> str:
    """Backticks inside an inline code span would close it early. Dropping
    them is enough — GitHub renders the rest of the body as trusted-author
    Markdown regardless, so this isn't a security boundary, just tidiness."""
    return (text or "").replace("`", "'")


def format_issue(
    repo_slug: str, forge: str, kind: str, name: str, tag: str, url: str
) -> tuple[str, str]:
    """Build (title, body) for the packaging-request issue."""
    label = "release" if kind == "release" else "tag"
    version = tag or name or "unknown version"
    title = f"Package request: {repo_slug} {_md_safe(version)}"

    lines = [f"A new {label} was detected for **{repo_slug}** ({forge})."]
    if name and name != version:
        lines.append(f"\n**Name:** {_md_safe(name)}")
    if tag:
        lines.append(f"\n**Tag:** `{_md_safe(tag)}`")
    if url:
        lines.append(f"\n**Link:** {url}")
    lines.append("\n_Filed automatically by Release Radar._")
    return title, "\n".join(lines)


async def create_github_issue(
    client: httpx.AsyncClient, token: str, target_repo: str, title: str, body: str
) -> None:
    """Raise on failure so the caller can record it and retry next cycle."""
    resp = await client.post(
        f"https://api.github.com/repos/{target_repo}/issues",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"title": title, "body": body},
    )
    if resp.status_code != 201:
        raise RuntimeError(f"GitHub issues API {resp.status_code}: {resp.text[:300]}")
