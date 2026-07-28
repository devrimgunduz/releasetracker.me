"""Tests for app.repo_url.parse_repo_url.

Pure function, no DB or settings needed — runs standalone:  pytest
"""
import pytest

from app.repo_url import RepoURLError, parse_repo_url

# (url, forge_hint, expected (forge, base_url, owner, name))
OK_CASES = [
    # The canonical example from the UI placeholder.
    (
        "https://github.com/devrimgunduz/passwordcheck_cracklib/",
        "github",
        ("github", "", "devrimgunduz", "passwordcheck_cracklib"),
    ),
    ("https://github.com/prometheus/prometheus", "github", ("github", "", "prometheus", "prometheus")),
    # Scheme-less input.
    ("github.com/cli/cli", "github", ("github", "", "cli", "cli")),
    # Clone URL with .git suffix.
    ("https://github.com/torvalds/linux.git", "github", ("github", "", "torvalds", "linux")),
    # SSH form.
    ("git@github.com:owner/repo.git", "github", ("github", "", "owner", "repo")),
    # Extra path segments after owner/repo are ignored (non-GitLab).
    ("https://github.com/owner/repo/tree/main", "github", ("github", "", "owner", "repo")),
    # www. is stripped for host matching; path case is preserved.
    ("https://WWW.GitHub.com/Owner/Repo", "github", ("github", "", "Owner", "Repo")),
    # GitLab nested subgroups: owner is everything but the last segment.
    ("https://gitlab.com/group/subgroup/project", "github", ("gitlab", "", "group/subgroup", "project")),
    # GitLab '/-/' sub-page path is trimmed.
    ("https://gitlab.com/gitlab-org/gitlab/-/tree/master", "gitlab", ("gitlab", "", "gitlab-org", "gitlab")),
    # Bitbucket.
    ("https://bitbucket.org/team/repo", "github", ("bitbucket", "", "team", "repo")),
    # Codeberg is a public Forgejo -> gitea forge with an explicit base_url.
    ("https://codeberg.org/forgejo/forgejo", "github", ("gitea", "https://codeberg.org", "forgejo", "forgejo")),
    # Self-hosted: forge falls back to the hint, host becomes the base_url.
    ("https://git.mycompany.com/ops/infra", "gitea", ("gitea", "https://git.mycompany.com", "ops", "infra")),
    # Self-hosted keeps the scheme (http) and port.
    ("http://git.local:3000/team/proj", "gitea", ("gitea", "http://git.local:3000", "team", "proj")),
    # SourceForge: single project identifier -> pseudo-owner "sourceforge".
    ("https://sourceforge.net/projects/proftpd/", "github", ("sourceforge", "", "sourceforge", "proftpd")),
    ("https://sourceforge.net/projects/proftpd/files/", "github", ("sourceforge", "", "sourceforge", "proftpd")),
    ("https://sourceforge.net/p/proftpd/", "github", ("sourceforge", "", "sourceforge", "proftpd")),
    # PyPI: single package identifier -> pseudo-owner "pypi".
    ("https://pypi.org/project/requests/", "github", ("pypi", "", "pypi", "requests")),
    ("https://pypi.org/project/requests/2.31.0/", "github", ("pypi", "", "pypi", "requests")),
    ("https://pypi.org/pypi/requests/json", "github", ("pypi", "", "pypi", "requests")),
]


@pytest.mark.parametrize("url,hint,expected", OK_CASES)
def test_parse_ok(url, hint, expected):
    assert parse_repo_url(url, hint) == expected


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "https://github.com/", "https://github.com/onlyowner", "https://"],
)
def test_parse_errors(bad):
    with pytest.raises(RepoURLError):
        parse_repo_url(bad, "github")


def test_known_host_overrides_hint():
    # Dropdown says github, but a gitlab.com URL wins.
    forge, base_url, owner, name = parse_repo_url("https://gitlab.com/a/b", "github")
    assert forge == "gitlab"
    assert base_url == ""


def test_unknown_host_uses_hint_and_captures_base_url():
    forge, base_url, owner, name = parse_repo_url("https://example.org/a/b", "gitlab")
    assert forge == "gitlab"
    assert base_url == "https://example.org"
    assert (owner, name) == ("a", "b")
