"""Run a single job and exit — used by the radarctl helper.

    python -m scripts.run poll       # one poll sweep now
    python -m scripts.run summary    # send the daily digest now
"""
from __future__ import annotations

import asyncio
import sys

from app.poller import poll_all, send_daily_summary, send_test_notifications

JOBS = {
    "poll": poll_all,
    "summary": send_daily_summary,
    "test-telegram": send_test_notifications,
}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in JOBS:
        sys.exit(f"Usage: python -m scripts.run {'|'.join(JOBS)}")
    asyncio.run(JOBS[sys.argv[1]]())


if __name__ == "__main__":
    main()
