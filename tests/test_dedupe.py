"""Tests for dashboard version de-duplication (release preferred over tag)."""
from datetime import datetime, timedelta, timezone

from app.web.releases import dedupe_versions, release_sort_key


class _Rel:
    def __init__(self, kind, tag_name, published_at=None, name="", discovered_at=None):
        self.kind = kind
        self.tag_name = tag_name
        self.name = name or tag_name
        self.published_at = published_at
        self.discovered_at = discovered_at or datetime(2024, 1, 1, tzinfo=timezone.utc)


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


def test_dateless_entries_sort_by_discovery_recency():
    # osdldbt/dbttools-style repo: GitHub tags with no published_at at all, so
    # published_at can't break the tie. The most recently discovered tag
    # (the actual newest release) must not get stuck behind older ones just
    # because they all share the same "no date" sentinel.
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    old1 = _Rel("tag", "v0.1.0", discovered_at=base)
    old2 = _Rel("tag", "v0.5.1", discovered_at=base + timedelta(days=9))
    newest = _Rel("tag", "v0.5.2", discovered_at=base + timedelta(days=13))
    out = sorted([old1, old2, newest], key=release_sort_key, reverse=True)
    assert out[0] is newest


def test_dated_entries_still_outrank_dateless_ones():
    dated = _Rel("release", "v1.0.0", published_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
    dateless_newer = _Rel("tag", "v1.1.0", discovered_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    out = sorted([dateless_newer, dated], key=release_sort_key, reverse=True)
    assert out[0] is dated


def test_dateless_entries_sort_by_version_not_discovery_order():
    # acassen/keepalived-style repo: a first-run backfill discovers a whole batch
    # of dateless tags in one sweep. If the provider handed them back
    # newest-first, processing order (and so discovered_at) ends up *inverted*
    # relative to version order. Version number must win over that artifact.
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    newest = _Rel("tag", "v2.4.3", discovered_at=base)  # processed first, earliest timestamp
    middle = _Rel("tag", "v2.1.0", discovered_at=base + timedelta(seconds=1))
    oldest = _Rel("tag", "v2.0.15", discovered_at=base + timedelta(seconds=2))  # processed last
    out = sorted([oldest, middle, newest], key=release_sort_key, reverse=True)
    assert [r.tag_name for r in out] == ["v2.4.3", "v2.1.0", "v2.0.15"]


def test_unparsable_version_falls_back_to_discovery_recency():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    older = _Rel("tag", "nightly-build", discovered_at=base)
    newer = _Rel("tag", "latest", discovered_at=base + timedelta(days=1))
    out = sorted([older, newer], key=release_sort_key, reverse=True)
    assert out[0] is newer
