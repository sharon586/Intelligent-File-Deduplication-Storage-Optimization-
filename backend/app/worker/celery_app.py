from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "dedup",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    task_eager_propagates=True,
    # Fail fast (instead of hanging an API request) when Redis is unreachable.
    task_publish_retry=True,
    task_publish_retry_policy={"max_retries": 2, "interval_start": 0, "interval_step": 0.3, "interval_max": 1},
    broker_transport_options={"socket_connect_timeout": 3, "socket_timeout": 3},
    result_expires=3600,
)
