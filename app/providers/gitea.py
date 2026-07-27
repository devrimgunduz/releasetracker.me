from __future__ import annotations

from datetime import datetime

from .base import Provider, RepoRef, ReleaseItem, register


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

    async def list_releases(self, repo: RepoRef) -> list[ReleaseItem]:
        url = f"{self.api_root(repo)}/repos/{repo.owner}/{repo.name}/releases"
        data = await self._get_json(url, repo, params={"limit": 30})
        return [
            ReleaseItem(
                kind="release",
                external_key=str(r["id"]),
                name=r.get("name") or r.get("tag_name", ""),
                tag_name=r.get("tag_name", ""),
                url=r.get("html_url", ""),
                published_at=_parse_ts(r.get("published_at") or r.get("created_at")),
            )
            for r in data
        ]

    async def list_tags(self, repo: RepoRef) -> list[ReleaseItem]:
        url = f"{self.api_root(repo)}/repos/{repo.owner}/{repo.name}/tags"
        data = await self._get_json(url, repo, params={"limit": 30})
        web = f"{self.api_base(repo)}/{repo.owner}/{repo.name}/releases/tag"
        return [
            ReleaseItem(
                kind="tag",
                external_key=t["name"],
                name=t["name"],
                tag_name=t["name"],
                url=f"{web}/{t['name']}",
            )
            for t in data
        ]
