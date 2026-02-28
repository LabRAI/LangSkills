from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..config import default_domain_for_topic
from ..queue import QueueSettings, QueueStore
from ..utils.fs import read_json
from ..utils.lang import resolve_output_language
from ..utils.paths import repo_root


def _iter_artifacts(captures_root: Path) -> list[Path]:
    if not captures_root.exists():
        return []
    return sorted(captures_root.rglob("sources/*.json"))


def _resolve_domain(extra: dict, fallback: str = "linux") -> str:
    domain = str(extra.get("domain") or "").strip()
    if domain:
        return domain
    topic = str(extra.get("topic") or "").strip()
    if topic:
        return default_domain_for_topic(topic)
    tags = extra.get("tags") if isinstance(extra.get("tags"), list) else []
    tag_str = " ".join(str(t) for t in tags if str(t))
    if tag_str:
        return default_domain_for_topic(tag_str)
    return fallback


def cli_queue_from_captures(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills queue-from-captures")
    parser.add_argument("--captures", default="captures", help="Root of captures/ (default: captures)")
    parser.add_argument("--queue", default="", help="Queue DB path (default: runs/queue.db)")
    parser.add_argument("--stage", default="preprocess", help="Queue stage to enqueue (default: preprocess)")
    parser.add_argument("--source-type", default="", help="Filter by source_type (comma-separated, optional)")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of artifacts to enqueue (0 = no limit)")
    parser.add_argument("--dry-run", action="store_true")
    ns = parser.parse_args(argv)

    root = repo_root()
    captures_root = Path(str(ns.captures or "")).expanduser()
    if not captures_root.is_absolute():
        captures_root = (root / captures_root).resolve()

    settings = QueueSettings.from_env(repo_root_path=root)
    if ns.queue:
        settings.path = Path(ns.queue)
        if not settings.path.is_absolute():
            settings.path = (root / settings.path).resolve()
    queue = QueueStore(settings.path)
    queue.init_db()

    type_filter: set[str] = set()
    raw_types = str(ns.source_type or "").strip()
    if raw_types:
        type_filter = {t.strip().lower() for t in raw_types.split(",") if t.strip()}

    output_language = resolve_output_language(default="en")
    artifacts = _iter_artifacts(captures_root)
    total = 0
    enqueued = 0
    skipped = 0
    errors = 0

    for path in artifacts:
        if ns.limit and enqueued >= int(ns.limit):
            break
        total += 1
        try:
            data = read_json(path)
        except Exception:
            errors += 1
            continue
        if not isinstance(data, dict):
            skipped += 1
            continue
        source_id = str(data.get("source_id") or "").strip()
        source_type = str(data.get("source_type") or "webpage").strip().lower()
        if type_filter and source_type not in type_filter:
            skipped += 1
            continue
        source_url = str(data.get("url") or "").strip()
        if not source_id or not source_url:
            skipped += 1
            continue
        title = str(data.get("title") or "").strip()
        extra = dict(data.get("extra") if isinstance(data.get("extra"), dict) else {})
        extra["language"] = output_language
        domain = _resolve_domain(extra)
        tags = extra.get("tags") if isinstance(extra.get("tags"), list) else []

        try:
            payload_path = path.relative_to(root).as_posix()
        except Exception:
            payload_path = path.as_posix()

        run_id = ""
        try:
            rel = path.relative_to(captures_root)
            if rel.parts:
                cand = str(rel.parts[0] or "")
                if cand.startswith("run-"):
                    run_id = cand
        except Exception:
            run_id = ""

        if ns.dry_run:
            enqueued += 1
            continue

        res = queue.enqueue(
            source_id=source_id,
            source_type=source_type,
            source_url=source_url,
            source_title=title,
            stage=str(ns.stage or "preprocess"),
            priority=0,
            max_attempts=settings.max_attempts,
            domain=domain,
            tags=tags,
            payload_path=payload_path,
            run_id=run_id or None,
            config_snapshot={
                "requeued_from": "captures",
                "captures_root": captures_root.as_posix(),
            },
            extra=extra,
        )
        if bool(res.get("enqueued")):
            enqueued += 1
        else:
            skipped += 1

    summary = {
        "queue": str(queue.db_path),
        "captures_root": str(captures_root),
        "total_seen": total,
        "enqueued": enqueued,
        "skipped": skipped,
        "errors": errors,
        "dry_run": bool(ns.dry_run),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_queue_from_captures())
