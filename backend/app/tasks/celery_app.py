from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "nexusflow",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.orchestration"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    task_time_limit=settings.celery_task_time_limit,
    task_soft_time_limit=settings.celery_task_soft_time_limit,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

celery_app.autodiscover_tasks(["app.tasks"])
