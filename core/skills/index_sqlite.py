"""Rebuild skills/index.sqlite from skills/index.json.

This fills the gap that ``publish_parallel.py`` expects: a fresh SQLite
index derived from the authoritative ``index.json`` manifest.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

_INDEX_COLS = [
    "skill_id",
    "dir",
    "item_json",
    "updated_at",
    "source_id",
    "primary_source_id",
    "domain",
    "profile",
    "source_type",
    "source_url",
    "title",
    "overall_score",
    "skill_kind",
    "language",
]

_DDL = """
CREATE TABLE IF NOT EXISTS skills_index (
    skill_id          TEXT PRIMARY KEY,
    dir               TEXT,
    item_json         TEXT,
    updated_at        TEXT,
    source_id         TEXT,
    primary_source_id TEXT,
    domain            TEXT,
    profile           TEXT,
    source_type       TEXT,
    source_url        TEXT,
    title             TEXT,
    overall_score     REAL,
    skill_kind        TEXT,
    language          TEXT
);
CREATE TABLE IF NOT EXISTS skills_index_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def rebuild_index(repo_root: Path) -> int:
    """Rebuild ``skills/index.sqlite`` from ``skills/index.json``.

    Returns the number of rows inserted.
    """
    index_json_path = repo_root / "skills" / "index.json"
    if not index_json_path.exists():
        raise FileNotFoundError(f"index.json not found: {index_json_path}")

    data = json.loads(index_json_path.read_text(encoding="utf-8"))
    items: list[dict] = data.get("items", [])
    if not items:
        print("Warning: index.json has zero items.", file=sys.stderr)

    out_path = repo_root / "skills" / "index.sqlite"
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".sqlite", dir=out_path.parent)
    os.close(tmp_fd)

    try:
        conn = sqlite3.connect(tmp_path)
        conn.executescript(_DDL)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        placeholders = ",".join("?" for _ in _INDEX_COLS)
        batch: list[list] = []

        for item in items:
            row = [
                str(item.get("skill_id") or ""),
                str(item.get("dir") or ""),
                json.dumps(item, ensure_ascii=False),
                str(item.get("updated_at") or ""),
                str(item.get("source_id") or item.get("primary_source_id") or ""),
                str(item.get("primary_source_id") or item.get("source_id") or ""),
                str(item.get("domain") or ""),
                str(item.get("profile") or ""),
                str(item.get("source_type") or ""),
                str(item.get("source_url") or ""),
                str(item.get("title") or ""),
                float(item.get("overall_score") or 0),
                str(item.get("skill_kind") or ""),
                str(item.get("language") or "en"),
            ]
            batch.append(row)
            if len(batch) >= 500:
                conn.executemany(
                    f"INSERT OR REPLACE INTO skills_index ({','.join(_INDEX_COLS)}) "
                    f"VALUES ({placeholders})",
                    batch,
                )
                batch.clear()

        if batch:
            conn.executemany(
                f"INSERT OR REPLACE INTO skills_index ({','.join(_INDEX_COLS)}) "
                f"VALUES ({placeholders})",
                batch,
            )

        # Write meta
        import datetime as _dt
        now = _dt.datetime.now(tz=_dt.timezone.utc).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO skills_index_meta (key, value) VALUES (?, ?)",
            ("rebuilt_at", now),
        )
        conn.execute(
            "INSERT OR REPLACE INTO skills_index_meta (key, value) VALUES (?, ?)",
            ("total_items", str(len(items))),
        )
        conn.commit()
        conn.close()
        os.replace(tmp_path, out_path)
        return len(items)
    except BaseException:
        try:
            conn.close()
        except Exception:
            pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def cli_rebuild_index(argv: list[str] | None = None) -> int:
    """CLI entry point for ``langskills bundle-rebuild``."""
    parser = argparse.ArgumentParser(
        prog="langskills bundle-rebuild",
        description="Rebuild skills/index.sqlite from skills/index.json",
    )
    parser.add_argument(
        "--repo-root",
        default="",
        help="Repository root (default: auto-detect)",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root) if args.repo_root else Path(__file__).resolve().parents[2]
    count = rebuild_index(repo_root)
    print(f"Rebuilt index.sqlite with {count:,} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_rebuild_index())
