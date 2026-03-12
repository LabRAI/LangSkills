"""Build self-contained SQLite bundles from skills/by-skill/.

Lite bundle:  skills_index + skills_content (metadata_yaml, skill_md, library_md) + FTS5
Full bundle:  above + source_json, lineage_json, reference_json
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from ..utils.fs import list_skill_dirs, read_text
from ..utils.yaml_simple import parse_metadata_yaml_text

# ── constants ────────────────────────────────────────────────────

_BATCH_SIZE = 500
_DEFAULT_WORKERS = 16

# Non-research tech domains
_TECH_DOMAINS = [
    "linux", "web", "programming", "devtools", "security",
    "observability", "data", "cloud", "ml", "llm",
]

# ── research journal classification ──────────────────────────────

RESEARCH_JOURNAL_RULES: list[tuple[str, callable]] = [
    ("plos-one",        lambda u: "journal.pone" in u),
    ("plos-compbio",    lambda u: "journal.pcbi" in u),
    ("plos-biology",    lambda u: "journal.pbio" in u),
    ("plos-medicine",   lambda u: "journal.pmed" in u),
    ("plos-ntd",        lambda u: "journal.pntd" in u),
    ("plos-pathogens",  lambda u: "journal.ppat" in u),
    ("plos-genetics",   lambda u: "journal.pgen" in u),
    ("arxiv",           lambda u: "arxiv" in u),
    ("elife",           lambda u: "elife" in u),
    ("other",           lambda u: True),  # fallback
]


def _classify_research_journal(source_url: str) -> str:
    """Classify a research skill into a journal sub-group by source URL."""
    url_lower = (source_url or "").lower()
    for name, matcher in RESEARCH_JOURNAL_RULES:
        if matcher(url_lower):
            return name
    return "other"

_INDEX_COLS = [
    "skill_id",
    "domain",
    "profile",
    "source_type",
    "source_url",
    "title",
    "overall_score",
    "skill_kind",
    "language",
    "source_id",
    "primary_source_id",
]

_CONTENT_LITE_COLS = ["skill_id", "metadata_yaml", "skill_md", "library_md"]
_CONTENT_FULL_EXTRA = ["source_json", "lineage_json", "reference_json"]

# ── DDL ──────────────────────────────────────────────────────────

_DDL_BUNDLE_META = """
CREATE TABLE IF NOT EXISTS bundle_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
)
"""

_DDL_SKILLS_INDEX = """
CREATE TABLE IF NOT EXISTS skills_index (
    skill_id          TEXT PRIMARY KEY,
    domain            TEXT,
    profile           TEXT,
    source_type       TEXT,
    source_url        TEXT,
    title             TEXT,
    overall_score     REAL,
    skill_kind        TEXT,
    language          TEXT,
    source_id         TEXT,
    primary_source_id TEXT
)
"""

_DDL_SKILLS_CONTENT_LITE = """
CREATE TABLE IF NOT EXISTS skills_content (
    skill_id      TEXT PRIMARY KEY,
    metadata_yaml TEXT,
    skill_md      TEXT,
    library_md    TEXT
)
"""

_DDL_SKILLS_CONTENT_FULL = """
CREATE TABLE IF NOT EXISTS skills_content (
    skill_id       TEXT PRIMARY KEY,
    metadata_yaml  TEXT,
    skill_md       TEXT,
    library_md     TEXT,
    source_json    TEXT,
    lineage_json   TEXT,
    reference_json TEXT
)
"""

_DDL_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS skills_fts
USING fts5(title, domain, skill_id UNINDEXED, content='skills_index', content_rowid='rowid')
"""

# ── file readers ─────────────────────────────────────────────────

def _safe_read(path: Path) -> str:
    """Read a file, return empty string on failure."""
    try:
        if path.exists():
            return path.read_text(encoding="utf-8")
    except Exception:
        pass
    return ""


