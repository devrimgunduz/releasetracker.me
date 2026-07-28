"""Tests for the PyPI provider: releases RSS feed + PEP 440 pre-release flags."""
import httpx
import pytest

from app.providers import get_provider
from app.providers.base import RepoRef

REPO = RepoRef(owner="pypi", name="requests")

FEED = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>2.34.2</title><link>https://pypi.org/project/requests/2.34.2/</link>
        <pubDate>Thu, 14 May 2026 19:25:26 GMT</pubDate></item>
  <item><title>2.34.0.dev1</title><link>https://pypi.org/project/requests/2.34.0.dev1/</link>
        <pubDate>Sun, 03 May 2026 20:21:40 GMT</pubDate></item>
  <item><title>2.33.0b1</title><link>https://pypi.org/project/requests/2.33.0b1/</link>
        <pubDate>Fri, 01 May 2026 10:00:00 GMT</pubDate></item>
</channel></rss>"""


@pytest.mark.asyncio
async def test_pypi_feed_parsed_with_dates_and_prerelease_flags():
    def handler(req):
        assert req.url.path == "/rss/project/requests/releases.xml"
        return httpx.Response(200, text=FEED)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        res = await get_provider("pypi", c).list_releases(REPO)

    by = {i.external_key: i for i in res.items}
    assert set(by) == {"2.34.2", "2.34.0.dev1", "2.33.0b1"}
    assert by["2.34.2"].prerelease is False
    assert by["2.34.0.dev1"].prerelease is True          # .dev1
    assert by["2.33.0b1"].prerelease is True             # b1 (no separator — needs PEP 440 parsing)
    assert by["2.34.2"].url == "https://pypi.org/project/requests/2.34.2/"
    assert by["2.34.2"].published_at.year == 2026


@pytest.mark.asyncio
async def test_pypi_has_no_tags():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="x"))) as c:
        res = await get_provider("pypi", c).list_tags(REPO)
    assert res.items == []
