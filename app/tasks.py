"""The Celery application, its tasks, and the schedule.

One module, imported by all three services, so the worker and the scheduler
cannot drift from what the web process thinks it is enqueuing.
"""
from __future__ import annotations

import os
import time

from celery import Celery
from celery.schedules import crontab

from .db import connection, migrate

BROKER_URL = os.environ.get("REDIS_URL") or os.environ["CELERY_BROKER_URL"]

celery = Celery("app", broker=BROKER_URL, backend=BROKER_URL)
celery.conf.update(
    task_acks_late=True,
    # Without this a worker that dies mid-task takes the task with it: the
    # message was acknowledged on receipt and nobody will run it again.
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_time_limit=int(os.environ.get("TASK_TIME_LIMIT", 900)),
    task_soft_time_limit=int(os.environ.get("TASK_SOFT_TIME_LIMIT", 870)),
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    beat_schedule={
        "heartbeat": {
            "task": "app.tasks.heartbeat",
            # Every minute, so a fresh deployment shows the scheduler working
            # without anyone having to wait.
            "schedule": crontab(minute="*"),
        }
    },
)


@celery.task(bind=True, name="app.tasks.process", max_retries=3, default_retry_delay=10)
def process(self, job_id: int) -> str:
    """The example task. Replace the body; keep the bookkeeping."""
    with connection() as conn:
        conn.execute(
            "update jobs set status = 'running', attempts = attempts + 1, updated_at = now() where id = %s",
            (job_id,),
        )
        conn.commit()
        row = conn.execute("select payload from jobs where id = %s", (job_id,)).fetchone()

    payload = (row or {}).get("payload") or {}

    try:
        # Stand-in for the real work: something slow enough that doing it inside
        # a web request would be the wrong shape.
        time.sleep(float(payload.get("seconds", 1)))
        if payload.get("fail"):
            raise RuntimeError(payload.get("fail"))
        result = str(payload.get("echo", "done"))
    except Exception as error:  # noqa: BLE001 - the failure is recorded, then re-raised
        with connection() as conn:
            conn.execute(
                "update jobs set status = 'failed', error = %s, updated_at = now() where id = %s",
                (str(error)[:2000], job_id),
            )
            conn.commit()
        raise

    with connection() as conn:
        conn.execute(
            "update jobs set status = 'done', result = %s, error = null, updated_at = now() where id = %s",
            (result[:2000], job_id),
        )
        conn.commit()
    return result


@celery.task(name="app.tasks.heartbeat")
def heartbeat() -> str:
    """Proof that the scheduler is alive - and the pattern for your own periodic work."""
    with connection() as conn:
        conn.execute("insert into heartbeats (source) values ('beat')")
        conn.commit()
    return "ok"


# The worker and the scheduler both start by making sure the schema is there,
# so the order in which the three services come up does not matter.
migrate()