def _read_skill_lite(skill_dir: Path) -> dict[str, Any] | None:
    """Read metadata.yaml + skill.md + library.md from a skill directory."""
    meta_path = skill_dir / "metadata.yaml"
    skill_path = skill_dir / "skill.md"
    if not meta_path.exists() or not skill_path.exists():
        return None

    meta_text = _safe_read(meta_path)
    if not meta_text.strip():
        return None

    meta = parse_metadata_yaml_text(meta_text)
    skill_id = str(meta.get("skill_id") or skill_dir.name or "").strip()
    if not skill_id:
        return None

    return {
        "skill_id": skill_id,
        "metadata_yaml": meta_text,
        "skill_md": _safe_read(skill_path),
        "library_md": _safe_read(skill_dir / "library.md"),
        # Index fields extracted from metadata
        "domain": str(meta.get("domain") or meta.get("profile") or ""),
        "profile": str(meta.get("profile") or meta.get("domain") or ""),
        "source_type": str(meta.get("source_type") or ""),
        "source_url": str(meta.get("source_url") or ""),
        "title": str(meta.get("title") or ""),
        "overall_score": float(meta.get("overall_score") or 0),
        "skill_kind": str(
            meta.get("skill_kind")
            or meta.get("topic")
            or meta.get("source_type")
            or "unknown"
        ),
        "language": str(meta.get("language") or meta.get("lang") or "en"),
        "source_id": str(
            meta.get("source_id")
            or meta.get("source_artifact_id")
            or meta.get("primary_source_id")
            or ""
        ),
        "primary_source_id": str(
            meta.get("primary_source_id")
            or meta.get("source_id")
            or meta.get("source_artifact_id")
            or ""
        ),
    }


def _read_skill_full(skill_dir: Path) -> dict[str, Any] | None:
    """Read all files from a skill directory (lite + source/lineage/reference)."""
    result = _read_skill_lite(skill_dir)
    if result is None:
        return None

    result["source_json"] = _safe_read(skill_dir / "source.json")
    result["lineage_json"] = _safe_read(skill_dir / "lineage.json")

    # Serialize reference/*.md into a JSON dict
    ref_dir = skill_dir / "reference"
    refs: dict[str, str] = {}
    if ref_dir.is_dir():
        try:
            for f in sorted(ref_dir.iterdir()):
                if f.is_file() and f.suffix == ".md":
                    refs[f.stem] = _safe_read(f)
        except OSError:
            pass
    result["reference_json"] = json.dumps(refs, ensure_ascii=False) if refs else ""

    return result


# ── DB construction ──────────────────────────────────────────────

