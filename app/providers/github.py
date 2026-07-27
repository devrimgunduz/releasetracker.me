from __future__ import annotations

from datetime import datetime

from .base import FetchResult, Provider, RepoRef, ReleaseItem, looks_prerelease, register


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@register
class GitHubProvider(Provider):
    key = "github"
    label = "GitHub"
    default_base_url = "https://api.github.com"

    def headers(self, repo: RepoRef) -> dict[str, str]:
        h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if repo.token:
            h["Authorization"] = f"Bearer {repo.token}"
        return h

    async def list_releases(self, repo: RepoRef, etag: str | None = None) -> FetchResult:
        url = f"{self.api_base(repo)}/repos/{repo.owner}/{repo.name}/releases"
        data, new_etag, not_modified = await self._fetch(url, repo, etag, {"per_page": 30})
        if not_modified:
            return FetchResult([], new_etag, True)
        items = [
            ReleaseItem(
                kind="release",
                external_key=str(r["id"]),
                name=r.get("name") or r.get("tag_name") or "",
                tag_name=r.get("tag_name", ""),
                url=r.get("html_url", ""),
                published_at=_parse_ts(r.get("published_at") or r.get("created_at")),
                prerelease=bool(r.get("prerelease")),
            )
            for r in data
        ]
        return FetchResult(items, new_etag, False)

    async def list_tags(self, repo: RepoRef, etag: str | None = None) -> FetchResult:
        url = f"{self.api_base(repo)}/repos/{repo.owner}/{repo.name}/tags"
        data, new_etag, not_modified = await self._fetch(url, repo, etag, {"per_page": 30})
        if not_modified:
            return FetchResult([], new_etag, True)
        base = f"https://github.com/{repo.owner}/{repo.name}/releases/tag"
        items = [
            ReleaseItem(
                kind="tag",
                external_key=t["name"],
                name=t["name"],
                tag_name=t["name"],
                url=f"{base}/{t['name']}",
                prerelease=looks_prerelease(t["name"]),
            )
            for t in data
        ]
        return FetchResult(items, new_etag, False)
