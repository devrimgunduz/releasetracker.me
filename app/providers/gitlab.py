from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from .base import Provider, RepoRef, ReleaseItem, register


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@register
class GitLabProvider(Provider):
    key = "gitlab"
    label = "GitLab"
    default_base_url = "https://gitlab.com"

    def api_root(self, repo: RepoRef) -> str:
        return f"{self.api_base(repo)}/api/v4"

    def project_id(self, repo: RepoRef) -> str:
        # GitLab identifies projects by URL-encoded "group/subgroup/project".
        return quote(f"{repo.owner}/{repo.name}", safe="")

    def headers(self, repo: RepoRef) -> dict[str, str]:
        return {"PRIVATE-TOKEN": repo.token} if repo.token else {}

    async def list_releases(self, repo: RepoRef) -> list[ReleaseItem]:
        url = f"{self.api_root(repo)}/projects/{self.project_id(repo)}/releases"
        data = await self._get_json(url, repo, params={"per_page": 30})
        return [
            ReleaseItem(
                kind="release",
                external_key=r.get("tag_name", ""),
                name=r.get("name") or r.get("tag_name", ""),
                tag_name=r.get("tag_name", ""),
                url=(r.get("_links") or {}).get("self", ""),
                published_at=_parse_ts(r.get("released_at") or r.get("created_at")),
            )
            for r in data
        ]

    async def list_tags(self, repo: RepoRef) -> list[ReleaseItem]:
        url = f"{self.api_root(repo)}/projects/{self.project_id(repo)}/repository/tags"
        data = await self._get_json(url, repo, params={"per_page": 30})
        web = f"{self.api_base(repo)}/{repo.owner}/{repo.name}/-/tags"
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
