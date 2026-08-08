from datetime import datetime, timedelta, timezone

from app.worker import plan_boot_poll

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
INTERVAL = timedelta(minutes=30)


def test_polls_immediately_when_never_polled():
    poll_now, first_poll_at = plan_boot_poll(None, NOW, INTERVAL)
    assert poll_now is True
    assert first_poll_at is None  # let the scheduler default to now + interval


def test_polls_immediately_when_overdue():
    last = NOW - timedelta(minutes=45)  # older than the interval
    poll_now, first_poll_at = plan_boot_poll(last, NOW, INTERVAL)
    assert poll_now is True
    assert first_poll_at is None


def test_polls_immediately_when_exactly_at_interval_boundary():
    last = NOW - INTERVAL  # exactly due
    poll_now, first_poll_at = plan_boot_poll(last, NOW, INTERVAL)
    assert poll_now is True


def test_skips_boot_poll_when_recently_polled():
    # e.g. a restart 5 minutes into a 30-minute interval
    last = NOW - timedelta(minutes=5)
    poll_now, first_poll_at = plan_boot_poll(last, NOW, INTERVAL)
    assert poll_now is False
    assert first_poll_at == last + INTERVAL  # keeps the original cadence, not now + interval


def test_next_poll_anchor_is_always_in_the_future_when_skipping():
    last = NOW - timedelta(seconds=1)  # restarted almost immediately
    poll_now, first_poll_at = plan_boot_poll(last, NOW, INTERVAL)
    assert poll_now is False
    assert first_poll_at > NOW
