from __future__ import annotations

import argparse
import json
import time
import datetime as _dt
from pathlib import Path

from ..queue import QueueSettings, QueueStore
from ..utils.paths import repo_root
from ..utils.fs import list_skill_dirs


def _queue_store_from_args(queue_path: str | None, *, read_only: bool = False) -> QueueStore:
    settings = QueueSettings.from_env()
    path = Path(queue_path) if queue_path else settings.path
    if not path.is_absolute():
        path = (repo_root() / path).resolve()
    return QueueStore(path, read_only=read_only)


def _parse_tags(raw: str | None) -> list[str]:
    s = str(raw or "").strip()
    if not s:
        return []
    return [t.strip() for t in s.split(",") if t.strip()]


def cli_queue_init(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills queue-init")
    parser.add_argument("--queue", default="", help="Queue DB path (default: runs/queue.db)")
    ns = parser.parse_args(argv)
    store = _queue_store_from_args(ns.queue or None)
    store.init_db()
    print(str(store.db_path))
    return 0


def cli_queue_enqueue(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills queue-enqueue")
    parser.add_argument("--queue", default="", help="Queue DB path (default: runs/queue.db)")
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--source-type", default="webpage")
    parser.add_argument("--stage", default="ingest")
    parser.add_argument("--domain", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--tags", default="")
    parser.add_argument("--priority", type=int, default=0)
    parser.add_argument("--max-attempts", type=int, default=0)
    parser.add_argument("--payload-path", default="")
    parser.add_argument("--config-json", default="")
    parser.add_argument("--extra-json", default="")
    ns = parser.parse_args(argv)

    config_snapshot = {}
    if ns.config_json:
        config_snapshot = json.loads(ns.config_json)
    extra = {}
    if ns.extra_json:
        extra = json.loads(ns.extra_json)

    store = _queue_store_from_args(ns.queue or None)
    store.init_db()
    settings = QueueSettings.from_env()
    max_attempts = int(ns.max_attempts or settings.max_attempts)
    result = store.enqueue(
        source_id="",
        source_type=str(ns.source_type),
        source_url=str(ns.source_url),
        source_title=str(ns.title),
        stage=str(ns.stage),
        priority=int(ns.priority or 0),
        max_attempts=max_attempts,
        domain=str(ns.domain or ""),
        tags=_parse_tags(ns.tags),
        payload_path=str(ns.payload_path or ""),
        config_snapshot=config_snapshot,
        extra=extra,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cli_queue_lease(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills queue-lease")
    parser.add_argument("--queue", default="", help="Queue DB path (default: runs/queue.db)")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--stage", action="append", default=[])
    parser.add_argument("--source-type", default="")
    parser.add_argument("--lease-seconds", type=int, default=0)
    parser.add_argument("--worker-id", default="manual")
    ns = parser.parse_args(argv)
    store = _queue_store_from_args(ns.queue or None)
    store.init_db()
    settings = QueueSettings.from_env()
    lease_seconds = int(ns.lease_seconds or settings.lease_seconds)
    items = store.lease_next(
        worker_id=str(ns.worker_id),
        limit=int(ns.limit or 1),
        stages=ns.stage or None,
        source_type=str(ns.source_type or "") or None,
        lease_seconds=lease_seconds,
    )
    print(json.dumps({"count": len(items), "items": items}, ensure_ascii=False, indent=2))
    return 0


def cli_queue_ack(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills queue-ack")
    parser.add_argument("--queue", default="", help="Queue DB path (default: runs/queue.db)")
    parser.add_argument("item_id", type=int)
    ns = parser.parse_args(argv)
    store = _queue_store_from_args(ns.queue or None)
    store.init_db()
    store.ack(int(ns.item_id))
    print(json.dumps({"ack": int(ns.item_id)}, ensure_ascii=False, indent=2))
    return 0


def cli_queue_nack(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills queue-nack")
    parser.add_argument("--queue", default="", help="Queue DB path (default: runs/queue.db)")
    parser.add_argument("item_id", type=int)
    parser.add_argument("--reason", default="error")
    parser.add_argument("--backoff-seconds", type=int, default=0)
    parser.add_argument("--max-attempts", type=int, default=0)
    ns = parser.parse_args(argv)
    store = _queue_store_from_args(ns.queue or None)
    store.init_db()
    settings = QueueSettings.from_env()
    backoff = int(ns.backoff_seconds or settings.backoff_base_seconds)
    max_attempts = int(ns.max_attempts or settings.max_attempts)
    result = store.nack(int(ns.item_id), reason=str(ns.reason), backoff_seconds=backoff, max_attempts=max_attempts)
    print(json.dumps({"item_id": int(ns.item_id), **result}, ensure_ascii=False, indent=2))
    return 0


def cli_queue_requeue(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills queue-requeue")
    parser.add_argument("--queue", default="", help="Queue DB path (default: runs/queue.db)")
    parser.add_argument("item_id", type=int)
    parser.add_argument("--stage", required=True)
    ns = parser.parse_args(argv)
    store = _queue_store_from_args(ns.queue or None)
    store.init_db()
    store.requeue(int(ns.item_id), new_stage=str(ns.stage))
    print(json.dumps({"item_id": int(ns.item_id), "stage": str(ns.stage)}, ensure_ascii=False, indent=2))
    return 0


def cli_queue_stats(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills queue-stats")
    parser.add_argument("--queue", default="", help="Queue DB path (default: runs/queue.db)")
    ns = parser.parse_args(argv)
    store = _queue_store_from_args(ns.queue or None)
    store.init_db()
    stats = store.stats()
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


def _render_queue_stats_table(
    *,
    stats: dict[str, object],
    queue_path: str,
    skills_total: int | None,
    skills_root_label: str,
    skills_published_total: int | None,
    skills_published_label: str,
) -> object:
    try:
        from rich import box
        from rich.table import Table
    except Exception:
        return None

    now = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    table = Table(title=f"Queue Stats: {queue_path}", box=box.ASCII)
    table.add_column("Group")
    table.add_column("Key")
    table.add_column("Count", justify="right")

    table.add_row("updated_at", "", now)
    table.add_row("total", "", str(int(stats.get("total", 0) or 0)))
    if skills_total is not None:
        table.add_row("skills_total", skills_root_label, str(int(skills_total)))
    if skills_published_total is not None:
        table.add_row("skills_published_total", skills_published_label, str(int(skills_published_total)))

    def _add_group(group_key: str, label: str) -> None:
        group = stats.get(group_key)
        if not isinstance(group, dict):
            return
        table.add_section()
        for key in sorted(group.keys()):
            table.add_row(label, str(key or "unknown"), str(int(group.get(key, 0) or 0)))

    _add_group("by_status", "status")
    _add_group("by_stage", "stage")
    _add_group("by_source_type", "source_type")
    _add_group("by_age", "age")

    return table


def cli_queue_watch(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills queue-watch")
    parser.add_argument("--queue", default="", help="Queue DB path (default: runs/queue.db)")
    parser.add_argument("--interval-ms", type=int, default=1000)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--skills-root", default="captures")
    parser.add_argument("--skills-published-root", default="skills/by-skill")
    parser.add_argument("--skills-scan-ms", type=int, default=30000)
    ns = parser.parse_args(argv)

    store = _queue_store_from_args(ns.queue or None)
    store.init_db()
    queue_path = str(store.db_path)
    interval_s = max(0.2, float(ns.interval_ms or 1000) / 1000.0)
    skills_interval_s = max(1.0, float(ns.skills_scan_ms or 30000) / 1000.0)
    root = repo_root()
    skills_root = Path(str(ns.skills_root or "")).expanduser()
    if not skills_root.is_absolute():
        skills_root = (root / skills_root).resolve()
    skills_root_label = str(skills_root.relative_to(root)) if str(skills_root).startswith(str(root)) else str(skills_root)
    published_root = Path(str(ns.skills_published_root or "")).expanduser()
    if not published_root.is_absolute():
        published_root = (root / published_root).resolve()
    published_root_label = (
        str(published_root.relative_to(root)) if str(published_root).startswith(str(root)) else str(published_root)
    )
    skills_total: int | None = None
    skills_published_total: int | None = None
    last_skills_scan = 0.0

    try:
        from rich.console import Console
        from rich.live import Live
    except Exception:
        stats = store.stats()
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return 0

    console = Console()

    def _refresh_skills(now_ts: float) -> None:
        nonlocal last_skills_scan, skills_total, skills_published_total
        if skills_root_label and (now_ts - last_skills_scan) >= skills_interval_s:
            try:
                skills_total = len(list_skill_dirs(skills_root))
            except Exception:
                skills_total = None
            try:
                skills_published_total = len(list_skill_dirs(published_root))
            except Exception:
                skills_published_total = None
            last_skills_scan = now_ts

    def _render() -> object:
        now_ts = time.time()
        _refresh_skills(now_ts)
        stats = store.stats()
        table = _render_queue_stats_table(
            stats=stats,
            queue_path=queue_path,
            skills_total=skills_total,
            skills_root_label=skills_root_label,
            skills_published_total=skills_published_total,
            skills_published_label=published_root_label,
        )
        return table or json.dumps(stats, ensure_ascii=False, indent=2)

    if ns.once:
        console.print(_render())
        return 0

    with Live(_render(), console=console, refresh_per_second=4, transient=False) as live:
        while True:
            live.update(_render())
            time.sleep(interval_s)


def cli_queue_gc(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills queue-gc")
    parser.add_argument("--queue", default="", help="Queue DB path (default: runs/queue.db)")
    parser.add_argument("--no-reclaim", action="store_true")
    ns = parser.parse_args(argv)
    store = _queue_store_from_args(ns.queue or None)
    store.init_db()
    out = store.gc(reclaim_expired=not bool(ns.no_reclaim))
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cli_queue_drain(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills queue-drain")
    parser.add_argument("--queue", default="", help="Queue DB path (default: runs/queue.db)")
    parser.add_argument("--enable", action="store_true")
    parser.add_argument("--disable", action="store_true")
    parser.add_argument("--status", action="store_true")
    ns = parser.parse_args(argv)
    store = _queue_store_from_args(ns.queue or None)
    store.init_db()
    if ns.enable:
        store.set_meta("drain", "1")
    elif ns.disable:
        store.set_meta("drain", "0")
    status = store.is_draining()
    print(json.dumps({"drain": status}, ensure_ascii=False, indent=2))
    return 0
