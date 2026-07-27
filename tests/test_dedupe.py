"""Tests for dashboard version de-duplication (release preferred over tag)."""
from datetime import datetime, timezone

from app.web.releases import dedupe_versions


class _Rel:
    def __init__(self, kind, tag_name, published_at=None, name=""):
        self.kind = kind
        self.tag_name = tag_name
        self.name = name or tag_name
        self.published_at = published_at


def test_release_wins_over_same_version_tag():
    when = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = [
        _Rel("tag", "v1.2.0"),                       # dateless tag
        _Rel("release", "v1.2.0", published_at=when),  # dated release, same version
    ]
    out = dedupe_versions(rows)
    assert len(out) == 1
    assert out[0].kind == "release"
    assert out[0].published_at == when


def test_distinct_versions_all_kept():
    rows = [_Rel("release", "v1.0.0"), _Rel("tag", "v1.1.0")]
    assert len(dedupe_versions(rows)) == 2


def test_tag_only_version_survives():
    rows = [_Rel("tag", "v9.9.9")]
    out = dedupe_versions(rows)
    assert len(out) == 1 and out[0].kind == "tag"


def test_entries_without_version_are_all_kept():
    rows = [_Rel("release", ""), _Rel("release", "")]
    assert len(dedupe_versions(rows)) == 2
