from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .config import get_settings
from .poller import poll_all, send_daily_summary

log = logging.getLogger("radar.scheduler")


def build_scheduler() -> AsyncIOScheduler:
    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone=settings.timezone)

    scheduler.add_job(
        poll_all,
        IntervalTrigger(minutes=settings.poll_interval_minutes),
        id="poll_all",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
        next_run_time=None,  # first run scheduled one interval out; call poll_all() at boot separately
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
