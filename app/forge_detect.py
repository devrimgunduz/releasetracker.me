"""Detect which forge software a self-hosted host runs, by probing its API.

Used when the user leaves the Forge dropdown on "Auto-detect" and the URL's
host isn't one of the well-known public forges. Each probe is a cheap
unauthenticated GET; all traffic goes through SSRFGuardTransport.
"""
from __future__ import annotations

import httpx

from .ssrf import SSRFGuardTransport

PROBE_TIMEOUT = httpx.Timeout(6.0)


def _json(resp: httpx.Response):
    try:
        return resp.json()
    except ValueError:
        return None


async def detect_forge(base_url: str, client: httpx.AsyncClient | None = None) -> str | None:
    """Return a provider key ("gitea" / "gitlab") for the instance at base_url,
    or None when it can't be identified."""
    base = base_url.rstrip("/")
    own = client is None
    if own:
        client = httpx.AsyncClient(
            timeout=PROBE_TIMEOUT,
            follow_redirects=False,
            transport=SSRFGuardTransport(httpx.AsyncHTTPTransport()),
        )
    try:
        # Gitea / Forgejo: /api/v1/version -> {"version": "..."}
        try:
            r = await client.get(f"{base}/api/v1/version")
            body = _json(r)
            if r.status_code == 200 and isinstance(body, dict) and "version" in body:
                return "gitea"
        except httpx.HTTPError:
            pass
        # GitLab: /api/v4/version needs auth (401 JSON {"message": ...}) on most
        # instances; public project listing is 200 with a JSON list.
        try:
            r = await client.get(f"{base}/api/v4/version")
            body = _json(r)
            if r.status_code == 200 and isinstance(body, dict) and "version" in body:
                return "gitlab"
            if r.status_code == 401 and isinstance(body, dict) and "message" in body:
                return "gitlab"
        except httpx.HTTPError:
            pass
        return None
    finally:
        if own:
            await client.aclose()
