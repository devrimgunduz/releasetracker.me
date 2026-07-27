"""Background worker: owns the poll + summary schedule.

Run separately from the web server so it stays a single instance even if the web
tier scales to multiple uvicorn workers:

    python -m app.worker
"""
from __future__ import annotations

import asyncio
import logging
import signal

from .poller import poll_all
from .scheduler import build_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("radar.worker")


async def main() -> None:
    scheduler = build_scheduler()
    scheduler.start()

    # Kick off one sweep immediately at boot instead of waiting a full interval.
    asyncio.create_task(poll_all())

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
