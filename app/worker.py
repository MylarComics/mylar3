from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "mylar3_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

celery_app.conf.update(
    task_track_started=True,
    timezone="UTC"
)

@celery_app.task(name="test_task")
def test_task():
    return "Celery is working!"