def _build_bundle_db(
    out_path: Path,
    by_skill_root: Path,
    bundle_type: str,
    workers: int,
    batch_size: int = _BATCH_SIZE,
    domain_filter: set[str] | None = None,
    exclude_domains: set[str] | None = None,
    min_score: float = 0.0,
    journal_filter: str | None = None,
) -> int:
    """Build the SQLite bundle database.

    Parameters
    ----------
    domain_filter : set[str] | None
        If given, only include skills whose domain is in this set.
    exclude_domains : set[str] | None
        If given, exclude skills whose domain is in this set (for "other" bundle).
    min_score : float
        Exclude skills with overall_score below this threshold.
    journal_filter : str | None
        For research domain, only include skills matching this journal sub-group.

    Returns the number of skills inserted.
    """
    reader = _read_skill_full if bundle_type == "full" else _read_skill_lite

    # Discover skill directories
    print(f"Scanning {by_skill_root} for skill directories ...", file=sys.stderr)
    skill_dirs = list_skill_dirs(by_skill_root)
    total = len(skill_dirs)
    print(f"Found {total:,} skill directories.", file=sys.stderr)

    if total == 0:
        return 0

    # Create DB in a temp file, then atomic-rename
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".sqlite", dir=out_path.parent)
    os.close(tmp_fd)

    try:
        conn = sqlite3.connect(tmp_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(_DDL_BUNDLE_META)
        conn.execute(_DDL_SKILLS_INDEX)
        if bundle_type == "full":
            conn.execute(_DDL_SKILLS_CONTENT_FULL)
        else:
            conn.execute(_DDL_SKILLS_CONTENT_LITE)
        conn.commit()

        inserted = 0
        batch: list[dict[str, Any]] = []

        def flush_batch(buf: list[dict[str, Any]]) -> None:
            nonlocal inserted
            if not buf:
                return
            # Insert index rows
            idx_placeholders = ",".join("?" for _ in _INDEX_COLS)
            conn.executemany(
                f"INSERT OR REPLACE INTO skills_index ({','.join(_INDEX_COLS)}) "
                f"VALUES ({idx_placeholders})",
                [[row.get(c, "") for c in _INDEX_COLS] for row in buf],
            )
            # Insert content rows
            content_cols = (
                _CONTENT_LITE_COLS + _CONTENT_FULL_EXTRA
                if bundle_type == "full"
                else _CONTENT_LITE_COLS
            )
            cph = ",".join("?" for _ in content_cols)
            conn.executemany(
                f"INSERT OR REPLACE INTO skills_content ({','.join(content_cols)}) "
                f"VALUES ({cph})",
                [[row.get(c, "") for c in content_cols] for row in buf],
            )
            conn.commit()
            inserted += len(buf)

        # Parallel read → sequential insert
        print(f"Reading skills with {workers} workers ...", file=sys.stderr)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(reader, d): d for d in skill_dirs}
            done = 0
            for fut in as_completed(futures):
                done += 1
                if done % 5000 == 0 or done == total:
                    print(
                        f"  read {done:,}/{total:,} ({100 * done // total}%)",
                        file=sys.stderr,
                    )
                result = fut.result()
                if result is None:
                    continue
                # Domain filter
                d = (result.get("domain") or "").lower()
                if domain_filter and d not in domain_filter:
                    continue
                if exclude_domains and d in exclude_domains:
                    continue
                # Min score filter
                if min_score > 0 and (result.get("overall_score") or 0) < min_score:
                    continue
                # Research journal sub-group filter
                if journal_filter and (result.get("domain") or "").lower() == "research":
                    j = _classify_research_journal(result.get("source_url", ""))
                    if j != journal_filter:
                        continue
                batch.append(result)
                if len(batch) >= batch_size:
                    flush_batch(batch)
                    batch.clear()

        flush_batch(batch)
        batch.clear()

        print(f"Inserted {inserted:,} skills. Building FTS5 index ...", file=sys.stderr)

        # Build FTS5
        try:
            conn.execute(_DDL_FTS)
            conn.execute("INSERT INTO skills_fts(skills_fts) VALUES('rebuild')")
            conn.commit()
            print("FTS5 index built.", file=sys.stderr)
        except Exception as exc:
            print(f"Warning: FTS5 not available ({exc}), skipping.", file=sys.stderr)

        conn.close()
        os.replace(tmp_path, out_path)
        return inserted
    except BaseException:
        conn.close()
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ── compression / checksums ──────────────────────────────────────

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _compress_zstd(src: Path, dst: Path) -> bool:
    """Compress with zstd if available, fallback to gzip."""
    try:
        import zstandard as zstd

        cctx = zstd.ZstdCompressor(level=9, threads=-1)
        with open(src, "rb") as fin, open(dst, "wb") as fout:
            cctx.copy_stream(fin, fout)
        return True
    except ImportError:
        gz_dst = dst.with_suffix(".gz")
        with open(src, "rb") as fin, gzip.open(gz_dst, "wb", compresslevel=6) as fout:
            while True:
                chunk = fin.read(1 << 20)
                if not chunk:
                    break
                fout.write(chunk)
        print(
            f"Warning: zstandard not installed, wrote gzip: {gz_dst.name}",
            file=sys.stderr,
        )
        return False


def _write_checksum(path: Path) -> Path:
    """Write a .sha256 sidecar file."""
    digest = _sha256_file(path)
    checksum_path = path.with_suffix(path.suffix + ".sha256")
    checksum_path.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return checksum_path


# ── bundle metadata ──────────────────────────────────────────────

def _write_bundle_meta(db_path: Path, version: str, bundle_type: str, count: int) -> None:
    conn = sqlite3.connect(str(db_path))
    meta = {
        "version": version,
        "created_at": __import__("datetime").datetime.now(
            tz=__import__("datetime").timezone.utc
        ).isoformat(),
        "total_skills": str(count),
        "bundle_type": bundle_type,
    }
    for k, v in meta.items():
        conn.execute(
            "INSERT OR REPLACE INTO bundle_meta (key, value) VALUES (?, ?)", (k, v)
        )
    conn.commit()
    conn.close()


# ── public API ───────────────────────────────────────────────────

