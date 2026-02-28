from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ..config import canonicalize_source_url, default_domain_for_topic
from ..queue import QueueSettings, QueueStore
from ..sources.artifacts import write_source_artifact
from ..utils.fs import ensure_dir
from ..utils.hashing import sha256_hex
from ..utils.paths import repo_root


def _queue_store(queue_path: str | None) -> QueueStore:
    settings = QueueSettings.from_env()
    path = Path(queue_path) if queue_path else settings.path
    if not path.is_absolute():
        path = (repo_root() / path).resolve()
    return QueueStore(path)


def _strip_query(url: str) -> str:
    u = str(url or "").strip()
    if not u:
        return ""
    try:
        parts = urlsplit(u)
    except Exception:
        return u
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))  # drop query+fragment


def _run_id_from_input(*, platform: str, input_path: Path) -> str:
    stem = str(input_path.stem or "").strip()
    return f"import-{platform}-{stem}" if stem else f"import-{platform}"


def _format_text(*, platform: str, item: dict[str, Any]) -> str:
    title = str(item.get("title") or "").strip()
    desc = str(item.get("desc") or "").strip()
    if platform == "zhihu":
        content_text = str(item.get("content_text") or "").strip()
        parts = [p for p in [title, desc, content_text] if p]
        return "\n\n".join(parts).strip()

    # xhs
    tag_list = str(item.get("tag_list") or "").strip()
    tags = [t.strip() for t in tag_list.split(",") if t.strip()]
    parts: list[str] = []
    if title:
        parts.append(title)
    if desc:
        parts.append(desc)
    if tags:
        parts.append("Tags: " + ", ".join(tags))
    return "\n\n".join(parts).strip()


