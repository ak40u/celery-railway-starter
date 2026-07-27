# Deploy and Host a Celery Worker Stack on Railway

A web service that answers immediately, a worker that does the slow part, and a scheduler for the work nobody asked for — three services from one image, with Redis as the queue and Postgres as the record of what happened.

Post a job, get an id back in milliseconds, read the outcome when it is ready.

## About Hosting Background Workers

The Queues category of this catalogue holds 55 templates and 2837 installs in total, on a platform where background work is table stakes. The most installed Django-and-Celery template sits at 245 installs with a 64% success rate.

The reason is not that Celery is difficult. It is that the shape is: three processes sharing one codebase, a broker, a database, and settings that agree — and when any part of it is wrong, the failure is quiet. Tasks disappear when a worker restarts, because Celery acknowledges a message on receipt by default. The scheduler runs everything twice because somebody scaled it to two replicas. Nothing writes down what happened, so "did last night's export run?" has no answer anywhere.

This template is that shape, assembled and checked.

## Common Use Cases

- **Anything too slow for a request** — sending mail, rendering a report, processing an upload, calling a third-party API that sometimes takes twenty seconds.
- **Retries that survive a restart.** A task that fails is recorded and retried rather than lost with the container.
- **Periodic work** — the nightly digest, the hourly sync — from the same codebase as everything else, without a separate scheduling product.

## Dependencies for Celery Hosting

### Deployment Dependencies

- Python 3.13, FastAPI and Celery 5.6
- Redis — broker and result backend
- Postgres — the record of every job and its outcome
- [Template source](https://github.com/ak40u/celery-railway-starter)

### Implementation Details

- **The database row is written before the message is published.** The other order loses work: a worker fast enough to pick the message up first finds no row to update.
- **`task_acks_late` with `worker_prefetch_multiplier=1`.** Celery acknowledges on receipt by default, so a worker killed mid-task takes the task with it and nobody ever runs it again. This is the setting that separates a queue from a lottery.
- **Failures are written down before they are re-raised**, so a retry storm still leaves a readable history rather than log lines that scrolled away.
- **The enqueue endpoint is behind a token.** An open one is a way for strangers to spend your worker's CPU.
- **The web service binds `0.0.0.0`, not `::`.** Uvicorn binds an IPv6 socket exclusively; the platform's HTTP proxy connects over IPv4, and the symptom is a 502 while the application logs that it is listening perfectly. (The reverse is true for private-network services, which is what makes this one worth stating.)
- **Redis runs with a password, an append-only file on a volume and dual-stack binding**, because the private network is IPv6 and a broker bound only to IPv4 is unreachable from the worker.
- **One scheduler, always.** Two mean every periodic task happens twice, and nothing in Celery prevents it — the card says so plainly, because it is the most common way a nightly job turns into two invoices.

The repository carries `scripts/verify-queue.sh`, which checks that enqueuing a three-second task returns in under three seconds — the difference between a queue and a slow endpoint — that the worker finishes it, that a task which raises is recorded as failed rather than lost, and that the scheduler produces work with nobody asking. This template was published only after that script passed against a deployment created from the template itself.

## Why Deploy a Celery Worker Stack on Railway?

Railway is a singular platform to deploy your infrastructure stack. Railway will host your infrastructure so you don't have to deal with configuration, while allowing you to vertically and horizontally scale it.

By deploying a Celery worker stack on Railway, you are one step closer to supporting a complete full-stack application with minimal burden. Host your servers, databases, AI agents, and more on Railway.
