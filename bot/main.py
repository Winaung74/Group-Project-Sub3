from __future__ import annotations

import argparse
import logging
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.config import load_settings
from bot.strategy import MirrorStrategy


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("capitol-mirror-bot")


def run_once() -> None:
    settings = load_settings()
    strategy = MirrorStrategy(settings)
    stats = strategy.run()
    logger.info(
        "Run complete | considered=%s submitted=%s seen=%s filter=%s budget=%s",
        stats.considered,
        stats.submitted,
        stats.skipped_seen,
        stats.skipped_filter,
        stats.skipped_budget,
    )


def run_scheduler() -> None:
    settings = load_settings()
    scheduler = BlockingScheduler(timezone="UTC")
    trigger = CronTrigger.from_crontab(settings.schedule_cron)
    scheduler.add_job(run_once, trigger=trigger, id="mirror_job", max_instances=1, coalesce=True)

    logger.info("Scheduler started (UTC) with cron: %s", settings.schedule_cron)
    scheduler.start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capitol Trades mirror bot (Alpaca paper)")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    args = parser.parse_args(argv)

    if args.once:
        run_once()
    else:
        run_scheduler()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
