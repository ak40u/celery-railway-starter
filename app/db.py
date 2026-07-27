"""Database access and schema.

The queue lives in Redis; the *record* of what happened lives here. Redis
forgets a finished task almost immediately, and "did the export actually run?"
is a question you ask hours later.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ["DATABASE_URL"]

SCHEMA = """
create table if not exists jobs (
  id           bigserial primary key,
  task_id      text unique,
  kind         text not null,
  payload      jsonb not null default '{}'::jsonb,
  status       text not null default 'queued'
               check (status in ('queued', 'running', 'done', 'failed')),
  result       text,
  error        text,
  attempts     integer not null default 0,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create index if not exists jobs_status_created_idx on jobs (status, created_at desc);

create table if not exists heartbeats (
  id           bigserial primary key,
  source       text not null,
  noted_at     timestamptz not null default now()
);

create index if not exists heartbeats_source_time_idx on heartbeats (source, noted_at desc);
"""


@contextmanager
def connection():
    # A connection per unit of work rather than a pool: web, worker and
    # scheduler are separate processes here, and each does little enough that a
    # pool would add moving parts without adding throughput.
    with psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10) as conn:
        yield conn


def migrate() -> None:
    with connection() as conn:
        conn.execute(SCHEMA)
