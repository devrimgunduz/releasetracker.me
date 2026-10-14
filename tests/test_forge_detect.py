"""resolve_repo_url: forge auto-detection and the webindex fallback."""
import asyncio

import pytest

from app import forge_detect
from app.repo_url import RepoURLError


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr(forge_detect, "validate_public_url", lambda url: None)


def _detect_returns(monkeypatch, value):
    async def fake(base_url, client=None):
        return value

    monkeypatch.setattr(forge_detect, "detect_forge", fake)


def _resolve(url, hint="auto"):
    return asyncio.run(forge_detect.resolve_repo_url(url, hint))


def test_deep_path_falls_back_to_webindex(monkeypatch):
    _detect_returns(monkeypatch, None)
    forge, base_url, owner, name = _resolve("https://www.haproxy.org/download/3.4/src/")
    assert forge == "webindex"
    assert base_url == "https://www.haproxy.org/download/3.4/src/"
    assert owner == "www.haproxy.org"


def test_bare_owner_repo_on_unknown_host_is_rejected(monkeypatch):
    _detect_returns(monkeypatch, None)
    with pytest.raises(RepoURLError, match="Couldn't detect the forge"):
        _resolve("https://git.example.com/owner/repo")


def test_shallow_listing_is_rejected(monkeypatch):
    _detect_returns(monkeypatch, None)
    with pytest.raises(RepoURLError):
        _resolve("https://example.org/downloads/")


def test_detected_forge_wins_over_webindex_fallback(monkeypatch):
    _detect_returns(monkeypatch, "gitlab")
    forge, base_url, owner, name = _resolve("https://git.example.com/group/sub/project")
    assert (forge, base_url, owner, name) == (
        "gitlab", "https://git.example.com", "group/sub", "project"
    )


def test_explicit_hint_skips_detection(monkeypatch):
    async def boom(base_url, client=None):
        raise AssertionError("should not probe")

    monkeypatch.setattr(forge_detect, "detect_forge", boom)
    forge, base_url, _, _ = _resolve("https://www.haproxy.org/download/3.4/src/", "webindex")
    assert forge == "webindex"
