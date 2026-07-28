"""Tests for the web directory-index provider (Apache/nginx autoindex scraping)."""
import httpx
import pytest

from app.providers import get_provider
from app.providers.base import RepoRef

REPO = RepoRef(owner="www.haproxy.org", name="download/3.4/src",
               base_url="https://www.haproxy.org/download/3.4/src/")

# Real HAProxy autoindex markup (trimmed).
PAGE = """<html><head><title>Index of /download/3.4/src</title></head><body>
<h1>Index of /download/3.4/src</h1>
<pre>      <a href="?C=N;O=A">Name</a> <a href="?C=M;O=A">Last modified</a>
<hr>      <a href="/download/3.4/">Parent Directory</a>                            -
      <a href="releases.json">releases.json</a>                 03-Jul-2026 08:23  3.6K
      <a href="haproxy-3.4.2.tar.gz.sha256">haproxy-3.4.2.tar.gz.sha256</a>  03-Jul-2026 08:23   87
      <a href="haproxy-3.4.2.tar.gz">haproxy-3.4.2.tar.gz</a>       03-Jul-2026 08:23  5.2M
      <a href="haproxy-3.4.1.tar.gz">haproxy-3.4.1.tar.gz</a>       25-Jun-2026 13:55  5.2M
      <a href="haproxy-3.4.0.tar.gz">haproxy-3.4.0.tar.gz</a>       03-Jun-2026 13:22  5.2M
      <a href="snapshot/">snapshot/</a>                            03-Jun-2026 04:25    -
<hr></pre></body></html>"""


@pytest.mark.asyncio
async def test_autoindex_parsed_into_releases():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=PAGE))) as c:
        res = await get_provider("webindex", c).list_releases(REPO)

    # Only real .tar.gz archives — sidecars (.sha256), non-archives (releases.json),
    # and subdirectories (snapshot/, Parent Directory) are ignored.
    assert [i.external_key for i in res.items] == ["3.4.2", "3.4.1", "3.4.0"]

    top = res.items[0]
    assert top.kind == "release" and top.prerelease is False
    assert top.published_at.year == 2026 and top.published_at.month == 7 and top.published_at.day == 3
    assert top.url == "https://www.haproxy.org/download/3.4/src/haproxy-3.4.2.tar.gz"


@pytest.mark.asyncio
async def test_dev_archive_flagged_prerelease():
    page = '<pre><a href="haproxy-3.5-dev14.tar.gz">x</a> 01-Jul-2026 08:23 5M</pre>'
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=page))) as c:
        res = await get_provider("webindex", c).list_releases(REPO)
    assert len(res.items) == 1
    assert res.items[0].external_key == "3.5-dev14"
    assert res.items[0].prerelease is True  # -dev suffix
