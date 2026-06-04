from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bookmarks_organizer.sync_service import BookmarkSyncService


def build_scheduler(
    sync_service: BookmarkSyncService,
    *,
    day_of_week: str,
    hour: int,
    minute: int,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        sync_service.sync_new_bookmarks,
        trigger=CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute),
        id="weekly-bookmark-sync",
        replace_existing=True,
    )
    return scheduler
