from __future__ import annotations

import html

import httpx


def _escape(text: str) -> str:
    return html.escape(text or "", quote=False)


def format_message(repo_slug: str, forge: str, kind: str, name: str, tag: str, url: str) -> str:
    label = "release" if kind == "release" else "tag"
    title = _escape(name or tag or "(unnamed)")
    lines = [
        f"\U0001f4e6 New {label} in <b>{_escape(repo_slug)}</b> ({_escape(forge)})",
        f"<b>{title}</b>",
    ]
    if tag and tag != name:
        lines.append(f"<code>{_escape(tag)}</code>")
    if url:
        # quote=True: escape any " in the URL so it can't break out of the href
        # attribute and inject Telegram HTML. The link text uses the normal escape.
        href = html.escape(url or "", quote=True)
        lines.append(f'<a href="{href}">View on {_escape(forge)}</a>')
    return "\n".join(lines)


async def send_telegram(
    client: httpx.AsyncClient, bot_token: str, chat_id: str, text: str
) -> None:
    """Raise on failure so the caller can record it and retry next cycle."""
    resp = await client.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Telegram API {resp.status_code}: {resp.text[:300]}")