def build_lite_bundle(
    repo_root: Path,
    out_dir: Path,
    version: str,
    workers: int = _DEFAULT_WORKERS,
) -> Path:
    """Build a lite bundle and return the path to the .sqlite file."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"langskills-bundle-lite-v{version}"
    db_path = out_dir / f"{stem}.sqlite"
    by_skill = repo_root / "skills" / "by-skill"

    count = _build_bundle_db(db_path, by_skill, "lite", workers)
    _write_bundle_meta(db_path, version, "lite", count)
    _write_checksum(db_path)

    # Compress
    zst_path = db_path.with_suffix(".sqlite.zst")
    _compress_zstd(db_path, zst_path)
    if zst_path.exists():
        _write_checksum(zst_path)

    print(f"\nLite bundle: {db_path} ({count:,} skills)", file=sys.stderr)
    return db_path


def build_full_bundle(
    repo_root: Path,
    out_dir: Path,
    version: str,
    workers: int = _DEFAULT_WORKERS,
) -> Path:
    """Build a full bundle and return the path to the .sqlite file."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"langskills-bundle-full-v{version}"
    db_path = out_dir / f"{stem}.sqlite"
    by_skill = repo_root / "skills" / "by-skill"

    count = _build_bundle_db(db_path, by_skill, "full", workers)
    _write_bundle_meta(db_path, version, "full", count)
    _write_checksum(db_path)

    print(f"\nFull bundle: {db_path} ({count:,} skills)", file=sys.stderr)
    return db_path


# ── split by domain ──────────────────────────────────────────────

def build_split_bundles(
    repo_root: Path,
    out_dir: Path,
    version: str,
    workers: int = _DEFAULT_WORKERS,
    bundle_type: str = "lite",
    min_score: float = 0.0,
    domains: list[str] | None = None,
) -> list[Path]:
    """Build independent bundles for each domain (research split by journal).

    Parameters
    ----------
    domains : list[str] | None
        If given, only build bundles for these domains.
        Use ``"research-arxiv"`` syntax for specific research sub-groups.
    min_score : float
        Exclude skills below this overall_score.

    Returns list of generated .sqlite paths.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    by_skill = repo_root / "skills" / "by-skill"
    results: list[Path] = []

    # Determine which domains/journals to build
    research_journals = [name for name, _ in RESEARCH_JOURNAL_RULES]

    if domains:
        # Parse user-specified domains: "linux", "research-arxiv", etc.
        tech_targets = []
        research_targets = []
        for d in domains:
            if d.startswith("research-"):
                journal = d[len("research-"):]
                research_targets.append(journal)
            elif d == "research":
                research_targets = research_journals
            else:
                tech_targets.append(d)
    else:
        tech_targets = list(_TECH_DOMAINS)
        research_targets = research_journals

    # Build tech domain bundles
    for domain in tech_targets:
        stem = f"langskills-bundle-{bundle_type}-{domain}-v{version}"
        db_path = out_dir / f"{stem}.sqlite"
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"Building domain bundle: {domain}", file=sys.stderr)
        count = _build_bundle_db(
            db_path, by_skill, bundle_type, workers,
            domain_filter={domain}, min_score=min_score,
        )
        if count > 0:
            _write_bundle_meta(db_path, version, bundle_type, count)
            _write_checksum(db_path)
            print(f"  {domain}: {count:,} skills → {db_path.name}", file=sys.stderr)
            results.append(db_path)
        else:
            # Remove empty database
            db_path.unlink(missing_ok=True)
            print(f"  {domain}: 0 skills, skipped.", file=sys.stderr)

    # Build research journal sub-group bundles
    for journal in research_targets:
        stem = f"langskills-bundle-{bundle_type}-research-{journal}-v{version}"
        db_path = out_dir / f"{stem}.sqlite"
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"Building research sub-bundle: research-{journal}", file=sys.stderr)
        count = _build_bundle_db(
            db_path, by_skill, bundle_type, workers,
            domain_filter={"research"}, min_score=min_score,
            journal_filter=journal,
        )
        if count > 0:
            _write_bundle_meta(db_path, version, bundle_type, count)
            _write_checksum(db_path)
            print(f"  research-{journal}: {count:,} skills → {db_path.name}", file=sys.stderr)
            results.append(db_path)
        else:
            db_path.unlink(missing_ok=True)
            print(f"  research-{journal}: 0 skills, skipped.", file=sys.stderr)

    # Build "other" bundle for skills not matching any known domain
    if not domains:
        all_known = set(_TECH_DOMAINS) | {"research"}
        stem = f"langskills-bundle-{bundle_type}-other-v{version}"
        db_path = out_dir / f"{stem}.sqlite"
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"Building 'other' bundle (domains not in {sorted(all_known)})", file=sys.stderr)
        count = _build_bundle_db(
            db_path, by_skill, bundle_type, workers,
            exclude_domains=all_known, min_score=min_score,
        )
        if count > 0:
            _write_bundle_meta(db_path, version, bundle_type, count)
            _write_checksum(db_path)
            print(f"  other: {count:,} skills → {db_path.name}", file=sys.stderr)
            results.append(db_path)
        else:
            db_path.unlink(missing_ok=True)
            print(f"  other: 0 skills, skipped.", file=sys.stderr)

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"Split build complete: {len(results)} bundles generated.", file=sys.stderr)
    return results


# ── release notes ────────────────────────────────────────────────

def generate_release_notes(repo_root: Path, version: str) -> str:
    """Generate Markdown release notes for a bundle release."""
    by_skill = repo_root / "skills" / "by-skill"
    total = 0
    try:
        total = sum(1 for d in by_skill.iterdir() if d.is_dir())
    except OSError:
        pass

    return f"""# LangSkills Bundle v{version}

