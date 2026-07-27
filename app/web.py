"""The web service: accepts work, reports on it, and never does it.

Every handler here returns in milliseconds. That is the whole point of the
shape - the moment a request waits for the work itself, you have a timeout
instead of a queue.
"""
from __future__ import annotations

import json
import os

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .db import connection, migrate
from .tasks import process

API_TOKEN = os.environ.get("API_TOKEN", "")
if len(API_TOKEN) < 16:
    raise SystemExit("API_TOKEN is missing or shorter than 16 characters. Refusing to start an open queue.")

app = FastAPI(title="Queue starter", docs_url=None, redoc_url=None)
migrate()


def authorize(authorization: str = Header(default="")) -> None:
    if authorization != f"Bearer {API_TOKEN}":
        raise HTTPException(status_code=401, detail="unauthorized")


class JobRequest(BaseModel):
    kind: str = Field(default="process", max_length=64)
    payload: dict = Field(default_factory=dict)


@app.post("/jobs", dependencies=[Depends(authorize)], status_code=202)
def enqueue(request: JobRequest) -> dict:
    with connection() as conn:
        row = conn.execute(
            "insert into jobs (kind, payload) values (%s, %s) returning id",
            (request.kind, json.dumps(request.payload)),
        ).fetchone()
        conn.commit()
    job_id = row["id"]

    # The row exists before the message does. The other order loses work: a
    # worker fast enough to pick the message up first finds no row to update.
    async_result = process.delay(job_id)
    with connection() as conn:
        conn.execute("update jobs set task_id = %s where id = %s", (async_result.id, job_id))
        conn.commit()

    return {"id": job_id, "status": "queued"}


@app.get("/jobs/{job_id}", dependencies=[Depends(authorize)])
def job(job_id: int) -> dict:
    with connection() as conn:
        row = conn.execute(
            "select id, kind, status, result, error, attempts, created_at, updated_at from jobs where id = %s",
            (job_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    return row


@app.get("/jobs", dependencies=[Depends(authorize)])
def jobs() -> dict:
    with connection() as conn:
        rows = conn.execute(
            "select id, kind, status, attempts, created_at from jobs order by created_at desc limit 50"
        ).fetchall()
        counts = conn.execute("select status, count(*)::int as n from jobs group by status").fetchall()
    return {"jobs": rows, "counts": {row["status"]: row["n"] for row in counts}}


@app.get("/heartbeats", dependencies=[Depends(authorize)])
def heartbeats() -> dict:
    with connection() as conn:
        rows = conn.execute(
            "select source, noted_at from heartbeats order by noted_at desc limit 20"
        ).fetchall()
    return {"heartbeats": rows}


@app.get("/health")
def health() -> dict:
    with connection() as conn:
        conn.execute("select 1")
    return {"status": "ok"}


@app.get("/")
def index() -> dict:
    return {
        "service": "queue starter",
        "post": "/jobs with {\"payload\": {\"seconds\": 2, \"echo\": \"hello\"}}",
        "note": "every route except /health needs Authorization: Bearer $API_TOKEN",
    }
