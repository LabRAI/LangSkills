"""Skill search module — query the LangSkills SQLite index locally.

Supports two modes:

1. **Single-file bundle** (preferred): A self-contained ``.sqlite`` bundle
   built by ``build_bundle.py`` that includes both ``skills_index`` and
   ``skills_content`` tables plus an FTS5 virtual table.

2. **Legacy two-file mode**: Separate ``index.sqlite`` (metadata) +
   ``skills_bundle.sqlite`` (content).

Bundle resolution order (first existing path wins):

1. ``LANGSKILLS_BUNDLE_PATH`` environment variable
2. ``skills/skills_bundle.sqlite`` in the repo  (if it contains ``skills_index``)
3. ``~/.langskills/search_config.json`` → ``bundle_path``
4. ``~/.langskills/langskills-bundle-lite-*.sqlite`` (glob, newest)
5. Fallback: legacy ``skills/index.sqlite`` + ``skills/skills_bundle.sqlite``

Zero new dependencies — uses only stdlib ``sqlite3``.
"""

from __future__ import annotations

import glob as _glob
import json
import os
import sqlite3
import sys
import textwrap
from pathlib import Path
from typing import Any

# ── path resolution ──────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _skills_dir() -> Path:
    """Return the directory containing the SQLite databases."""
    override = os.environ.get("LANGSKILLS_SKILLS_DIR", "").strip()
    if override:
        return Path(override)
    return _REPO_ROOT / "skills"


def _dist_dir() -> Path:
    """Return the dist/ directory containing built bundles."""
    override = os.environ.get("LANGSKILLS_DIST_DIR", "").strip()
    if override:
        return Path(override)
    return _REPO_ROOT / "dist"


def _index_db() -> Path:
    return _skills_dir() / "index.sqlite"


def _bundle_db() -> Path:
    return _skills_dir() / "skills_bundle.sqlite"


def _bundle_has_index(conn: sqlite3.Connection) -> bool:
    """Check whether a bundle DB contains the ``skills_index`` table.

    If True, the bundle is self-contained (single-file mode).
    """
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='skills_index'"
        ).fetchone()
        return row is not None
    except Exception:
        return False


def _resolve_bundle() -> Path | None:
    """Walk the fallback chain and return the first usable bundle path.

    Returns None if no bundle is found (caller should fall back to legacy).
    """
    # 1. Explicit env override
    env_path = os.environ.get("LANGSKILLS_BUNDLE_PATH", "").strip()
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    # 2. Repo-local skills_bundle.sqlite (only if it has skills_index)
    repo_bundle = _bundle_db()
    if repo_bundle.exists():
        try:
            c = sqlite3.connect(f"file:{repo_bundle}?mode=ro", uri=True)
            has = _bundle_has_index(c)
            c.close()
            if has:
                return repo_bundle
        except Exception:
            pass

    # 3. ~/.langskills/search_config.json → bundle_path
    config_path = Path.home() / ".langskills" / "search_config.json"
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            bp = cfg.get("bundle_path", "")
            if bp and Path(bp).exists():
                return Path(bp)
        except Exception:
            pass

    # 4. Glob ~/.langskills/langskills-bundle-lite-*.sqlite (newest)
    home_dir = Path.home() / ".langskills"
    if home_dir.is_dir():
        candidates = sorted(
            _glob.glob(str(home_dir / "langskills-bundle-lite-*.sqlite")),
            reverse=True,
        )
        if candidates:
            return Path(candidates[0])

    return None