## Contents

- **{total:,}** evidence-backed skills
- Domains: linux, ml, cloud, security, web, data, devtools, programming, observability, research, llm
- Sources: web, GitHub, ArXiv, academic journals, StackOverflow, forums

## Bundles

| File | Description |
|------|-------------|
| `langskills-bundle-lite-v{version}.sqlite` | Index + skill content (~500MB) |
| `langskills-bundle-lite-v{version}.sqlite.zst` | Compressed lite bundle |
| `langskills-bundle-full-v{version}.sqlite` | Full bundle with sources + references |

## Installation

```bash
# Install matching bundles for the current project
langskills-rai bundle-install --auto

# Or install a specific domain bundle from Hugging Face
langskills-rai bundle-install --domain linux
```

Pre-built bundles are distributed via the Hugging Face dataset
`Tommysha/langskills-bundles`. The repo-local `dist/` directory is for local
build outputs and is not the public distribution channel.

## Checksums

SHA-256 checksums are provided as `.sha256` sidecar files.
"""


# ── CLI ──────────────────────────────────────────────────────────

def cli_build_bundle(argv: list[str] | None = None) -> int:
    """CLI entry point for ``langskills build-bundle``."""
    parser = argparse.ArgumentParser(
        prog="langskills-rai build-bundle",
        description="Build a self-contained SQLite skill bundle",
    )
    parser.add_argument(
        "--type",
        choices=["lite", "full", "both"],
        default="lite",
        help="Bundle type (default: lite)",
    )
    parser.add_argument(
        "--out",
        default="dist",
        help="Output directory (default: dist/)",
    )
    parser.add_argument(
        "--version",
        default="",
        help="Version string (default: auto from date)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=_DEFAULT_WORKERS,
        help=f"Parallel reader threads (default: {_DEFAULT_WORKERS})",
    )
    parser.add_argument(
        "--split-by-domain",
        action="store_true",
        help="Build independent bundles for each domain/journal",
    )
    parser.add_argument(
        "--domain",
        default="",
        help="Comma-separated domain list (e.g. linux,web,research-arxiv)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help="Exclude skills with overall_score below this threshold",
    )

    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = repo_root / out_dir

    version = args.version or __import__("datetime").date.today().strftime("%Y%m%d")

    domain_list = [d.strip() for d in args.domain.split(",") if d.strip()] if args.domain else None

    if args.split_by_domain:
        build_split_bundles(
            repo_root, out_dir, version, args.workers,
            bundle_type=args.type if args.type != "both" else "lite",
            min_score=args.min_score,
            domains=domain_list,
        )
    else:
        if args.type in ("lite", "both"):
            build_lite_bundle(repo_root, out_dir, version, args.workers)
        if args.type in ("full", "both"):
            build_full_bundle(repo_root, out_dir, version, args.workers)

    return 0


if __name__ == "__main__":
    raise SystemExit(cli_build_bundle())
