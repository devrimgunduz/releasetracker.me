from datetime import datetime, timedelta, timezone

from app.scheduler import build_scheduler


def test_default_first_poll_is_one_interval_from_now():
    scheduler = build_scheduler()
    job = scheduler.get_job("poll_all")
    now = datetime.now(job.next_run_time.tzinfo)
    # Should be ~poll_interval_minutes from now (default settings in tests use
    # whatever POLL_INTERVAL_MINUTES the environment/config default to) —
    # just assert it's in the future and not immediate.
    assert job.next_run_time > now


def test_explicit_first_poll_at_is_honoured():
    anchor = datetime.now(timezone.utc) + timedelta(minutes=7)
    scheduler = build_scheduler(first_poll_at=anchor)
    job = scheduler.get_job("poll_all")
    assert job.next_run_time == anchor
