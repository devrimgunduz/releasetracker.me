from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .config import get_settings
from .poller import poll_all, send_daily_summary

log = logging.getLogger("radar.scheduler")


def build_scheduler() -> AsyncIOScheduler:
    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone=settings.timezone)

    # next_run_time=None adds a job *paused* in APScheduler — it never computes a
    # next fire time on its own, so the recurring sweep would never run again
    # after the one-off boot poll. Set it explicitly to one interval from now so
    # the job is actually scheduled, not just deferred.
    first_poll = datetime.now(scheduler.timezone) + timedelta(minutes=settings.poll_interval_minutes)
    scheduler.add_job(
        poll_all,
        IntervalTrigger(minutes=settings.poll_interval_minutes),
        id="poll_all",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
        next_run_time=first_poll,  # boot triggers one sweep separately; this is the first recurring one
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
