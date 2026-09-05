"""Tests for the GitHub-issue notifier's message formatting."""
from app.notifiers.github_issue import format_issue


def test_release_formats_title_and_body():
    title, body = format_issue(
        "postgres/postgres", "github", "release", "PostgreSQL 18.1", "REL_18_1",
        "https://github.com/postgres/postgres/releases/tag/REL_18_1",
    )
    assert title == "Package request: postgres/postgres REL_18_1"
    assert "**postgres/postgres** (github)" in body
    assert "**Name:** PostgreSQL 18.1" in body
    assert "**Tag:** `REL_18_1`" in body
    assert "https://github.com/postgres/postgres/releases/tag/REL_18_1" in body


def test_tag_only_uses_tag_as_version_and_skips_redundant_name():
    title, body = format_issue("owner/repo", "gitea", "tag", "v2.0.0", "v2.0.0", "")
    assert title == "Package request: owner/repo v2.0.0"
    assert "**Name:**" not in body  # name == tag, nothing extra to say
    assert "**Link:**" not in body  # no url


def test_backticks_in_tag_do_not_break_the_code_span():
    _, body = format_issue("owner/repo", "github", "tag", "", "v1`; DROP", "")
    assert "`v1'; DROP`" in body
