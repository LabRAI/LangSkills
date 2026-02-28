from __future__ import annotations

import datetime as _dt
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from ..config import canonicalize_source_url
from ..utils.hashing import sha256_hex
from ..utils.time import utc_now_iso_z, utc_iso_z


DEFAULT_STAGES = [
    "discover",
    "ingest",
    "preprocess",
    "llm_generate",
    "validate",
    "improve",
    "publish",
    "done",
    "dead",
]


def _json_dumps(obj: Any) -> str:
    if obj is None:
        return ""
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True)
    except Exception:
        return ""


def _json_loads(raw: str) -> Any:
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


def _clean_stage(stage: str) -> str:
    s = str(stage or "").strip().lower()
    return s if s else "ingest"


class QueueStore:
    def __init__(self, db_path: Path, *, timeout_sec: int = 30, read_only: bool = False) -> None:
        self.db_path = Path(db_path)
        self.timeout_sec = max(1, int(timeout_sec))
        self.read_only = bool(read_only)

    def _connect(self) -> sqlite3.Connection:
        if self.read_only:
            return self._connect_read_only()
        return self._connect_read_write()

    def _connect_read_only(self) -> sqlite3.Connection:
        path = self.db_path.resolve().as_posix()
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=self.timeout_sec)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            return conn
        except sqlite3.OperationalError:
            # Fallback for disks that cannot handle any journal writes.
            conn = sqlite3.connect(f"file:{path}?immutable=1", uri=True, timeout=self.timeout_sec)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            return conn

    def _connect_read_write(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path.as_posix(), timeout=self.timeout_sec)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError as exc:
            # Some filesystems do not support WAL; fall back to DELETE journal mode.
            try:
                conn.execute("PRAGMA journal_mode=DELETE")
            except sqlite3.OperationalError:
                raise exc
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if self.read_only:
            if not self.db_path.exists():
                raise FileNotFoundError(f"queue db not found: {self.db_path}")
            return
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS queue_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    source_title TEXT,
                    payload_path TEXT,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    available_at TEXT NOT NULL,
                    lease_until TEXT,
                    lease_owner TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 5,
                    last_error TEXT,
                    last_error_at TEXT,
                    run_id TEXT,
                    trace_id TEXT,
                    domain TEXT,
                    tags_json TEXT,
                    config_hash TEXT,
                    config_snapshot_json TEXT,
                    extra_json TEXT,
                    UNIQUE(source_id, stage, config_hash)
                )
                """
            )
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_queue_items_source_unique ON queue_items(source_id)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS queue_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER NOT NULL,
                    stage TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    duration_ms INTEGER,
                    status TEXT,
                    error TEXT,
                    trace_path TEXT,
                    FOREIGN KEY(item_id) REFERENCES queue_items(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS source_registry (
                    source_id TEXT PRIMARY KEY,
                    source_url TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    canonical_url TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    license_spdx TEXT,
                    license_risk TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS queue_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_budgets (
                    run_id TEXT NOT NULL,
                    budget_key TEXT NOT NULL,
                    target INTEGER NOT NULL,
                    done INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(run_id, budget_key)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_budget_reservations (
                    run_id TEXT NOT NULL,
                    budget_key TEXT NOT NULL,
                    item_id INTEGER NOT NULL,
                    worker_id TEXT,
                    reserved_at TEXT NOT NULL,
                    lease_until TEXT NOT NULL,
                    PRIMARY KEY(run_id, budget_key, item_id),
                    FOREIGN KEY(item_id) REFERENCES queue_items(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_budget_commits (
                    run_id TEXT NOT NULL,
                    budget_key TEXT NOT NULL,
                    item_id INTEGER NOT NULL,
                    committed_at TEXT NOT NULL,
                    PRIMARY KEY(run_id, budget_key, item_id),
                    FOREIGN KEY(item_id) REFERENCES queue_items(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_items_stage_status ON queue_items(stage, status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_items_available ON queue_items(available_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_items_lease ON queue_items(lease_until)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_items_source ON queue_items(source_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_items_type ON queue_items(source_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_attempts_item ON queue_attempts(item_id)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_run_budget_reservations_lease ON run_budget_reservations(run_id, budget_key, lease_until)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_run_budget_commits ON run_budget_commits(run_id, budget_key)")
            conn.commit()
        finally:
            conn.close()

    def set_meta(self, key: str, value: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO queue_meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(key or ""), str(value or "")),
            )
            conn.commit()
        finally:
            conn.close()

    def get_meta(self, key: str) -> str:
        conn = self._connect()
        try:
            cur = conn.execute("SELECT value FROM queue_meta WHERE key = ?", (str(key or ""),))
            row = cur.fetchone()
            return str(row["value"] if row else "")
        finally:
            conn.close()

    def is_draining(self) -> bool:
        return str(self.get_meta("drain") or "").strip() == "1"

    def enqueue(
        self,
        *,
        source_id: str,
        source_type: str,
        source_url: str,
        source_title: str = "",
        stage: str = "ingest",
        priority: int = 0,
        max_attempts: int = 5,
        domain: str = "",
        tags: list[str] | None = None,
        payload_path: str = "",
        config_snapshot: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
        run_id: str = "",
        trace_id: str = "",
        available_at: str | None = None,
        allow_requeue_done: bool = True,
    ) -> dict[str, Any]:
        if self.is_draining():
            return {"enqueued": False, "reason": "drain_enabled"}

        canon_url = canonicalize_source_url(source_url) or str(source_url or "").strip()
        sid = str(source_id or "").strip() or sha256_hex(canon_url)
        stype = str(source_type or "").strip().lower()
        stg = _clean_stage(stage)
        now = utc_now_iso_z()
        cfg = dict(config_snapshot or {})
        cfg_hash = sha256_hex(_json_dumps(cfg))
        tags_json = _json_dumps(tags or [])
        extra_json = _json_dumps(extra or {})
        cfg_json = _json_dumps(cfg)
        avail = str(available_at or now)

        conn = self._connect()
        try:
            # Global source_id uniqueness: never enqueue the same source again.
            cur = conn.execute("SELECT id, status FROM queue_items WHERE source_id = ? LIMIT 1", (sid,))
            row = cur.fetchone()
            if row:
                # Update last_seen in source registry for audit.
                self.update_source_registry(
                    source_id=sid,
                    source_url=canon_url,
                    source_type=stype,
                )
                return {"enqueued": False, "id": int(row["id"]), "reason": "source_exists", "status": str(row["status"] or "")}

            # Legacy: if same (source_id, stage, config_hash) exists, optionally requeue.
            cur = conn.execute(
                "SELECT id, status FROM queue_items WHERE source_id = ? AND stage = ? AND config_hash = ?",
                (sid, stg, cfg_hash),
            )
            row = cur.fetchone()
            if row:
                status = str(row["status"] or "")
                if status in {"queued", "running"}:
                    return {"enqueued": False, "id": int(row["id"]), "reason": "exists"}
                if allow_requeue_done:
                    conn.execute(
                        """
                        UPDATE queue_items
                        SET status = ?, available_at = ?, updated_at = ?, attempts = 0, last_error = NULL, last_error_at = NULL
                        WHERE id = ?
                        """,
                        ("queued", avail, now, int(row["id"])),
                    )
                    conn.commit()
                    return {"enqueued": True, "id": int(row["id"]), "requeued": True}
                return {"enqueued": False, "id": int(row["id"]), "reason": "exists_terminal"}

            conn.execute(
                """
                INSERT INTO queue_items (
                    source_id, source_type, source_url, source_title, payload_path,
                    stage, status, priority, created_at, updated_at, available_at,
                    lease_until, lease_owner, attempts, max_attempts, last_error, last_error_at,
                    run_id, trace_id, domain, tags_json, config_hash, config_snapshot_json, extra_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sid,
                    stype,
                    canon_url,
                    str(source_title or ""),
                    str(payload_path or ""),
                    stg,
                    "queued",
                    int(priority or 0),
                    now,
                    now,
                    avail,
                    None,
                    None,
                    0,
                    int(max(1, max_attempts)),
                    None,
                    None,
                    str(run_id or ""),
                    str(trace_id or ""),
                    str(domain or ""),
                    tags_json,
                    cfg_hash,
                    cfg_json,
                    extra_json,
                ),
            )
            conn.execute(
                """
                INSERT INTO source_registry (source_id, source_url, source_type, canonical_url, first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET last_seen_at=excluded.last_seen_at
                """,
                (sid, canon_url, stype, canon_url, now, now),
            )
            conn.commit()
            return {"enqueued": True, "id": int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])}
        finally:
            conn.close()

    def lease_next(
        self,
        *,
        worker_id: str,
        limit: int,
        stages: Iterable[str] | None = None,
        source_type: str | None = None,
        lease_seconds: int = 600,
    ) -> list[dict[str, Any]]:
        lim = max(1, int(limit or 1))
        stg_list = [_clean_stage(s) for s in (stages or []) if str(s or "").strip()]
        stg_clause = ""
        params: list[Any] = []
        if stg_list:
            stg_clause = f"AND stage IN ({','.join(['?'] * len(stg_list))})"
            params.extend(stg_list)
        type_clause = ""
        if source_type:
            type_clause = "AND source_type = ?"
            params.append(str(source_type))

        now = utc_now_iso_z()
        lease_until = utc_iso_z(_dt.datetime.now(tz=_dt.timezone.utc) + _dt.timedelta(seconds=max(10, int(lease_seconds or 10))))

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                f"""
                SELECT id FROM queue_items
                WHERE status = 'queued'
                  AND available_at <= ?
                  AND (lease_until IS NULL OR lease_until < ?)
                  {stg_clause}
                  {type_clause}
                ORDER BY priority DESC, created_at ASC
                LIMIT {lim}
                """,
                [now, now, *params],
            )
            ids = [int(r["id"]) for r in cur.fetchall()]
            if not ids:
                conn.execute("COMMIT")
                return []
            for item_id in ids:
                # Increment attempts when leasing.
                conn.execute(
                    "UPDATE queue_items SET status = ?, lease_owner = ?, lease_until = ?, updated_at = ?, attempts = attempts + 1 WHERE id = ?",
                    ("running", str(worker_id or ""), lease_until, now, item_id),
                )
                attempt = conn.execute("SELECT attempts, stage FROM queue_items WHERE id = ?", (item_id,)).fetchone()
                if attempt:
                    conn.execute(
                        """
                        INSERT INTO queue_attempts (item_id, stage, attempt, started_at, status)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (item_id, str(attempt["stage"] or ""), int(attempt["attempts"] or 0), now, "running"),
                    )
            conn.execute("COMMIT")
            return [self.get_item(item_id) for item_id in ids]
        finally:
            conn.close()

    def ack(self, item_id: int, *, status: str = "done", attempt_status: str = "ok", attempt_error: str = "") -> None:
        now = utc_now_iso_z()
        conn = self._connect()
        try:
            row = conn.execute("SELECT stage, attempts FROM queue_items WHERE id = ?", (int(item_id),)).fetchone()
            stage = str(row["stage"] or "") if row else ""
            attempt_num = int(row["attempts"] or 0) if row else 0
            dur_ms = 0
            started = conn.execute(
                "SELECT started_at FROM queue_attempts WHERE item_id = ? AND stage = ? AND attempt = ?",
                (int(item_id), stage, attempt_num),
            ).fetchone()
            if started and started["started_at"]:
                try:
                    t0 = _dt.datetime.fromisoformat(str(started["started_at"]).replace("Z", "+00:00"))
                    dur_ms = int((_dt.datetime.now(tz=_dt.timezone.utc) - t0).total_seconds() * 1000)
                except Exception:
                    dur_ms = 0
            conn.execute(
                """
                UPDATE queue_items
                SET status = ?, stage = ?, updated_at = ?, lease_owner = NULL, lease_until = NULL
                WHERE id = ?
                """,
                (status, status, now, int(item_id)),
            )
            conn.execute(
                """
                UPDATE queue_attempts
                SET ended_at = ?, duration_ms = ?, status = ?, error = ?
                WHERE item_id = ? AND stage = ? AND attempt = ?
                """,
                (now, dur_ms, str(attempt_status or "ok"), str(attempt_error or ""), int(item_id), stage, attempt_num),
            )
            conn.commit()
        finally:
            conn.close()

    def nack(self, item_id: int, *, reason: str, backoff_seconds: int, max_attempts: int | None = None) -> dict[str, Any]:
        now = utc_now_iso_z()
        conn = self._connect()
        try:
            row = conn.execute("SELECT attempts, max_attempts, stage FROM queue_items WHERE id = ?", (int(item_id),)).fetchone()
            attempts = int(row["attempts"] or 0) if row else 0
            max_a = int(max_attempts or (row["max_attempts"] if row else 5))
            stage = str(row["stage"] or "") if row else ""
            attempt_num = attempts
            dur_ms = 0
            started = conn.execute(
                "SELECT started_at FROM queue_attempts WHERE item_id = ? AND stage = ? AND attempt = ?",
                (int(item_id), stage, attempt_num),
            ).fetchone()
            if started and started["started_at"]:
                try:
                    t0 = _dt.datetime.fromisoformat(str(started["started_at"]).replace("Z", "+00:00"))
                    dur_ms = int((_dt.datetime.now(tz=_dt.timezone.utc) - t0).total_seconds() * 1000)
                except Exception:
                    dur_ms = 0
            if attempts >= max_a:
                conn.execute(
                    """
                    UPDATE queue_items
                    SET status = 'dead', stage = 'dead', last_error = ?, last_error_at = ?, updated_at = ?,
                        lease_owner = NULL, lease_until = NULL
                    WHERE id = ?
                    """,
                    (str(reason or ""), now, now, int(item_id)),
                )
                outcome = "dead"
            else:
                avail = utc_iso_z(_dt.datetime.now(tz=_dt.timezone.utc) + _dt.timedelta(seconds=max(1, int(backoff_seconds))))
                conn.execute(
                    """
                    UPDATE queue_items
                    SET status = 'queued', available_at = ?, last_error = ?, last_error_at = ?, updated_at = ?,
                        lease_owner = NULL, lease_until = NULL
                    WHERE id = ?
                    """,
                    (avail, str(reason or ""), now, now, int(item_id)),
                )
                outcome = "queued"
            conn.execute(
                """
                UPDATE queue_attempts
                SET ended_at = ?, duration_ms = ?, status = ?, error = ?
                WHERE item_id = ? AND stage = ? AND attempt = ?
                """,
                (now, dur_ms, "error", str(reason or ""), int(item_id), stage, attempt_num),
            )
            conn.commit()
            return {"status": outcome}
        finally:
            conn.close()

    def requeue(self, item_id: int, *, new_stage: str) -> None:
        now = utc_now_iso_z()
        stg = _clean_stage(new_stage)
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE queue_items
                SET status = 'queued', stage = ?, available_at = ?, updated_at = ?,
                    lease_owner = NULL, lease_until = NULL, last_error = NULL, last_error_at = NULL
                WHERE id = ?
                """,
                (stg, now, now, int(item_id)),
            )
            conn.commit()
        finally:
            conn.close()

    def complete_attempt(self, item_id: int, *, status: str = "ok", error: str = "") -> None:
        now = utc_now_iso_z()
        conn = self._connect()
        try:
            row = conn.execute("SELECT stage, attempts FROM queue_items WHERE id = ?", (int(item_id),)).fetchone()
            stage = str(row["stage"] or "") if row else ""
            attempt_num = int(row["attempts"] or 0) if row else 0
            dur_ms = 0
            started = conn.execute(
                "SELECT started_at FROM queue_attempts WHERE item_id = ? AND stage = ? AND attempt = ?",
                (int(item_id), stage, attempt_num),
            ).fetchone()
            if started and started["started_at"]:
                try:
                    t0 = _dt.datetime.fromisoformat(str(started["started_at"]).replace("Z", "+00:00"))
                    dur_ms = int((_dt.datetime.now(tz=_dt.timezone.utc) - t0).total_seconds() * 1000)
                except Exception:
                    dur_ms = 0
            conn.execute(
                """
                UPDATE queue_attempts
                SET ended_at = ?, duration_ms = ?, status = ?, error = ?
                WHERE item_id = ? AND stage = ? AND attempt = ?
                """,
                (now, dur_ms, str(status or "ok"), str(error or ""), int(item_id), stage, attempt_num),
            )
            conn.commit()
        finally:
            conn.close()

    def update_item_fields(self, item_id: int, **fields: Any) -> None:
        if not fields:
            return
        now = utc_now_iso_z()
        updates: list[str] = []
        params: list[Any] = []

        def _set(col: str, val: Any) -> None:
            updates.append(f"{col} = ?")
            params.append(val)

        if "extra" in fields:
            _set("extra_json", _json_dumps(fields.get("extra") or {}))
        if "tags" in fields:
            _set("tags_json", _json_dumps(fields.get("tags") or []))
        if "config_snapshot" in fields:
            _set("config_snapshot_json", _json_dumps(fields.get("config_snapshot") or {}))

        simple_fields = {
            "payload_path": "payload_path",
            "source_title": "source_title",
            "run_id": "run_id",
            "trace_id": "trace_id",
            "domain": "domain",
            "available_at": "available_at",
            "last_error": "last_error",
            "last_error_at": "last_error_at",
            "status": "status",
            "priority": "priority",
            "max_attempts": "max_attempts",
            "lease_owner": "lease_owner",
            "lease_until": "lease_until",
            "source_url": "source_url",
            "source_type": "source_type",
            "source_id": "source_id",
        }
        for key, col in simple_fields.items():
            if key not in fields:
                continue
            val = fields.get(key)
            if key == "source_type":
                val = str(val or "").strip().lower()
            elif key in {
                "status",
                "source_id",
                "source_url",
                "source_title",
                "payload_path",
                "run_id",
                "trace_id",
                "domain",
                "lease_owner",
                "lease_until",
                "last_error",
                "last_error_at",
                "available_at",
            }:
                val = str(val or "")
            elif key in {"priority", "max_attempts"}:
                val = int(val or 0)
            _set(col, val)

        if "stage" in fields:
            _set("stage", _clean_stage(fields.get("stage")))

        if not updates:
            return

        updates.append("updated_at = ?")
        params.append(now)
        params.append(int(item_id))

        conn = self._connect()
        try:
            conn.execute(f"UPDATE queue_items SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        finally:
            conn.close()

    def get_item(self, item_id: int) -> dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM queue_items WHERE id = ?", (int(item_id),)).fetchone()
            return self._row_to_item(row)
        finally:
            conn.close()

    def _row_to_item(self, row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            return {}
        return {
            "id": int(row["id"]) if row["id"] is not None else 0,
            "source_id": str(row["source_id"] or ""),
            "source_type": str(row["source_type"] or ""),
            "source_url": str(row["source_url"] or ""),
            "source_title": str(row["source_title"] or ""),
            "payload_path": str(row["payload_path"] or ""),
            "stage": str(row["stage"] or ""),
            "status": str(row["status"] or ""),
            "priority": int(row["priority"] or 0),
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
            "available_at": str(row["available_at"] or ""),
            "lease_until": str(row["lease_until"] or ""),
            "lease_owner": str(row["lease_owner"] or ""),
            "attempts": int(row["attempts"] or 0),
            "max_attempts": int(row["max_attempts"] or 0),
            "last_error": str(row["last_error"] or ""),
            "last_error_at": str(row["last_error_at"] or ""),
            "run_id": str(row["run_id"] or ""),
            "trace_id": str(row["trace_id"] or ""),
            "domain": str(row["domain"] or ""),
            "tags": _json_loads(row["tags_json"]) or [],
            "config_snapshot": _json_loads(row["config_snapshot_json"]) or {},
            "extra": _json_loads(row["extra_json"]) or {},
        }

    def stats(self) -> dict[str, Any]:
        conn = self._connect()
        try:
            total = int(conn.execute("SELECT COUNT(*) FROM queue_items").fetchone()[0])
            by_status = {
                str(r["status"] or ""): int(r["c"] or 0)
                for r in conn.execute("SELECT status, COUNT(*) AS c FROM queue_items GROUP BY status").fetchall()
            }
            by_stage = {
                str(r["stage"] or ""): int(r["c"] or 0)
                for r in conn.execute("SELECT stage, COUNT(*) AS c FROM queue_items GROUP BY stage").fetchall()
            }
            by_source_type = {
                str(r["source_type"] or ""): int(r["c"] or 0)
                for r in conn.execute("SELECT source_type, COUNT(*) AS c FROM queue_items GROUP BY source_type").fetchall()
            }

            now = _dt.datetime.now(tz=_dt.timezone.utc)
            age_buckets = {
                "lt_1h": 0,
                "lt_6h": 0,
                "lt_24h": 0,
                "lt_7d": 0,
                "gte_7d": 0,
            }
            for row in conn.execute("SELECT updated_at FROM queue_items").fetchall():
                raw = str(row["updated_at"] or "")
                if not raw:
                    continue
                try:
                    ts = _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
                except Exception:
                    continue
                delta = now - ts
                hours = delta.total_seconds() / 3600.0
                if hours < 1:
                    age_buckets["lt_1h"] += 1
                elif hours < 6:
                    age_buckets["lt_6h"] += 1
                elif hours < 24:
                    age_buckets["lt_24h"] += 1
                elif hours < 24 * 7:
                    age_buckets["lt_7d"] += 1
                else:
                    age_buckets["gte_7d"] += 1

            return {
                "total": total,
                "by_status": by_status,
                "by_stage": by_stage,
                "by_source_type": by_source_type,
                "by_age": age_buckets,
            }
        finally:
            conn.close()

    def gc(self, *, reclaim_expired: bool = True) -> dict[str, int]:
        now = utc_now_iso_z()
        conn = self._connect()
        try:
            reclaimed = 0
            if reclaim_expired:
                rows = conn.execute(
                    """
                    SELECT id FROM queue_items
                    WHERE status = 'running' AND lease_until IS NOT NULL AND lease_until < ?
                    """,
                    (now,),
                ).fetchall()
                ids = [int(r["id"]) for r in rows]
                for item_id in ids:
                    conn.execute(
                        """
                        UPDATE queue_items
                        SET status = 'queued', updated_at = ?, lease_owner = NULL, lease_until = NULL
                        WHERE id = ?
                        """,
                        (now, item_id),
                    )
                reclaimed = len(ids)

                conn.execute(
                    "DELETE FROM run_budget_reservations WHERE lease_until < ?",
                    (now,),
                )

            conn.execute(
                "DELETE FROM queue_attempts WHERE item_id NOT IN (SELECT id FROM queue_items)"
            )

            conn.commit()
            return {"reclaimed": reclaimed}
        finally:
            conn.close()

    def update_source_registry(
        self,
        *,
        source_id: str,
        source_url: str,
        source_type: str,
        license_spdx: str | None = None,
        license_risk: str | None = None,
        status: str | None = None,
    ) -> None:
        now = utc_now_iso_z()
        sid = str(source_id or "").strip()
        if not sid:
            return
        canon_url = canonicalize_source_url(source_url) or str(source_url or "").strip()
        stype = str(source_type or "").strip().lower()

        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT status, license_spdx, license_risk FROM source_registry WHERE source_id = ?",
                (sid,),
            ).fetchone()
            cur_status = str(row["status"] or "") if row else ""
            cur_spdx = str(row["license_spdx"] or "") if row else ""
            cur_risk = str(row["license_risk"] or "") if row else ""

            next_status = str(status or cur_status or "active")
            next_spdx = str(license_spdx or cur_spdx or "")
            next_risk = str(license_risk or cur_risk or "")

            if row:
                conn.execute(
                    """
                    UPDATE source_registry
                    SET source_url = ?, source_type = ?, canonical_url = ?, last_seen_at = ?,
                        status = ?, license_spdx = ?, license_risk = ?
                    WHERE source_id = ?
                    """,
                    (canon_url, stype, canon_url, now, next_status, next_spdx, next_risk, sid),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO source_registry (
                        source_id, source_url, source_type, canonical_url, first_seen_at, last_seen_at,
                        status, license_spdx, license_risk
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (sid, canon_url, stype, canon_url, now, now, next_status, next_spdx, next_risk),
                )
            conn.commit()
        finally:
            conn.close()

    def reserve_run_budget(
        self,
        *,
        run_id: str,
        budget_key: str,
        item_id: int,
        target: int,
        lease_seconds: int,
        worker_id: str = "",
    ) -> dict[str, Any]:
        if not run_id or not budget_key or int(item_id or 0) <= 0:
            return {"reserved": False, "reason": "invalid"}

        now = utc_now_iso_z()
        lease_until = utc_iso_z(_dt.datetime.now(tz=_dt.timezone.utc) + _dt.timedelta(seconds=max(10, int(lease_seconds or 10))))
        run_id = str(run_id or "").strip()
        budget_key = str(budget_key or "").strip()

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT target, done FROM run_budgets WHERE run_id = ? AND budget_key = ?",
                (run_id, budget_key),
            ).fetchone()
            if row:
                cur_target = int(row["target"] or 0)
                if target > cur_target:
                    conn.execute(
                        "UPDATE run_budgets SET target = ?, updated_at = ? WHERE run_id = ? AND budget_key = ?",
                        (int(target), now, run_id, budget_key),
                    )
            else:
                conn.execute(
                    """
                    INSERT INTO run_budgets (run_id, budget_key, target, done, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (run_id, budget_key, int(target), 0, now, now),
                )

            conn.execute(
                "DELETE FROM run_budget_reservations WHERE run_id = ? AND budget_key = ? AND lease_until < ?",
                (run_id, budget_key, now),
            )

            done = int(
                conn.execute(
                    "SELECT COUNT(*) FROM run_budget_commits WHERE run_id = ? AND budget_key = ?",
                    (run_id, budget_key),
                ).fetchone()[0]
            )
            conn.execute(
                "UPDATE run_budgets SET done = ?, updated_at = ? WHERE run_id = ? AND budget_key = ?",
                (done, now, run_id, budget_key),
            )

            reserved_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM run_budget_reservations WHERE run_id = ? AND budget_key = ?",
                    (run_id, budget_key),
                ).fetchone()[0]
            )

            if conn.execute(
                "SELECT 1 FROM run_budget_commits WHERE run_id = ? AND budget_key = ? AND item_id = ?",
                (run_id, budget_key, int(item_id)),
            ).fetchone():
                conn.execute("COMMIT")
                return {
                    "reserved": False,
                    "reason": "already_committed",
                    "target": int(target),
                    "done": done,
                    "reserved_count": reserved_count,
                }

            if conn.execute(
                "SELECT 1 FROM run_budget_reservations WHERE run_id = ? AND budget_key = ? AND item_id = ?",
                (run_id, budget_key, int(item_id)),
            ).fetchone():
                conn.execute(
                    "UPDATE run_budget_reservations SET lease_until = ?, worker_id = ? WHERE run_id = ? AND budget_key = ? AND item_id = ?",
                    (lease_until, str(worker_id or ""), run_id, budget_key, int(item_id)),
                )
                conn.execute("COMMIT")
                return {
                    "reserved": True,
                    "reason": "already_reserved",
                    "target": int(target),
                    "done": done,
                    "reserved_count": reserved_count,
                }

            if int(target) > 0 and done >= int(target):
                conn.execute("COMMIT")
                return {
                    "reserved": False,
                    "reason": "budget_full",
                    "target": int(target),
                    "done": done,
                    "reserved_count": reserved_count,
                }
            if int(target) > 0 and (done + reserved_count) >= int(target):
                conn.execute("COMMIT")
                return {
                    "reserved": False,
                    "reason": "budget_reserved",
                    "target": int(target),
                    "done": done,
                    "reserved_count": reserved_count,
                }

            conn.execute(
                """
                INSERT INTO run_budget_reservations (run_id, budget_key, item_id, worker_id, reserved_at, lease_until)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, budget_key, int(item_id), str(worker_id or ""), now, lease_until),
            )
            reserved_count += 1
            conn.execute("COMMIT")
            return {
                "reserved": True,
                "reason": "reserved",
                "target": int(target),
                "done": done,
                "reserved_count": reserved_count,
            }
        finally:
            conn.close()

    def release_run_budget_reservation(self, *, run_id: str, budget_key: str, item_id: int) -> None:
        run_id = str(run_id or "").strip()
        budget_key = str(budget_key or "").strip()
        if not run_id or not budget_key:
            return
        conn = self._connect()
        try:
            conn.execute(
                "DELETE FROM run_budget_reservations WHERE run_id = ? AND budget_key = ? AND item_id = ?",
                (run_id, budget_key, int(item_id)),
            )
            conn.commit()
        finally:
            conn.close()

    def commit_run_budget(
        self,
        *,
        run_id: str,
        budget_key: str,
        item_id: int,
        target: int,
    ) -> dict[str, Any]:
        if not run_id or not budget_key or int(item_id or 0) <= 0:
            return {"committed": False, "reason": "invalid"}

        now = utc_now_iso_z()
        run_id = str(run_id or "").strip()
        budget_key = str(budget_key or "").strip()

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT target FROM run_budgets WHERE run_id = ? AND budget_key = ?",
                (run_id, budget_key),
            ).fetchone()
            if row:
                cur_target = int(row["target"] or 0)
                if int(target) > cur_target:
                    conn.execute(
                        "UPDATE run_budgets SET target = ?, updated_at = ? WHERE run_id = ? AND budget_key = ?",
                        (int(target), now, run_id, budget_key),
                    )
            else:
                conn.execute(
                    """
                    INSERT INTO run_budgets (run_id, budget_key, target, done, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (run_id, budget_key, int(target), 0, now, now),
                )

            committed = False
            if not conn.execute(
                "SELECT 1 FROM run_budget_commits WHERE run_id = ? AND budget_key = ? AND item_id = ?",
                (run_id, budget_key, int(item_id)),
            ).fetchone():
                conn.execute(
                    """
                    INSERT INTO run_budget_commits (run_id, budget_key, item_id, committed_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (run_id, budget_key, int(item_id), now),
                )
                committed = True

            conn.execute(
                "DELETE FROM run_budget_reservations WHERE run_id = ? AND budget_key = ? AND item_id = ?",
                (run_id, budget_key, int(item_id)),
            )

            done = int(
                conn.execute(
                    "SELECT COUNT(*) FROM run_budget_commits WHERE run_id = ? AND budget_key = ?",
                    (run_id, budget_key),
                ).fetchone()[0]
            )
            conn.execute(
                "UPDATE run_budgets SET done = ?, updated_at = ? WHERE run_id = ? AND budget_key = ?",
                (done, now, run_id, budget_key),
            )

            reserved_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM run_budget_reservations WHERE run_id = ? AND budget_key = ?",
                    (run_id, budget_key),
                ).fetchone()[0]
            )

            conn.execute("COMMIT")
            return {
                "committed": committed,
                "target": int(target),
                "done": done,
                "reserved_count": reserved_count,
            }
        finally:
            conn.close()
