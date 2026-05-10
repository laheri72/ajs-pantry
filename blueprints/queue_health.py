"""RQ queue health helpers used by admin diagnostics and import polling."""
from __future__ import annotations

import os
from datetime import datetime, timezone

from flask import current_app
from redis import Redis

try:
    from rq import Worker
    from rq.registry import DeferredJobRegistry, FailedJobRegistry, StartedJobRegistry
except Exception:  # pragma: no cover - lets app boot without RQ installed
    Worker = None
    DeferredJobRegistry = FailedJobRegistry = StartedJobRegistry = None


QUEUE_NAME = "ajs_pantry_tasks"


def _utcnow():
    return datetime.now(timezone.utc)


def _as_aware(value):
    if not value:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _age_seconds(value):
    value = _as_aware(value)
    if not value:
        return None
    return max(0, int((_utcnow() - value).total_seconds()))


def _redis_connection():
    queue = getattr(current_app, "task_queue", None)
    if queue and getattr(queue, "connection", None):
        return queue.connection

    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        return None
    return Redis.from_url(redis_url)


def _registry_count(registry_class, queue, connection):
    if not registry_class:
        return 0
    try:
        return registry_class(queue.name, connection=connection).count
    except Exception:
        return 0


def _job_error(job):
    result = getattr(job, "result", None)
    if isinstance(result, dict) and result.get("error"):
        return result["error"]

    exc_info = getattr(job, "exc_info", None)
    if exc_info:
        lines = [line.strip() for line in exc_info.splitlines() if line.strip()]
        if lines:
            return lines[-1]
    return None


def _serialize_failed_job(job):
    ended_at = _as_aware(getattr(job, "ended_at", None))
    return {
        "id": job.id,
        "description": getattr(job, "description", None),
        "error": _job_error(job),
        "ended_at": ended_at.isoformat() if ended_at else None,
        "ended_age_seconds": _age_seconds(ended_at),
    }


def _recent_failed_jobs(queue, connection, limit=5):
    if not FailedJobRegistry:
        return []

    try:
        registry = FailedJobRegistry(queue.name, connection=connection)
        jobs = []
        for job_id in registry.get_job_ids(start=0, end=limit - 1, desc=True):
            job = queue.fetch_job(job_id)
            if job:
                jobs.append(_serialize_failed_job(job))
        return jobs
    except Exception:
        return []


def _worker_queue_names(worker):
    names = getattr(worker, "queue_names", None)
    if callable(names):
        names = names()
    if names is not None:
        return list(names)

    queues = getattr(worker, "queues", None) or []
    if callable(queues):
        queues = queues()
    return [getattr(queue, "name", str(queue)) for queue in queues]


def _queue_job_ids(queue):
    job_ids = getattr(queue, "job_ids", None)
    if callable(job_ids):
        return job_ids()
    if job_ids is not None:
        return list(job_ids)

    get_job_ids = getattr(queue, "get_job_ids", None)
    if callable(get_job_ids):
        return get_job_ids()
    return []


def _serialize_worker(worker):
    last_heartbeat = _as_aware(getattr(worker, "last_heartbeat", None))
    state = getattr(worker, "state", None)
    return {
        "name": getattr(worker, "name", None),
        "state": getattr(state, "value", str(state)) if state is not None else None,
        "queues": _worker_queue_names(worker),
        "last_heartbeat": last_heartbeat.isoformat() if last_heartbeat else None,
        "last_heartbeat_age_seconds": _age_seconds(last_heartbeat),
    }


def get_queue_health():
    """Return operational health for the app's RQ queue."""
    redis_url_configured = bool(os.environ.get("REDIS_URL"))
    queue = getattr(current_app, "task_queue", None)

    health = {
        "healthy": False,
        "redis_url_configured": redis_url_configured,
        "redis_connected": False,
        "queue_configured": bool(queue),
        "queue_name": getattr(queue, "name", QUEUE_NAME),
        "queue_length": None,
        "started_count": 0,
        "failed_count": 0,
        "deferred_count": 0,
        "worker_count": 0,
        "workers": [],
        "recent_failed_jobs": [],
        "oldest_queued_job_age_seconds": None,
        "error": None,
    }

    if not queue:
        health["error"] = "RQ queue is not configured for this Flask process."
        return health

    if Worker is None:
        health["error"] = "RQ is not installed."
        return health

    try:
        connection = _redis_connection()
        if not connection:
            health["error"] = "REDIS_URL is not configured."
            return health

        connection.ping()
        health["redis_connected"] = True
        health["queue_length"] = len(queue)
        health["started_count"] = _registry_count(StartedJobRegistry, queue, connection)
        health["failed_count"] = _registry_count(FailedJobRegistry, queue, connection)
        health["deferred_count"] = _registry_count(DeferredJobRegistry, queue, connection)

        workers = Worker.all(connection=connection, queue=queue)
        health["workers"] = [_serialize_worker(worker) for worker in workers]
        health["worker_count"] = len(health["workers"])
        health["recent_failed_jobs"] = _recent_failed_jobs(queue, connection)

        queued_ids = _queue_job_ids(queue)
        if queued_ids:
            oldest_job = queue.fetch_job(queued_ids[0])
            health["oldest_queued_job_age_seconds"] = _age_seconds(
                getattr(oldest_job, "enqueued_at", None) or getattr(oldest_job, "created_at", None)
            )

        health["healthy"] = health["redis_connected"] and health["worker_count"] > 0
        if not health["healthy"]:
            health["error"] = "No active RQ workers are registered for ajs_pantry_tasks."
    except Exception as exc:
        health["error"] = str(exc)

    return health


def active_worker_count():
    return get_queue_health().get("worker_count", 0)


def job_age_seconds(job):
    return _age_seconds(getattr(job, "enqueued_at", None) or getattr(job, "created_at", None))


def job_started_age_seconds(job):
    return _age_seconds(getattr(job, "started_at", None))
