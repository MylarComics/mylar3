"""
Celery application entry-point for mylar3.

Defines the celery_app instance, configures serialization and result handling,
and registers the beat schedule for automated periodic tasks.

Worker:  celery -A app.worker.celery_app worker --loglevel=info
Beat:    celery -A app.worker.celery_app beat  --loglevel=info
"""
from celery import Celery
from celery.schedules import crontab
from kombu import Queue

from app.core.config import settings

celery_app = Celery(
    "mylar3_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.search_wanted",
        "app.tasks.grab_issue",
        "app.tasks.db_sync",
        "app.tasks.post_process",
        "app.tasks.weekly_pull",
    ],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Tracking & expiry
    task_track_started=True,
    result_expires=3600,  # Results expire after 1 hour

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Queues
    task_default_queue="default",
    task_queues=[
        Queue("default"),
        Queue("grabs"),    # High-priority queue for grab tasks
    ],
    task_routes={
        "tasks.grab_issue": {"queue": "grabs"},
        "tasks.search_wanted": {"queue": "default"},
        "tasks.sync_comic_metadata": {"queue": "default"},
    },

    # Beat schedule — driven by settings for easy user control
    beat_schedule={
        "search-wanted-issues": {
            "task": "tasks.search_wanted",
            "schedule": settings.SEARCH_INTERVAL_MINUTES * 60,  # seconds
            "options": {"queue": "default"},
        },
        "sync-weekly-pull-list": {
            "task": "tasks.sync_weekly_pull_list",
            "schedule": crontab(hour=0, minute=0), # daily at midnight
            "options": {"queue": "default"},
        },
    },
)

import asyncio
from celery.signals import worker_process_init, worker_process_shutdown

_loop = None

@worker_process_init.connect
def init_worker_process(*args, **kwargs):
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

@worker_process_shutdown.connect
def shutdown_worker_process(*args, **kwargs):
    global _loop
    if _loop:
        try:
            _loop.close()
        except Exception:
            pass

def run_async(coro):
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop.run_until_complete(coro)
