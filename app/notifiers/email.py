from __future__ import annotations

import html
from datetime import datetime
from email.message import EmailMessage

import aiosmtplib

from ..config import Settings


def _row(repo_slug: str, kind: str, name: str, url: str, when: datetime | None) -> str:
    e = lambda s: html.escape(s or "", quote=True)  # noqa: E731
    ts = when.strftime("%Y-%m-%d %H:%M") if when else ""
    link = f'<a href="{e(url)}">{e(name)}</a>' if url else e(name)
    return (
        "<tr>"
        f'<td style="padding:6px 12px;font-family:monospace">{e(repo_slug)}</td>'
        f'<td style="padding:6px 12px">{e(kind)}</td>'
        f'<td style="padding:6px 12px">{link}</td>'
        f'<td style="padding:6px 12px;color:#667">{e(ts)}</td>'
        "</tr>"
    )


def build_digest_html(items: list[dict]) -> str:
    rows = "\n".join(
        _row(i["repo_slug"], i["kind"], i["name"], i["url"], i["published_at"]) for i in items
    )
    return f"""\
<div style="font-family:system-ui,-apple-system,sans-serif;color:#16202a">
  <h2 style="margin:0 0 4px">Release Radar — daily summary</h2>
  <p style="color:#556;margin:0 0 16px">{len(items)} new release(s)/tag(s) in the last day.</p>
  <table style="border-collapse:collapse;width:100%;font-size:14px">
    <thead>
      <tr style="text-align:left;border-bottom:2px solid #ddd">
        <th style="padding:6px 12px">Repository</th>
        <th style="padding:6px 12px">Type</th>
        <th style="padding:6px 12px">Release / tag</th>
        <th style="padding:6px 12px">Published</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""


async def send_digest(settings: Settings, subject: str, html_body: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(settings.recipient_list)
    msg["Subject"] = subject
    msg.set_content("This is an HTML email. Open it in an HTML-capable client.")
    msg.add_alternative(html_body, subtype="html")

    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username or None,
        password=settings.smtp_password or None,
        start_tls=settings.smtp_use_tls,
    )
