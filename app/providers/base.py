"""Forge provider adapters.

Adding a new forge = subclass Provider, implement list_releases / list_tags,
and register it with @register("name"). Nothing else in the app needs to change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import httpx


@dataclass(slots=True)
class ReleaseItem:
    """A forge-agnostic release or tag."""

    kind: str            # "release" | "tag"
    external_key: str    # stable id used for dedup (release id, or tag name)
    name: str = ""
    tag_name: str = ""
    url: str = ""
    published_at: datetime | None = None


@dataclass(slots=True)
class RepoRef:
    """Everything a provider needs to identify and reach one repository."""

    owner: str
    name: str
    base_url: str = ""          # instance URL; "" means provider default
    token: str | None = None    # decrypted access token, if any

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"


class Provider:
    """Base class. Subclasses set `default_base_url` and `requires_base_url`."""

    key: str = ""
    label: str = ""
    default_base_url: str = ""
    requires_base_url: bool = False   # true for self-hosted-only forges
    supports_releases: bool = True
    supports_tags: bool = True

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    def api_base(self, repo: RepoRef) -> str:
        return (repo.base_url or self.default_base_url).rstrip("/")

    def headers(self, repo: RepoRef) -> dict[str, str]:
        return {}

    async def list_releases(self, repo: RepoRef) -> list[ReleaseItem]:
        raise NotImplementedError

    async def list_tags(self, repo: RepoRef) -> list[ReleaseItem]:
        raise NotImplementedError

    async def _get_json(self, url: str, repo: RepoRef, params: dict | None = None):
        resp = await self.client.get(url, headers=self.headers(repo), params=params)
        resp.raise_for_status()
        return resp.json()


_REGISTRY: dict[str, type[Provider]] = {}


def register(cls: type[Provider]) -> type[Provider]:
    _REGISTRY[cls.key] = cls
    return cls


def get_provider(key: str, client: httpx.AsyncClient) -> Provider:
    try:
        return _REGISTRY[key](client)
    except KeyError:
        raise ValueError(f"Unknown forge type: {key!r}") from None


def available_providers() -> list[type[Provider]]:
    return sorted(_REGISTRY.values(), key=lambda c: c.label)
