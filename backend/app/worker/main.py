"""Worker process entrypoint (docs/decisions.md ADR-007, FR-24).

A small APScheduler `AsyncIOScheduler` running the deterministic proactive
checks that the API cannot run synchronously:

- `scheduled-checks` — every `SCHEDULER_CHECK_INTERVAL_MINUTES` (default 60):
  low-stock scan + forecasted-stockout scan for every business.
- `daily-report` — once a day at `SCHEDULER_DAILY_REPORT_HOUR` UTC (default
  8): publish each business's sales summary as a DAILY_REPORT notification.

This is deliberately NOT a task queue / broker (no Celery/Redis) — the jobs
share the API's codebase and DB, and scale later by swapping the trigger
mechanism, not by a rewrite (ADR-007).

Run: `python -m app.worker.main` (or `python -m app.worker`).
"""

import asyncio
import logging
from collections.abc import AsyncGenerator

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.session import AsyncSessionLocal
from app.services.worker_jobs import generate_daily_report, run_scheduled_checks

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("worker")

settings = get_settings()


async def _session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def _run_scheduled_checks() -> None:
    async for session in _session():
        try:
            counts = await run_scheduled_checks(session)
            logger.info(
                "scheduled checks: %s businesses, %s low-stock, %s stockouts",
                counts["businesses"],
                counts["low_stock"],
                counts["stockouts"],
            )
        except Exception:
            logger.exception("scheduled checks crashed")


async def _run_daily_report() -> None:
    from sqlalchemy import select

    from app.models.business import Business

    async for session in _session():
        rows = (await session.execute(select(Business.id).order_by(Business.id))).all()
        for (business_id,) in rows:
            try:
                summary = await generate_daily_report(session, business_id)
                logger.info("daily report for business %s: %s", business_id, summary)
            except Exception:
                logger.exception("daily report failed for business %s", business_id)


def main() -> None:
    scheduler = AsyncIOScheduler(timezone="UTC")

    scheduler.add_job(
        _run_scheduled_checks,
        IntervalTrigger(minutes=settings.scheduler_check_interval_minutes),
        id="scheduled-checks",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        _run_daily_report,
        CronTrigger(hour=settings.scheduler_daily_report_hour, minute=0, timezone="UTC"),
        id="daily-report",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    logger.info(
        "worker started: checks every %s min, daily report at %02d:00 UTC",
        settings.scheduler_check_interval_minutes,
        settings.scheduler_daily_report_hour,
    )
    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()