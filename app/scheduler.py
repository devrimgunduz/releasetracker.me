from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .config import get_settings
from .poller import poll_all, send_daily_summary

log = logging.getLogger("radar.scheduler")


def build_scheduler(first_poll_at: datetime | None = None) -> AsyncIOScheduler:
    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone=settings.timezone)

    # next_run_time=None adds a job *paused* in APScheduler — it never computes a
    # next fire time on its own, so the recurring sweep would never run again
    # after the one-off boot poll. Set it explicitly so the job is actually
    # scheduled, not just deferred.
    #
    # first_poll_at lets the caller (app/worker.py) anchor this to the *actual*
    # last completed sweep instead of always "one interval from right now" —
    # otherwise restarting the worker shortly before its interval elapses both
    # fires a redundant immediate poll AND resets the cadence to the restart
    # time, drifting it further on every restart.
    first_poll = first_poll_at or (
        datetime.now(scheduler.timezone) + timedelta(minutes=settings.poll_interval_minutes)
    )
    scheduler.add_job(
        poll_all,
        IntervalTrigger(minutes=settings.poll_interval_minutes),
        id="poll_all",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
        next_run_time=first_poll,
    )

    scheduler.add_job(
        send_daily_summary,
        CronTrigger(hour=settings.summary_hour, minute=settings.summary_minute),
        id="daily_summary",
        max_instances=1,
        coalesce=True,
    )

    log.info(
        "scheduler configured: poll every %d min, summary at %02d:%02d %s",
        settings.poll_interval_minutes,
        settings.summary_hour,
        settings.summary_minute,
        settings.timezone,
    )
    return scheduler
