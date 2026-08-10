"""Outbound-URL validation to stop the poller being used as an SSRF pivot.

Every repository `base_url` (and, for known forges, the API base) is fetched
periodically and unattended by the worker. Without this check, a low-privilege
user could register a URL pointing at loopback, link-local (incl. cloud
metadata endpoints like 169.254.169.254), or other private-network addresses
and have the worker poll it forever — or, worse, ride along with a
credential attached (see poller._poll_repo's GitHub-token handling).

Two layers are provided:

* validate_public_url() — a fast, string-level pre-check used at repo-add time
  and again before each request/redirect hop. It resolves the hostname and
  refuses if any resolved address is non-public. On its own this is a
  time-of-check/time-of-use (TOCTOU) check: httpx re-resolves the name when it
  actually connects, so a name that passed validation could still be rebound to
  a private address (DNS rebinding) by the time the socket opens.

* SSRFGuardTransport — the authoritative *connect-time* guard. It resolves the
  host once, validates every address, and connects straight to the validated IP
  (pinning it), while preserving the original hostname for the Host header and
  TLS SNI/certificate verification. Because the exact IP used for the socket is
  the one that was validated, DNS rebinding can't slip a private address in
  between check and connect. The polling client is built with this transport.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

import httpx

ALLOWED_SCHEMES = {"http", "https"}


class SSRFError(ValueError):
    """Raised with a message safe to show the user (repo add) or log (poller)."""


def _is_blocked_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local      # covers 169.254.0.0/16, incl. cloud metadata
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def _resolve(host: str) -> list[str]:
    """Resolve a hostname to the list of IP literals it maps to.

    Factored out so both validate_public_url() and pick_public_ip() share one
    resolver, and so tests can monkeypatch a deterministic resolver.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise SSRFError(f"Could not resolve host {host!r}: {exc}") from None
    if not infos:
        raise SSRFError(f"Could not resolve host {host!r}.")
    return [sockaddr[0] for _, _, _, _, sockaddr in infos]


def _assert_all_public(host: str, ips: list[str]) -> None:
    for ip in ips:
        try:
            if _is_blocked_ip(ip):
                raise SSRFError(
                    f"{host!r} resolves to a non-public address ({ip}); refusing to fetch it."
                )
        except ValueError:
            raise SSRFError(f"{host!r} resolved to an unparseable address ({ip}).") from None


def validate_public_url(url: str) -> None:
    """Raise SSRFError unless every address the host resolves to is a public,
    routable address. A fast pre-check; the connect-time guarantee comes from
    SSRFGuardTransport (see module docstring)."""
    parts = urlsplit(url)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise SSRFError(f"Unsupported URL scheme: {parts.scheme!r}")
    host = parts.hostname
    if not host:
        raise SSRFError("URL has no host.")
    _assert_all_public(host, _resolve(host))


def pick_public_ip(host: str) -> str:
    """Resolve `host`, refuse if *any* resolved address is non-public, and return
    the first address to connect to. Refusing on any private address (rather than
    just picking a public one) means an attacker can't smuggle a private target
    past the guard by padding the record with an extra public answer."""
    ips = _resolve(host)
    _assert_all_public(host, ips)
    return ips[0]


class SSRFGuardTransport(httpx.AsyncBaseTransport):
    """Wraps a real transport so every outbound connection is pinned to an IP
    validated as public at connect time — closing the DNS-rebinding gap that a
    validate-then-connect check leaves open. The original hostname is preserved
    for the Host header (already set on the request) and for TLS SNI / cert
    verification via the `sni_hostname` request extension."""

    def __init__(self, inner: httpx.AsyncBaseTransport | None = None) -> None:
        self._inner = inner or httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        scheme = request.url.scheme
        if scheme not in ALLOWED_SCHEMES:
            raise SSRFError(f"Unsupported URL scheme: {scheme!r}")
        host = request.url.host
        if not host:
            raise SSRFError("URL has no host.")
        ip = pick_public_ip(host)  # raises SSRFError on a non-public target
        # Keep the real hostname for SNI + certificate verification, then pin the
        # connection to the validated IP so no second DNS lookup can divert it.
        request.extensions = {**request.extensions, "sni_hostname": host}
        request.url = request.url.copy_with(host=ip)
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()
