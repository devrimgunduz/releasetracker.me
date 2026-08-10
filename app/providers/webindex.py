from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin

from .base import FetchResult, Provider, RepoRef, ReleaseItem, looks_prerelease, register

# Source archives we treat as releases (checksum/sig sidecars end past these, so
# the end-anchor naturally skips .sha256/.md5/.asc/.sig files).
_ARCHIVE_RE = re.compile(r"\.(?:tar\.gz|tar\.xz|tar\.bz2|tgz|zip)$", re.IGNORECASE)
# A dotted version, optionally with a pre-release-ish suffix (e.g. 3.4.0, 3.4-dev14).
_VERSION_RE = re.compile(r"(\d+(?:\.\d+)+(?:[-.][A-Za-z0-9]+)*)")
# Apache/nginx autoindex row: an <a href> (not a ?sort link) then an optional
# "DD-Mon-YYYY HH:MM" last-modified stamp.
_ROW_RE = re.compile(
    r'<a\s+href="([^"?][^"]*)"[^>]*>[^<]*</a>\s*'
    r"(?:(\d{2})-([A-Za-z]{3})-(\d{4})\s+(\d{2}):(\d{2}))?",
    re.IGNORECASE,
)
_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def _extract_version(filename: str) -> str | None:
    stem = _ARCHIVE_RE.sub("", filename)
    m = _VERSION_RE.search(stem)
    return m.group(1) if m else None


@register
class WebIndexProvider(Provider):
    """Scrapes a plain HTTP directory listing (Apache/nginx autoindex) of source
    archives — for projects that publish tarballs on a web page rather than via a
    forge's releases API (e.g. https://www.haproxy.org/download/3.4/src/).

    The whole listing URL is the identity, stored in `repo.base_url`. Each archive
    file becomes a release; its version is parsed from the filename and its date
    from the listing's last-modified column."""

    key = "webindex"
    label = "Web directory index"
    requires_base_url = True
    supports_tags = False

    def headers(self, repo: RepoRef) -> dict[str, str]:
        return {"User-Agent": "release-radar (+https://github.com/)"}

    async def list_releases(self, repo: RepoRef, etag: str | None = None) -> FetchResult:
        # Use base_url as-is (with its trailing slash) — api_base() strips it,
        # which would make urljoin resolve links against the parent directory.
        url = repo.base_url
        resp, new_etag, not_modified = await self._fetch_response(url, repo, etag)
        if not_modified:
            return FetchResult([], new_etag, True)
        return FetchResult(self._parse(resp.text, url), new_etag, False)

    async def list_tags(self, repo: RepoRef, etag: str | None = None) -> FetchResult:
        return FetchResult([], None, False)

    def _parse(self, html: str, base_url: str) -> list[ReleaseItem]:
        order: list[str] = []
        by_version: dict[str, ReleaseItem] = {}
        for m in _ROW_RE.finditer(html):
            href = m.group(1)
            if href.endswith("/") or not _ARCHIVE_RE.search(href):
                continue  # skip subdirectories and non-archive files (sidecars, etc.)
            version = _extract_version(href.rsplit("/", 1)[-1])
            if not version or version in by_version:
                continue  # one release per version (first archive of it wins)
            resolved = urljoin(base_url, href)
            # A scraped href can carry a dangerous scheme (e.g. javascript:) that
            # still ends in an archive extension; only ever store http(s) URLs so
            # nothing but a real link is rendered on the dashboard later.
            if not resolved.lower().startswith(("http://", "https://")):
                continue
            when = None
            if m.group(2):
                try:
                    when = datetime(
                        int(m.group(4)), _MONTHS[m.group(3).title()], int(m.group(2)),
                        int(m.group(5)), int(m.group(6)), tzinfo=timezone.utc,
                    )
                except (KeyError, ValueError):
                    when = None
            by_version[version] = ReleaseItem(
                kind="release",
                external_key=version,
                name=version,
                tag_name=version,
                url=resolved,
                published_at=when,
                prerelease=looks_prerelease(version),
            )
            order.append(version)
        return [by_version[v] for v in order]