def _resolve_all_bundles(domain: str = "") -> list[Path]:
    """Return all installed bundle paths for multi-bundle search.

    Resolution order:
    1. ``search_config.json`` → ``bundles`` dict (domain-keyed)
    2. Glob ``~/.langskills/langskills-bundle-*.sqlite``
    3. Single-bundle fallback via ``_resolve_bundle()``

    If *domain* is given, only return the bundle for that domain.
    """
    found: list[Path] = []
    seen: set[str] = set()

    # 1. search_config.json → bundles dict
    config_path = Path.home() / ".langskills" / "search_config.json"
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            bundles_dict = cfg.get("bundles", {})
            if isinstance(bundles_dict, dict):
                for d, bp in bundles_dict.items():
                    if domain and d != domain:
                        continue
                    p = Path(bp)
                    if p.exists() and str(p) not in seen:
                        found.append(p)
                        seen.add(str(p))
        except Exception:
            pass

    if domain and found:
        return found

    # 2. Glob dist/ directory for split bundles
    dist = _dist_dir()
    if dist.is_dir():
        for candidate in sorted(
            _glob.glob(str(dist / "langskills-bundle-*.sqlite")),
            reverse=True,
        ):
            p = Path(candidate)
            if str(p) not in seen:
                if domain:
                    name = p.name
                    if f"-{domain}-" not in name:
                        continue
                found.append(p)
                seen.add(str(p))

    if found:
        return found

    # 3. Glob ~/.langskills/langskills-bundle-*-*.sqlite (domain bundles)
    home_dir = Path.home() / ".langskills"
    if home_dir.is_dir():
        for candidate in sorted(
            _glob.glob(str(home_dir / "langskills-bundle-*-*.sqlite")),
            reverse=True,
        ):
            p = Path(candidate)
            if str(p) not in seen:
                if domain:
                    name = p.name
                    if f"-{domain}-" not in name:
                        continue
                found.append(p)
                seen.add(str(p))

    if found:
        return found

    # 3. Fallback to single bundle
    single = _resolve_bundle()
    if single is not None:
        return [single]

    return []


# ── FTS helpers ──────────────────────────────────────────────────

def _ensure_fts(conn: sqlite3.Connection) -> bool:
    """Try to create an FTS5 virtual table over ``skills_index.title``.

    Returns True if FTS5 is available, False otherwise (falls back to LIKE).
    """
    try:
        # Check if FTS table already exists (e.g. built into the bundle).
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='skills_fts'"
        ).fetchone()
        if row is not None:
            return True
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS skills_fts "
            "USING fts5(title, skill_id UNINDEXED, content='skills_index', content_rowid='rowid')"
        )
        # Populate if empty.
        count = conn.execute("SELECT COUNT(*) FROM skills_fts").fetchone()[0]
        if count == 0:
            conn.execute(
                "INSERT INTO skills_fts(skills_fts) VALUES('rebuild')"
            )
        return True
    except Exception:
        return False


def _fts_query(conn: sqlite3.Connection, query: str, limit: int) -> list[str]:
    """Return matching skill_ids via FTS5 ranked search."""
    # Escape double-quotes in query for FTS5 syntax.
    safe_q = query.replace('"', '""')
    rows = conn.execute(
        'SELECT skill_id FROM skills_fts WHERE skills_fts MATCH ? ORDER BY rank LIMIT ?',
        (f'"{safe_q}"', limit),
    ).fetchall()
    return [r[0] for r in rows]


def _like_query(conn: sqlite3.Connection, query: str, limit: int) -> list[str]:
    """Fallback: return matching skill_ids via LIKE %query%."""
    rows = conn.execute(
        "SELECT skill_id FROM skills_index WHERE title LIKE ? ORDER BY overall_score DESC LIMIT ?",
        (f"%{query}%", limit),
    ).fetchall()
    return [r[0] for r in rows]


# ── core search ──────────────────────────────────────────────────

