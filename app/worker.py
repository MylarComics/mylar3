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
    },
)
