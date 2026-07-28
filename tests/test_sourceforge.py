"""Tests for the SourceForge provider: RSS files grouped into version releases."""
import httpx
import pytest

from app.providers import get_provider
from app.providers.base import RepoRef

REPO = RepoRef(owner="sourceforge", name="proftpd")

# Two version folders (1.3.8, 1.3.7) with multiple files each, plus a root file.
FEED = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>/1.3.8/proftpd-1.3.8.tar.gz</title>
        <link>https://sourceforge.net/projects/proftpd/files/1.3.8/proftpd-1.3.8.tar.gz/download</link>
        <pubDate>Tue, 01 Jul 2025 10:00:00 GMT</pubDate></item>
  <item><title>/1.3.8/proftpd-1.3.8.tar.bz2</title>
        <link>x</link><pubDate>Wed, 02 Jul 2025 10:00:00 GMT</pubDate></item>
  <item><title>/1.3.7/proftpd-1.3.7.tar.gz</title>
        <link>x</link><pubDate>Mon, 01 Jan 2024 10:00:00 GMT</pubDate></item>
  <item><title>/README.md</title>
        <link>x</link><pubDate>Fri, 01 Mar 2024 10:00:00 GMT</pubDate></item>
</channel></rss>"""


@pytest.mark.asyncio
async def test_rss_grouped_into_version_releases():
    def handler(req):
        assert req.url.path == "/projects/proftpd/rss"
        return httpx.Response(200, text=FEED, headers={"Content-Type": "application/rss+xml"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        res = await get_provider("sourceforge", c).list_releases(REPO)

    keys = [i.external_key for i in res.items]
    assert keys == ["1.3.8", "1.3.7", "README.md"]  # one entry per top-level folder, feed order

    by_key = {i.external_key: i for i in res.items}
    # Folder date is the newest file within it (bz2 uploaded Jul 2).
    assert by_key["1.3.8"].published_at.day == 2
    # Release URL points at the version folder's files page.
    assert by_key["1.3.8"].url == "https://sourceforge.net/projects/proftpd/files/1.3.8/"
    assert by_key["1.3.8"].kind == "release"


@pytest.mark.asyncio
async def test_sourceforge_has_no_tags():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="x"))) as c:
        res = await get_provider("sourceforge", c).list_tags(REPO)
    assert res.items == []
