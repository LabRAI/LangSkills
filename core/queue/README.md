# `langskills/queue/`

Persistent queue storage and scheduling for long-running capture workflows.

## What it does

- Stores queued source items and their current stage/status in SQLite (default: `runs/queue.db`).
- Supports leasing, ACK/NACK with backoff, and stage transitions.
- Enables multi-worker processing via `langskills_cli.py runner ...`.

## Key files

- `store.py`: SQLite schema and queue operations (enqueue/lease/ack/nack/requeue/stats).
- `config.py`: queue configuration defaults and environment overrides.

See the root README for the stage flowchart and runner usage: `../../README.md`.
