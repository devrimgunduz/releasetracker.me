"""Forge provider adapters.

Adding a new forge = subclass Provider, implement list_releases / list_tags,
and register it with @register("name"). Nothing else in the app needs to change.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

from ..ssrf import SSRFError, validate_public_url

# Detects a pre-release identifier in a tag/version string, for forges that don't
# expose an explicit flag (GitLab, Bitbucket) and for plain tags. Requires the
# token to follow a separator so real names like "prometheus" don't match "pre".
_PRE_RE = re.compile(
    r"[-_.+](?:alpha|beta|rc|preview|pre|dev|snapshot|nightly|canary|eap)",
    re.IGNORECASE,
)


def looks_prerelease(tag: str) -> bool:
    return bool(_PRE_RE.search(tag or ""))


@dataclass(slots=True)
class ReleaseItem:
    """A forge-agnostic release or tag."""

    kind: str            # "release" | "tag"
    external_key: str    # stable id used for dedup (release id, or tag name)
    name: str = ""
    tag_name: str = ""
    url: str = ""
    published_at: datetime | None = None
    prerelease: bool = False


@dataclass(slots=True)
class FetchResult:
    """Outcome of one conditional listing request."""

    items: list[ReleaseItem]
    etag: str | None = None
    not_modified: bool = False  # server returned 304; items is empty, reuse stored data


class RateLimited(Exception):
    """Raised when a forge signals its rate limit is exhausted."""

    def __init__(self, host: str, reset_at: datetime | None) -> None:
        self.host = host
        self.reset_at = reset_at
        super().__init__(f"rate limited by {host}" + (f" until {reset_at}" if reset_at else ""))


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


def _reset_at(resp: httpx.Response) -> datetime | None:
    retry_after = resp.headers.get("retry-after", "")
    if retry_after.isdigit():
        return datetime.now(timezone.utc) + timedelta(seconds=int(retry_after))
    reset = resp.headers.get("x-ratelimit-reset", "")
    if reset.isdigit():
        return datetime.fromtimestamp(int(reset), tz=timezone.utc)
    return None


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

    async def list_releases(self, repo: RepoRef, etag: str | None = None) -> FetchResult:
        raise NotImplementedError

    async def list_tags(self, repo: RepoRef, etag: str | None = None) -> FetchResult:
        raise NotImplementedError

    async def _fetch_response(
        self, url: str, repo: RepoRef, etag: str | None = None, params: dict | None = None
    ) -> tuple[httpx.Response | None, str | None, bool]:
        """Conditional GET returning the raw response (None on 304). Raises
        RateLimited on an exhausted quota. Use this for non-JSON bodies (e.g. RSS).

        Validates the destination — and every redirect hop — against
        ssrf.validate_public_url() before connecting, so a repo/base_url
        pointing at an internal or loopback address is refused rather than
        polled. The client is expected to have follow_redirects disabled;
        redirects are followed here, one hop at a time, so each Location can
        be re-validated (a naive allow-then-follow check can be bypassed by a
        redirect to a private address)."""
        headers = dict(self.headers(repo))
        if etag:
            headers["If-None-Match"] = etag

        next_url = url
        for _ in range(5):  # bounded redirect chain
            validate_public_url(next_url)
            resp = await self.client.get(next_url, headers=headers, params=params)
            if resp.is_redirect:
                location = resp.headers.get("location")
                if not location:
                    break
                next_url = str(resp.next_request.url) if resp.next_request else location
                params = None  # query params only apply to the original request
                continue
            break
        else:
            raise SSRFError("Too many redirects.")

        if resp.status_code == 304:
            return None, etag, True

        if resp.status_code in (403, 429):
            remaining = resp.headers.get("x-ratelimit-remaining")
            retry_after = resp.headers.get("retry-after")
            message = ""
            try:
                message = (resp.json() or {}).get("message", "")
            except Exception:
                pass
            if remaining == "0" or retry_after or "rate limit" in message.lower():
                raise RateLimited(resp.request.url.host, _reset_at(resp))

        resp.raise_for_status()
        return resp, resp.headers.get("ETag"), False

    async def _fetch(
        self, url: str, repo: RepoRef, etag: str | None = None, params: dict | None = None
    ) -> tuple[object | None, str | None, bool]:
        """Conditional GET returning parsed JSON. Returns (json_or_None, etag, not_modified)."""
        resp, new_etag, not_modified = await self._fetch_response(url, repo, etag, params)
        if not_modified:
            return None, new_etag, True
        return resp.json(), new_etag, False


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
