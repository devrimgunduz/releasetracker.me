"""Tests for the provider HTTP layer: conditional requests + rate-limit handling.

Uses httpx.MockTransport, so no network and no database.
"""
import httpx
import pytest

from app.providers import RateLimited, get_provider
from app.providers.base import RepoRef

REPO = RepoRef(owner="acme", name="widget")

RELEASE = {
    "id": 1, "name": "v1.0.0", "tag_name": "v1.0.0",
    "html_url": "https://github.com/acme/widget/releases/tag/v1.0.0",
    "published_at": "2026-01-01T00:00:00Z", "prerelease": False,
}


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_returns_items_and_etag():
    def handler(req):
        return httpx.Response(200, json=[RELEASE], headers={"ETag": 'W/"abc"'})

    async with _client(handler) as c:
        res = await get_provider("github", c).list_releases(REPO)
    assert res.not_modified is False
    assert res.etag == 'W/"abc"'
    assert len(res.items) == 1 and res.items[0].tag_name == "v1.0.0"


@pytest.mark.asyncio
async def test_conditional_304_is_not_modified():
    seen = {}

    def handler(req):
        seen["if_none_match"] = req.headers.get("if-none-match")
        return httpx.Response(304, headers={"ETag": 'W/"abc"'})

    async with _client(handler) as c:
        res = await get_provider("github", c).list_releases(REPO, etag='W/"abc"')
    assert seen["if_none_match"] == 'W/"abc"'  # we sent the stored etag
    assert res.not_modified is True
    assert res.items == [] and res.etag == 'W/"abc"'


@pytest.mark.asyncio
async def test_rate_limit_raises():
    def handler(req):
        return httpx.Response(
            403,
            json={"message": "API rate limit exceeded"},
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "4102444800"},
        )

    async with _client(handler) as c:
        with pytest.raises(RateLimited) as exc:
            await get_provider("github", c).list_releases(REPO)
    assert exc.value.reset_at is not None  # parsed from x-ratelimit-reset


@pytest.mark.asyncio
async def test_plain_403_is_not_treated_as_rate_limit():
    # A 403 without rate-limit signals (e.g. private repo, bad token) should surface
    # as a normal HTTP error, not a RateLimited backoff.
    def handler(req):
        return httpx.Response(403, json={"message": "Must have admin rights"})

    async with _client(handler) as c:
        with pytest.raises(httpx.HTTPStatusError):
            await get_provider("github", c).list_releases(REPO)


@pytest.mark.asyncio
async def test_credentials_stripped_on_cross_origin_redirect(monkeypatch):
    # A forge (or an open redirect on one) bounces us to another host. The token
    # must not follow across the origin boundary.
    monkeypatch.setattr("app.providers.base.validate_public_url", lambda url: None)
    seen = []

    def handler(req):
        seen.append((req.url.host, req.headers.get("authorization")))
        if req.url.host == "api.github.com":
            return httpx.Response(302, headers={"location": "https://evil.example.com/repos"})
        return httpx.Response(200, json=[RELEASE])

    repo = RepoRef(owner="acme", name="widget", token="s3cret")
    async with _client(handler) as c:
        await get_provider("github", c).list_releases(repo)

    assert seen[0] == ("api.github.com", "Bearer s3cret")  # sent to the real forge
    assert seen[1][0] == "evil.example.com"
    assert seen[1][1] is None  # Authorization dropped on the cross-origin hop


@pytest.mark.asyncio
async def test_credentials_kept_on_same_origin_redirect(monkeypatch):
    monkeypatch.setattr("app.providers.base.validate_public_url", lambda url: None)
    seen = []

    def handler(req):
        seen.append((str(req.url), req.headers.get("authorization")))
        if req.url.path.endswith("/releases"):
            return httpx.Response(302, headers={"location": "https://api.github.com/moved"})
        return httpx.Response(200, json=[RELEASE])

    repo = RepoRef(owner="acme", name="widget", token="s3cret")
    async with _client(handler) as c:
        await get_provider("github", c).list_releases(repo)

    assert seen[1][1] == "Bearer s3cret"  # same origin: token still sent
