"""
Celery app for InSAR async tasks. Uses Redis as broker and result backend.
"""
from celery import Celery
import os

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)

app = Celery(
    "insar_tasks",
    broker=REDIS_URL,
    backend=RESULT_BACKEND,
    include=["backend.app.tasks"],
)
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600 * 6,  # 6 hours max per task
    worker_prefetch_multiplier=1,
)
