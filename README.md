# Celery worker starter for Railway

A web service that answers immediately, a worker that does the slow part, and a
scheduler for the work nobody asked for — as three services from one image, with
Redis as the queue and Postgres as the record.

## Why this exists

Search the catalogue for a Django and Celery template and you find one at 245
installs with a 64% success rate. The whole Queues category is 55 templates and
2837 installs, on a platform where background work is table stakes.

The reason is not that Celery is hard. It is that the shape is: three processes
that must share code, a broker, a database, and settings that agree — and if any
of that is wrong, the failure is quiet. Tasks vanish when a worker restarts. The
scheduler runs twice because it was accidentally scaled to two replicas. Nothing
records what happened, so "did the export run?" has no answer.

## The shape

```
POST /jobs ──▶ row in Postgres ──▶ message in Redis
                                        │
                                     Worker picks it up
                                        └──▶ updates the row: done or failed

Scheduler ──▶ periodic task ──▶ its own row, every minute
```

One image, three start commands:

| Service | Command |
|---------|---------|
| API | `uvicorn app.web:app --host 0.0.0.0 --port 8080` |
| Worker | `celery -A app.tasks.celery worker --concurrency=2` |
| Scheduler | `celery -A app.tasks.celery beat` |

## Try it

```bash
curl -X POST https://your-api.up.railway.app/jobs \
  -H "authorization: Bearer $API_TOKEN" -H 'content-type: application/json' \
  -d '{"payload":{"seconds":5,"echo":"hello"}}'
# -> {"id": 1, "status": "queued"}   (returns at once, not in five seconds)

curl https://your-api.up.railway.app/jobs/1 -H "authorization: Bearer $API_TOKEN"
```

`GET /jobs` lists the recent ones with counts by status; `GET /heartbeats` shows
the scheduler's own work.

## Prove it works

```bash
scripts/verify-queue.sh https://your-api.up.railway.app 'the-token'
```

It checks that enqueuing a three-second task returns in under three seconds —
the difference between a queue and a slow endpoint — that the worker finishes
it, that a task which raises is **recorded as failed** rather than lost, and
that the scheduler produces work on its own.

## Decisions worth knowing

- **The database row is written before the message.** The other order loses
  work: a worker fast enough to pick the message up first finds no row to
  update.
- **`task_acks_late` with `prefetch_multiplier=1`.** By default Celery
  acknowledges a message on receipt, so a worker that dies mid-task takes the
  task with it and nobody runs it again.
- **Failures are written down before they are re-raised**, so a retry storm
  still leaves you with a readable history.
- **The queue is behind a token.** An open enqueue endpoint is a way for
  strangers to spend your worker's CPU.
- **Bind the web service on `0.0.0.0`, not `::`.** Uvicorn binds an IPv6 socket
  exclusively; the platform's HTTP proxy connects over IPv4, and the symptom is
  a 502 while the application logs that it is listening perfectly.

## Configuration

| Variable | Where | Purpose |
|----------|-------|---------|
| `DATABASE_URL` | all three | Postgres — the record of what ran |
| `REDIS_URL` | all three | The broker and result backend |
| `API_TOKEN` | api | Bearer token. At least 16 characters |
| `TASK_TIME_LIMIT` / `TASK_SOFT_TIME_LIMIT` | worker | Hard and soft ceilings, 900s and 870s |

## Scaling

Add replicas to the worker; the queue distributes. Add replicas to the API; it
holds nothing.

**Never run more than one scheduler.** Two schedulers mean every periodic task
happens twice, and Celery does not prevent it — this is the single most common
way a nightly job turns into two invoices.

## Making it yours

`app/tasks.py` holds the example task. Replace its body, keep the bookkeeping
around it, and add your own `beat_schedule` entries. `app/web.py` is where the
routes live; the enqueue path is six lines.

## License

MIT