def _tags_from_item(*, platform: str, item: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    kw = str(item.get("source_keyword") or "").strip()
    if kw:
        tags.append(kw)
    if platform == "xhs":
        tag_list = str(item.get("tag_list") or "").strip()
        tags.extend([t.strip() for t in tag_list.split(",") if t.strip()])
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _artifact_source_url(*, platform: str, item: dict[str, Any]) -> str:
    if platform == "zhihu":
        return str(item.get("content_url") or "").strip()
    # XHS: keep a stable URL without xsec_token/xsec_source query params.
    return _strip_query(str(item.get("note_url") or "").strip())


def _artifact_extra(*, platform: str, item: dict[str, Any], input_path: Path, index: int) -> dict[str, Any]:
    common = {
        "import_source": "LittleCrawler",
        "import_file": input_path.as_posix(),
        "import_index": int(index),
        "source_keyword": str(item.get("source_keyword") or "").strip(),
        "last_modify_ts": item.get("last_modify_ts"),
    }

    if platform == "zhihu":
        return {
            **common,
            "content_id": str(item.get("content_id") or "").strip(),
            "content_type": str(item.get("content_type") or "").strip(),
            "question_id": str(item.get("question_id") or "").strip(),
            "user_id": str(item.get("user_id") or "").strip(),
            "user_nickname": str(item.get("user_nickname") or "").strip(),
            "voteup_count": item.get("voteup_count"),
            "comment_count": item.get("comment_count"),
            "created_time": item.get("created_time"),
            "updated_time": item.get("updated_time"),
        }

    # xhs
    original_note_url = str(item.get("note_url") or "").strip()
    safe_item = dict(item)
    safe_item.pop("xsec_token", None)
    safe_item["note_url"] = _strip_query(original_note_url)
    return {
        **common,
        "note_id": str(item.get("note_id") or "").strip(),
        "note_url_raw": original_note_url,
        "user_id": str(item.get("user_id") or "").strip(),
        "nickname": str(item.get("nickname") or "").strip(),
        "type": str(item.get("type") or "").strip(),
        "ip_location": str(item.get("ip_location") or "").strip(),
        "liked_count": item.get("liked_count"),
        "collected_count": item.get("collected_count"),
        "comment_count": item.get("comment_count"),
        "share_count": item.get("share_count"),
        "time": item.get("time"),
        "last_update_time": item.get("last_update_time"),
        "has_video": bool(str(item.get("video_url") or "").strip()),
        "image_count": len(safe_item.get("image_list") or []) if isinstance(safe_item.get("image_list"), list) else 0,
    }


def cli_import_littlecrawler(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills import-littlecrawler")
    parser.add_argument("platform", choices=["zhihu", "xhs"])
    parser.add_argument("--input", required=True, help="Path to LittleCrawler search_contents_*.json")
    parser.add_argument("--queue", default="", help="Queue DB path (default: runs/queue_<platform>.db)")
    parser.add_argument("--run-id", default="", help="captures/<run-id>/ will be created to store SourceArtifact JSON files")
    parser.add_argument("--stage", default="preprocess", help="Queue stage to enqueue (default: preprocess)")
    parser.add_argument("--limit", type=int, default=0, help="Import at most N items (0 = all)")
    parser.add_argument("--dry-run", action="store_true", help="Do not write artifacts or enqueue; only print counts")
    ns = parser.parse_args(argv)

    platform = str(ns.platform).strip().lower()
    input_path = Path(str(ns.input)).expanduser()
    if not input_path.is_absolute():
        input_path = (repo_root() / input_path).resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    queue_path = str(ns.queue or "").strip() or f"runs/queue_{platform}.db"
    run_id = str(ns.run_id or "").strip() or _run_id_from_input(platform=platform, input_path=input_path)
    run_dir = (repo_root() / "captures" / run_id).resolve()

    data = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise RuntimeError("Expected a JSON list in search_contents file.")

    limit = int(ns.limit or 0)
    items = data if limit <= 0 else data[: max(0, limit)]

    # Preflight counts.
    urls = [_artifact_source_url(platform=platform, item=it) for it in items if isinstance(it, dict)]
    urls = [u for u in urls if str(u).strip()]
    unique_urls = len(set([canonicalize_source_url(u) or u for u in urls]))

    if ns.dry_run:
        print(
            json.dumps(
                {
                    "platform": platform,
                    "input": input_path.as_posix(),
                    "total_items": len(items),
                    "unique_urls": unique_urls,
                    "queue": queue_path,
                    "run_id": run_id,
                    "stage": str(ns.stage),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    store = _queue_store(queue_path)
    store.init_db()
    ensure_dir(run_dir / "sources")
    settings = QueueSettings.from_env()

    enq_ok = enq_skip = artifacts_written = artifacts_existing = skipped_bad = 0
    errors: list[str] = []

    for idx, raw in enumerate(items):
        if not isinstance(raw, dict):
            skipped_bad += 1
            continue

        url_raw = _artifact_source_url(platform=platform, item=raw)
        url = canonicalize_source_url(url_raw) or url_raw
        if not url:
            skipped_bad += 1
            continue

        title = str(raw.get("title") or "").strip()
        keyword = str(raw.get("source_keyword") or "").strip()
        domain = default_domain_for_topic(keyword or title or "")
        extracted_text = _format_text(platform=platform, item=raw)
        if not extracted_text:
            extracted_text = title or json.dumps(raw, ensure_ascii=False)[:500]

        extra = _artifact_extra(platform=platform, item=raw, input_path=input_path, index=idx)

        # Persist content as a SourceArtifact JSON (offline import).
        artifact_id = sha256_hex(url)
        artifact_path = run_dir / "sources" / f"{artifact_id}.json"
        if artifact_path.exists():
            artifacts_existing += 1
        else:
            safe_raw = dict(raw)
            if platform == "xhs":
                safe_raw.pop("xsec_token", None)
                safe_raw["note_url"] = _strip_query(str(safe_raw.get("note_url") or ""))
            write_source_artifact(
                run_dir=run_dir,
                source_type=platform,
                url=url,
                title=title,
                raw_text=json.dumps(safe_raw, ensure_ascii=False, sort_keys=True),
                extracted_text=extracted_text,
                license_spdx="",
                license_risk="unknown",
                extra=extra,
            )
            artifacts_written += 1

        try:
            out = store.enqueue(
                source_id="",
                source_type=platform,
                source_url=url,
                source_title=title,
                stage=str(ns.stage),
                priority=0,
                max_attempts=settings.max_attempts,
                domain=domain,
                tags=_tags_from_item(platform=platform, item=raw),
                payload_path=artifact_path.as_posix(),
                config_snapshot={"import": "littlecrawler", "platform": platform, "run_id": run_id},
                extra={"import_file": input_path.as_posix(), "import_index": idx, "source_keyword": keyword},
                run_id=run_id,
            )
            if bool(out.get("enqueued")):
                enq_ok += 1
            else:
                enq_skip += 1
        except Exception as e:
            errors.append(f"idx={idx} url={url} err={e}")

    summary = {
        "platform": platform,
        "input": input_path.as_posix(),
        "total_items": len(items),
        "unique_urls": unique_urls,
        "queue": str(store.db_path),
        "run_id": run_id,
        "run_dir": run_dir.as_posix(),
        "stage": str(ns.stage),
        "enqueued": enq_ok,
        "skipped_existing": enq_skip,
        "artifacts_written": artifacts_written,
        "artifacts_existing": artifacts_existing,
        "skipped_bad": skipped_bad,
        "errors": errors[:50],
        "error_count": len(errors),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0