def _search_single_bundle(
    bundle_path: Path,
    query: str,
    top_k: int,
    domain: str,
    kind: str,
    source_type: str,
    min_score: float,
    content: bool,
    max_chars: int,
) -> list[dict[str, Any]]:
    """Search a self-contained bundle (has both skills_index and skills_content)."""
    conn = sqlite3.connect(f"file:{bundle_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        has_fts = _ensure_fts(conn)
        if has_fts:
            candidate_ids = _fts_query(conn, query, top_k * 5)
        else:
            candidate_ids = _like_query(conn, query, top_k * 5)

        if not candidate_ids:
            return []

        placeholders = ",".join("?" for _ in candidate_ids)
        rows = conn.execute(
            f"SELECT * FROM skills_index WHERE skill_id IN ({placeholders})",
            candidate_ids,
        ).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            r = dict(row)
            if domain and (r.get("domain") or "").lower() != domain.lower():
                continue
            if kind and (r.get("skill_kind") or "").lower() != kind.lower():
                continue
            if source_type and (r.get("source_type") or "").lower() != source_type.lower():
                continue
            if min_score and (r.get("overall_score") or 0) < min_score:
                continue
            results.append(r)
            if len(results) >= top_k:
                break

        id_order = {sid: i for i, sid in enumerate(candidate_ids)}
        results.sort(key=lambda r: id_order.get(r["skill_id"], 9999))

        # Content fetch from the same DB
        if content and results:
            ids = [r["skill_id"] for r in results]
            ph = ",".join("?" for _ in ids)
            content_rows = conn.execute(
                f"SELECT skill_id, skill_md FROM skills_content WHERE skill_id IN ({ph})",
                ids,
            ).fetchall()
            content_map = {cr["skill_id"]: cr["skill_md"] for cr in content_rows}
            for r in results:
                md = content_map.get(r["skill_id"], "")
                if max_chars and len(md) > max_chars:
                    md = md[:max_chars] + "\n\n... [truncated]"
                r["skill_md"] = md

        return results
    finally:
        conn.close()


def search_skills(
    query: str,
    *,
    top_k: int = 10,
    domain: str = "",
    kind: str = "",
    source_type: str = "",
    min_score: float = 0.0,
    content: bool = False,
    max_chars: int = 0,
) -> list[dict[str, Any]]:
    """Search the skill index and optionally fetch full content.

    Parameters
    ----------
    query : str
        Free-text search string.
    top_k : int
        Maximum results to return.
    domain : str
        Filter by domain (e.g. ``linux``, ``ml``, ``web``).
    kind : str
        Filter by skill_kind (e.g. ``github``, ``arxiv``, ``webpage``).
    source_type : str
        Filter by source_type (e.g. ``github``, ``journal``).
    min_score : float
        Minimum ``overall_score`` threshold.
    content : bool
        If True, join the bundle DB to include ``skill_md`` content.
    max_chars : int
        Truncate ``skill_md`` to this many characters (0 = no limit).

    Returns
    -------
    list[dict]
        Each dict has index metadata fields and optionally ``skill_md``.
    """
    # Try multi-bundle search first (covers domain bundles + single bundle)
    bundles = _resolve_all_bundles(domain=domain)
    if bundles:
        all_results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for bp in bundles:
            try:
                partial = _search_single_bundle(
                    bp, query, top_k, domain, kind, source_type,
                    min_score, content, max_chars,
                )
            except Exception:
                continue
            for r in partial:
                sid = r.get("skill_id", "")
                if sid not in seen_ids:
                    seen_ids.add(sid)
                    all_results.append(r)
        # Sort by overall_score descending across all bundles
        all_results.sort(
            key=lambda r: (r.get("overall_score") or 0), reverse=True,
        )
        return all_results[:top_k]

    # Legacy two-file mode
    idx_path = _index_db()
    if not idx_path.exists():
        raise FileNotFoundError(
            f"No bundle found and index database missing: {idx_path}\n"
            "Install a bundle with: langskills bundle-install"
        )

    conn = sqlite3.connect(f"file:{idx_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        # Phase 1: get candidate skill_ids.
        has_fts = _ensure_fts(conn)

        if has_fts:
            candidate_ids = _fts_query(conn, query, top_k * 5)
        else:
            candidate_ids = _like_query(conn, query, top_k * 5)

        if not candidate_ids:
            return []

        # Fetch full index rows for candidates.
        placeholders = ",".join("?" for _ in candidate_ids)
        rows = conn.execute(
            f"SELECT * FROM skills_index WHERE skill_id IN ({placeholders})",
            candidate_ids,
        ).fetchall()

        # Apply filters.
        results: list[dict[str, Any]] = []
        for row in rows:
            r = dict(row)
            if domain and (r.get("domain") or "").lower() != domain.lower():
                continue
            if kind and (r.get("skill_kind") or "").lower() != kind.lower():
                continue
            if source_type and (r.get("source_type") or "").lower() != source_type.lower():
                continue
            if min_score and (r.get("overall_score") or 0) < min_score:
                continue
            results.append(r)
            if len(results) >= top_k:
                break

        # Preserve FTS rank order (candidates list order).
        id_order = {sid: i for i, sid in enumerate(candidate_ids)}
        results.sort(key=lambda r: id_order.get(r["skill_id"], 9999))

    finally:
        conn.close()

    # Phase 2: optionally fetch content.
    if content and results:
        bun_path = _bundle_db()
        if not bun_path.exists():
            raise FileNotFoundError(f"Bundle database not found: {bun_path}")

        bconn = sqlite3.connect(f"file:{bun_path}?mode=ro", uri=True)
        bconn.row_factory = sqlite3.Row
        try:
            ids = [r["skill_id"] for r in results]
            ph = ",".join("?" for _ in ids)
            content_rows = bconn.execute(
                f"SELECT skill_id, skill_md FROM skills_content WHERE skill_id IN ({ph})",
                ids,
            ).fetchall()
            content_map = {cr["skill_id"]: cr["skill_md"] for cr in content_rows}
            for r in results:
                md = content_map.get(r["skill_id"], "")
                if max_chars and len(md) > max_chars:
                    md = md[:max_chars] + "\n\n... [truncated]"
                r["skill_md"] = md
        finally:
            bconn.close()

    return results


def _list_distinct_values(column: str) -> list[str]:
    """Return sorted unique values from ``skills_index.<column>``."""
    values: set[str] = set()
    bundles = _resolve_all_bundles()
    if bundles:
        for bp in bundles:
            try:
                conn = sqlite3.connect(f"file:{bp}?mode=ro", uri=True)
                rows = conn.execute(
                    f"SELECT DISTINCT {column} FROM skills_index "
                    f"WHERE COALESCE({column}, '') != ''"
                ).fetchall()
                for row in rows:
                    val = str(row[0] or "").strip()
                    if val:
                        values.add(val)
            except Exception:
                continue
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        return sorted(values)

    idx_path = _index_db()
    if not idx_path.exists():
        raise FileNotFoundError(
            f"No bundle found and index database missing: {idx_path}\n"
            "Install a bundle with: langskills bundle-install"
        )

    conn = sqlite3.connect(f"file:{idx_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            f"SELECT DISTINCT {column} FROM skills_index "
            f"WHERE COALESCE({column}, '') != ''"
        ).fetchall()
        for row in rows:
            val = str(row[0] or "").strip()
            if val:
                values.add(val)
    finally:
        conn.close()
    return sorted(values)


def list_domains() -> list[str]:
    """Return sorted unique domain values from installed bundles/index."""
    return _list_distinct_values("domain")


def list_kinds() -> list[str]:
    """Return sorted unique skill_kind values from installed bundles/index."""
    return _list_distinct_values("skill_kind")


# ── formatters ───────────────────────────────────────────────────

def _local_skill_md_path(item: dict[str, Any]) -> str:
    """Best-effort local skill.md path from index metadata."""
    raw_dir = str(item.get("dir") or "").strip()
    if raw_dir:
        base = raw_dir.replace("\\", "/").rstrip("/")
    else:
        skill_id = str(item.get("skill_id") or "").strip()
        base = f"skills/by-skill/{skill_id}" if skill_id else ""
    if not base:
        return ""
    return f"{base}/skill.md"


def format_brief(results: list[dict[str, Any]], *, show_path: bool = False) -> str:
    """One line per result: score | domain | kind | title."""
    if not results:
        return "No results found."
    lines = []
    for i, r in enumerate(results, 1):
        score = r.get("overall_score") or 0
        domain = r.get("domain") or "-"
        kind = r.get("skill_kind") or "-"
        title = r.get("title") or "(untitled)"
        line = f"{i:>3}. [{score:.1f}] {domain:<14} {kind:<10} {title}"
        if show_path:
            path = _local_skill_md_path(r)
            if path:
                line += f"\n     path: {path}"
        lines.append(line)
    return "\n".join(lines)


def format_markdown(results: list[dict[str, Any]], *, show_path: bool = False) -> str:
    """Full Markdown output suitable for agent consumption."""
    if not results:
        return "No results found."
    parts = []
    for i, r in enumerate(results, 1):
        score = r.get("overall_score") or 0
        title = r.get("title") or "(untitled)"
        domain = r.get("domain") or "-"
        kind = r.get("skill_kind") or "-"
        source_type = r.get("source_type") or "-"
        skill_id = r.get("skill_id") or ""

        hdr = f"## {i}. {title}\n"
        meta = (
            f"- **Score:** {score:.1f}\n"
            f"- **Domain:** {domain}\n"
            f"- **Kind:** {kind}\n"
            f"- **Source type:** {source_type}\n"
            f"- **Skill ID:** `{skill_id[:12]}...`\n"
        )
        if show_path:
            path = _local_skill_md_path(r)
            if path:
                meta += f"- **Path:** `{path}`\n"
        body = ""
        if "skill_md" in r and r["skill_md"]:
            body = f"\n### Content\n\n{r['skill_md']}\n"

        parts.append(hdr + meta + body)
    return "\n---\n\n".join(parts)


def format_json(results: list[dict[str, Any]]) -> str:
    """JSON output."""
    # Drop heavy item_json field for cleaner output.
    cleaned = []
    for r in results:
        out = {k: v for k, v in r.items() if k != "item_json"}
        cleaned.append(out)
    return json.dumps(cleaned, indent=2, ensure_ascii=False)


# ── CLI ──────────────────────────────────────────────────────────

def cli_skill_search(argv: list[str] | None = None) -> int:
    """CLI entry point for ``langskills skill-search``."""
    import argparse

    p = argparse.ArgumentParser(
        prog="langskills skill-search",
        description="Search the LangSkills skill library",
    )
    p.add_argument("query", nargs="?", default="", help="Free-text search query")
    p.add_argument("--top", type=int, default=10, help="Max results (default: 10)")
    p.add_argument("--domains", action="store_true", help="List available domains and exit")
    p.add_argument("--kinds", action="store_true", help="List available skill kinds and exit")
    p.add_argument("--show-path", action="store_true", help="Show local skill.md paths in results")
    p.add_argument("--domain", default="", help="Filter by domain (linux, ml, web, ...)")
    p.add_argument("--kind", default="", help="Filter by skill_kind (github, arxiv, ...)")
    p.add_argument("--source-type", default="", help="Filter by source_type (github, journal, ...)")
    p.add_argument("--min-score", type=float, default=0.0, help="Minimum overall_score")
    p.add_argument("--content", action="store_true", help="Include full skill.md content (joins bundle DB)")
    p.add_argument("--max-chars", type=int, default=4000, help="Truncate skill content (0=unlimited, default: 4000)")
    p.add_argument(
        "--format",
        choices=["brief", "markdown", "json"],
        default="brief",
        help="Output format (default: brief)",
    )
    p.add_argument("--brief", action="store_true", help="Shorthand for --format brief")

    args = p.parse_args(argv)

    fmt = "brief" if args.brief else args.format

    if args.domains:
        try:
            domains = list_domains()
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print("\n".join(domains) if domains else "No domains found.")
        return 0

    if args.kinds:
        try:
            kinds = list_kinds()
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print("\n".join(kinds) if kinds else "No kinds found.")
        return 0

    if not str(args.query or "").strip():
        p.error("query is required unless --domains or --kinds is set")

    try:
        results = search_skills(
            args.query,
            top_k=args.top,
            domain=args.domain,
            kind=args.kind,
            source_type=args.source_type,
            min_score=args.min_score,
            content=args.content,
            max_chars=args.max_chars,
        )
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if fmt == "brief":
        print(format_brief(results, show_path=bool(args.show_path)))
    elif fmt == "markdown":
        print(format_markdown(results, show_path=bool(args.show_path)))
    else:
        print(format_json(results))

    return 0


if __name__ == "__main__":
    raise SystemExit(cli_skill_search())
