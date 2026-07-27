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
class BitbucketProvider(Provider):
    key = "bitbucket"
    label = "Bitbucket"
    default_base_url = "https://api.bitbucket.org/2.0"
    supports_releases = False  # Bitbucket has no releases API — tags only.

    def headers(self, repo: RepoRef) -> dict[str, str]:
        # Accepts an access token as a bearer credential.
        return {"Authorization": f"Bearer {repo.token}"} if repo.token else {}

    async def list_releases(self, repo: RepoRef) -> list[ReleaseItem]:
        return []  # not supported by the forge

    async def list_tags(self, repo: RepoRef) -> list[ReleaseItem]:
        url = f"{self.api_base(repo)}/repositories/{repo.owner}/{repo.name}/refs/tags"
        data = await self._get_json(url, repo, params={"pagelen": 30, "sort": "-target.date"})
        web = f"https://bitbucket.org/{repo.owner}/{repo.name}/src"
        items = []
        for t in data.get("values", []):
            target = t.get("target") or {}
            items.append(
                ReleaseItem(
                    kind="tag",
                    external_key=t["name"],
                    name=t["name"],
                    tag_name=t["name"],
                    url=f"{web}/{t['name']}",
                    published_at=_parse_ts(target.get("date")),
                    prerelease=looks_prerelease(t["name"]),
                )
            )
        return items
