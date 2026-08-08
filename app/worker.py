"""Background worker: owns the poll + summary schedule.

Run separately from the web server so it stays a single instance even if the web
tier scales to multiple uvicorn workers:

    python -m app.worker
"""
from __future__ import annotations

import asyncio
import logging
import signal
from datetime import datetime, timedelta, timezone

from .config import get_settings
from .poller import last_sweep_at, poll_all
from .scheduler import build_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("radar.worker")


def plan_boot_poll(
    last: datetime | None, now: datetime, interval: timedelta
) -> tuple[bool, datetime | None]:
    """Decide whether to fire an immediate boot poll, and what to anchor the
    next scheduled sweep to. Pure function (no I/O) so the decision itself is
    easy to unit test independent of the scheduler/DB/event loop.

    Returns (poll_immediately, first_poll_at):
    - never polled, or already overdue -> (True, None) — sweep now; let the
      scheduler default to one interval from now for the next one.
    - polled recently (e.g. we're just restarting) -> (False, last + interval)
      — skip the redundant sweep and keep the existing cadence.
    """
    if last is None or now - last >= interval:
        return True, None
    return False, last + interval


async def main() -> None:
    settings = get_settings()
    interval = timedelta(minutes=settings.poll_interval_minutes)
    now = datetime.now(timezone.utc)

    # Decide whether to fire the "poll immediately at boot" sweep, or whether a
    # previous process (before a restart) already polled recently enough that
    # doing so again now would just be a redundant, out-of-cadence sweep.
    #
    # Falls back to the old "always poll immediately" behaviour if the check
    # itself fails (e.g. DB not reachable yet) — poll_all() will hit the same
    # DB and fail the same way regardless, so there's nothing to protect by
    # skipping it here.
    try:
        last = await last_sweep_at()
    except Exception:
        log.exception("could not determine last sweep time; polling immediately as before")
        last = None

    poll_now, first_poll_at = plan_boot_poll(last, now, interval)
    if poll_now:
        asyncio.create_task(poll_all())
    else:
        log.info(
            "skipping boot poll — last sweep was %s ago; next sweep due at %s",
            now - last, first_poll_at,
        )

    scheduler = build_scheduler(first_poll_at=first_poll_at)
    scheduler.start()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    log.info("worker started")
    await stop.wait()
    log.info("worker shutting down")
    scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
