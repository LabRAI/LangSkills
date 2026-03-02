from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ..queue import QueueSettings, QueueStore
from ..utils.fs import ensure_dir


def load_topics(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Topics file not found: {path}")
    if path.suffix.lower() in {".json"}:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("topics") if isinstance(data, dict) else data
    from ..utils.yaml_lite import safe_load_yaml_text

    data = safe_load_yaml_text(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data.get("topics") or []
    return data or []


def cli_topics_capture(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills-rai topics-capture")
    parser.add_argument("--topics-file", default="topics/topics.yaml")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of topics (0 = all)")
    parser.add_argument("--queue", default="", help="Queue DB path (default: runs/queue.db)")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    from ..env import load_dotenv
    from ..llm.factory import create_llm_from_env
    from ..scripts.runner import _discover_tasks
    from ..skills.generate import classify_domain_by_llm
    from ..config import DOMAIN_CONFIG

    load_dotenv(repo_root)
    llm = create_llm_from_env(provider_override=None)
    offline = str(os.environ.get("LANGSKILLS_OFFLINE") or "").strip() == "1"
    if offline:
        raise RuntimeError("Offline mode is disabled; remove LANGSKILLS_OFFLINE.")

    settings = QueueSettings.from_env(repo_root_path=repo_root)
    if args.queue:
        settings.path = Path(args.queue)
    if not settings.path.is_absolute():
        settings.path = (repo_root / settings.path).resolve()
    queue = QueueStore(settings.path)
    queue.init_db()

    topics_path = Path(args.topics_file)
    if not topics_path.is_absolute():
        topics_path = repo_root / topics_path
    topics = load_topics(topics_path)
    if not isinstance(topics, list):
        raise RuntimeError("Invalid topics file format")

    n_limit = int(args.limit or 0)
    picked = topics[:n_limit] if n_limit > 0 else topics

    all_names = sorted(DOMAIN_CONFIG.keys())

    for t in picked:
        tags: list[str] | None = None
        profile: str | None = None
        if isinstance(t, dict):
            topic_str = str(t.get("topic") or "").strip()
            tags = t.get("tags") if isinstance(t.get("tags"), list) else None
            profile = str(t.get("profile") or t.get("domain") or "").strip() or None
        else:
            topic_str = str(t).strip()
        if not topic_str:
            continue
        if profile and profile in all_names:
            domains_for_topic = [profile]
        else:
            picked_domain = classify_domain_by_llm(topic=topic_str, domains=all_names, llm=llm)
            domains_for_topic = [picked_domain]
        _discover_tasks(
            domains=domains_for_topic,
            topic_override=topic_str,
            topic_tags=tags or [],
            queue=queue,
            repo_root=repo_root,
            max_attempts=settings.max_attempts,
        )

    ensure_dir(repo_root / "runs")
    stats = queue.stats()
    (repo_root / "runs" / "topics_runs.json").write_text(json.dumps({"queue": str(queue.db_path), "stats": stats}, ensure_ascii=False, indent=2))
    print(json.dumps({"queue": str(queue.db_path), "stats": stats}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_topics_capture())
