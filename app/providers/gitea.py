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
class GiteaProvider(Provider):
    key = "gitea"
    label = "Gitea / Forgejo"
    requires_base_url = True  # self-hosted: user must supply the instance URL

    def api_root(self, repo: RepoRef) -> str:
        return f"{self.api_base(repo)}/api/v1"

    def headers(self, repo: RepoRef) -> dict[str, str]:
        return {"Authorization": f"token {repo.token}"} if repo.token else {}

    async def list_releases(self, repo: RepoRef, etag: str | None = None) -> FetchResult:
        url = f"{self.api_root(repo)}/repos/{repo.owner}/{repo.name}/releases"
        data, new_etag, not_modified = await self._fetch(url, repo, etag, {"limit": 30})
        if not_modified:
            return FetchResult([], new_etag, True)
        items = [
            ReleaseItem(
                kind="release",
                external_key=str(r["id"]),
                name=r.get("name") or r.get("tag_name", ""),
                tag_name=r.get("tag_name", ""),
                url=r.get("html_url", ""),
                published_at=_parse_ts(r.get("published_at") or r.get("created_at")),
                prerelease=bool(r.get("prerelease")),
            )
            for r in data
        ]
        return FetchResult(items, new_etag, False)

    async def list_tags(self, repo: RepoRef, etag: str | None = None) -> FetchResult:
        url = f"{self.api_root(repo)}/repos/{repo.owner}/{repo.name}/tags"
        data, new_etag, not_modified = await self._fetch(url, repo, etag, {"limit": 30})
        if not_modified:
            return FetchResult([], new_etag, True)
        web = f"{self.api_base(repo)}/{repo.owner}/{repo.name}/releases/tag"
        items = [
            ReleaseItem(
                kind="tag",
                external_key=t["name"],
                name=t["name"],
                tag_name=t["name"],
                url=f"{web}/{t['name']}",
                prerelease=looks_prerelease(t["name"]),
            )
            for t in data
        ]
        return FetchResult(items, new_etag, False)
