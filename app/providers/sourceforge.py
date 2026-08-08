from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime

# defusedxml guards against entity-expansion/XXE-style abuse of XML parsing;
# xml.etree.ElementTree's docs explicitly warn it's unsafe for untrusted data.
import defusedxml.ElementTree as ET

from .base import FetchResult, Provider, RepoRef, ReleaseItem, looks_prerelease, register


def _parse_rfc822(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


@register
class SourceForgeProvider(Provider):
    """SourceForge has no git-style releases/tags; it distributes files. The
    project's file RSS feed lists uploaded files, which are grouped here by their
    top-level folder (the conventional 'version' directory) into one release each.

    Note: the project is a single identifier, not owner/name — it is stored in
    `repo.name` (with `owner` fixed to 'sourceforge')."""

    key = "sourceforge"
    label = "SourceForge"
    default_base_url = "https://sourceforge.net"
    supports_tags = False  # file releases only

    def headers(self, repo: RepoRef) -> dict[str, str]:
        # Be a polite, identifiable client for the feed.
        return {"User-Agent": "release-radar (+https://github.com/)"}

    async def list_releases(self, repo: RepoRef, etag: str | None = None) -> FetchResult:
        project = repo.name
        base = self.api_base(repo)
        url = f"{base}/projects/{project}/rss"
        resp, new_etag, not_modified = await self._fetch_response(url, repo, etag)
        if not_modified:
            return FetchResult([], new_etag, True)
        return FetchResult(self._parse_feed(resp.text, project, base), new_etag, False)

    async def list_tags(self, repo: RepoRef, etag: str | None = None) -> FetchResult:
        return FetchResult([], None, False)  # not applicable

    def _parse_feed(self, xml_text: str, project: str, base: str) -> list[ReleaseItem]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []

        # Group files by their top-level folder = the version directory.
        order: list[str] = []
        groups: dict[str, datetime | None] = {}
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip().strip("/")
            if not title:
                continue
            version = title.split("/", 1)[0]  # top folder, or the filename at root
            when = _parse_rfc822(item.findtext("pubDate"))
            if version not in groups:
                groups[version] = when
                order.append(version)
            elif when and (groups[version] is None or when > groups[version]):
                groups[version] = when  # newest file in the folder dates the release

        return [
            ReleaseItem(
                kind="release",
                external_key=version,
                name=version,
                tag_name=version,
                url=f"{base}/projects/{project}/files/{version}/",
                published_at=groups[version],
                prerelease=looks_prerelease(version),
            )
            for version in order
        ]
