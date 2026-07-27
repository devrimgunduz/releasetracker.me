"""Tests for Repository.web_url (browser URL derivation)."""
from app.models import Repository


def _repo(**kw):
    kw.setdefault("base_url", "")
    return Repository(owner="acme", name="widget", **kw)


def test_github_public():
    assert _repo(forge_type="github").web_url == "https://github.com/acme/widget"


def test_gitlab_public():
    assert _repo(forge_type="gitlab").web_url == "https://gitlab.com/acme/widget"


def test_bitbucket_public():
    assert _repo(forge_type="bitbucket").web_url == "https://bitbucket.org/acme/widget"


def test_gitea_selfhosted_uses_base_url():
    r = _repo(forge_type="gitea", base_url="https://codeberg.org")
    assert r.web_url == "https://codeberg.org/acme/widget"


def test_selfhosted_github_enterprise():
    r = _repo(forge_type="github", base_url="https://ghe.example.com")
    assert r.web_url == "https://ghe.example.com/acme/widget"


def test_gitea_without_base_url_has_no_link():
    # Self-hosted forge with no known root can't produce a URL.
    assert _repo(forge_type="gitea").web_url == ""
