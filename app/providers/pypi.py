from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

from .base import FetchResult, Provider, RepoRef, ReleaseItem, looks_prerelease, register

try:  # accurate PEP 440 pre-release detection
    from packaging.version import InvalidVersion, Version
except Exception:  # pragma: no cover - packaging is a dependency, but stay safe
    Version = None  # type: ignore
    InvalidVersion = Exception  # type: ignore


def _parse_rfc822(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def _is_prerelease(version: str) -> bool:
    if Version is not None:
        try:
            return Version(version).is_prerelease
        except InvalidVersion:
            pass
    return looks_prerelease(version)


@register
class PyPIProvider(Provider):
    """PyPI packages have no git releases/tags; a project's releases RSS feed
    lists its versions. Each feed item is one release (version + date + page URL).

    The package is a single identifier, stored in `repo.name` (with `owner`
    fixed to 'pypi')."""

    key = "pypi"
    label = "PyPI"
    default_base_url = "https://pypi.org"
    supports_tags = False

    def headers(self, repo: RepoRef) -> dict[str, str]:
        return {"User-Agent": "release-radar (+https://github.com/)"}

    async def list_releases(self, repo: RepoRef, etag: str | None = None) -> FetchResult:
        pkg = repo.name
        url = f"{self.api_base(repo)}/rss/project/{pkg}/releases.xml"
        resp, new_etag, not_modified = await self._fetch_response(url, repo, etag)
        if not_modified:
            return FetchResult([], new_etag, True)
        return FetchResult(self._parse_feed(resp.text), new_etag, False)

    async def list_tags(self, repo: RepoRef, etag: str | None = None) -> FetchResult:
        return FetchResult([], None, False)  # not applicable

    def _parse_feed(self, xml_text: str) -> list[ReleaseItem]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []
        items = []
        for item in root.iter("item"):
            version = (item.findtext("title") or "").strip()
            if not version:
                continue
            items.append(
                ReleaseItem(
                    kind="release",
                    external_key=version,
                    name=version,
                    tag_name=version,
                    url=(item.findtext("link") or "").strip(),
                    published_at=_parse_rfc822(item.findtext("pubDate")),
                    prerelease=_is_prerelease(version),
                )
            )
        return items
