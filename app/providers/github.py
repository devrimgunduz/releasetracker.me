from __future__ import annotations

from datetime import datetime

from .base import Provider, RepoRef, ReleaseItem, looks_prerelease, register


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

    async def list_releases(self, repo: RepoRef) -> list[ReleaseItem]:
        url = f"{self.api_base(repo)}/repos/{repo.owner}/{repo.name}/releases"
        data = await self._get_json(url, repo, params={"per_page": 30})
        items = []
        for r in data:
            items.append(
                ReleaseItem(
                    kind="release",
                    external_key=str(r["id"]),
                    name=r.get("name") or r.get("tag_name") or "",
                    tag_name=r.get("tag_name", ""),
                    url=r.get("html_url", ""),
                    published_at=_parse_ts(r.get("published_at") or r.get("created_at")),
                    prerelease=bool(r.get("prerelease")),
                )
            )
        return items

    async def list_tags(self, repo: RepoRef) -> list[ReleaseItem]:
        url = f"{self.api_base(repo)}/repos/{repo.owner}/{repo.name}/tags"
        data = await self._get_json(url, repo, params={"per_page": 30})
        base = f"https://github.com/{repo.owner}/{repo.name}/releases/tag"
        return [
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
