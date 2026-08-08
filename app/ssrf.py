"""Outbound-URL validation to stop the poller being used as an SSRF pivot.

Every repository `base_url` (and, for known forges, the API base) is fetched
periodically and unattended by the worker. Without this check, a low-privilege
user could register a URL pointing at loopback, link-local (incl. cloud
metadata endpoints like 169.254.169.254), or other private-network addresses
and have the worker poll it forever — or, worse, ride along with a
credential attached (see poller._poll_repo's GitHub-token handling).

This is deliberately a *connect-time* check: it resolves the hostname and
inspects the actual IP(s) the connection would use, not just the string in
the URL, so it isn't fooled by a hostname that merely looks external.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

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


def validate_public_url(url: str) -> None:
    """Raise SSRFError unless every address the host resolves to is a public,
    routable address. Call this before *every* outbound request the poller
    makes, including after following each redirect hop."""
    parts = urlsplit(url)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise SSRFError(f"Unsupported URL scheme: {parts.scheme!r}")
    host = parts.hostname
    if not host:
        raise SSRFError("URL has no host.")

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise SSRFError(f"Could not resolve host {host!r}: {exc}") from None

    if not infos:
        raise SSRFError(f"Could not resolve host {host!r}.")

    for family, _, _, _, sockaddr in infos:
        ip = sockaddr[0]
        try:
            if _is_blocked_ip(ip):
                raise SSRFError(
                    f"{host!r} resolves to a non-public address ({ip}); refusing to fetch it."
                )
        except ValueError:
            raise SSRFError(f"{host!r} resolved to an unparseable address ({ip}).") from None
