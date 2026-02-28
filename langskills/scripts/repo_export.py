from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Iterable

from ..utils.redact import redact_text
from ..utils.time import utc_now_iso_z


_TEXT_EXTS = {
    ".log",
    ".jsonl",
    ".json",
    ".md",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".txt",
}


def _is_text_path(path: Path) -> bool:
    return path.suffix.lower() in _TEXT_EXTS


def _iter_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_file():
            yield p


def _copy_tree(
    *,
    src_root: Path,
    dst_root: Path,
    redact: bool,
    redact_urls: bool,
    max_file_bytes: int,
) -> dict[str, Any]:
    from typing import Any

    copied: list[str] = []
    redacted_files: list[str] = []
    skipped: list[dict[str, str]] = []

    for src in _iter_files(src_root):
        try:
            rel = src.relative_to(src_root).as_posix()
        except Exception:
            rel = src.name

        # Never export .env files.
        if src.name == ".env" or rel.endswith("/.env"):
            skipped.append({"path": rel, "reason": "env"})
            continue

        try:
            size = int(src.stat().st_size)
        except OSError:
            size = 0

        if max_file_bytes > 0 and size > max_file_bytes:
            skipped.append({"path": rel, "reason": f"too_large:{size}"})
            continue

        dst = dst_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)

        if redact and _is_text_path(src):
            try:
                text = src.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                try:
                    text = src.read_text(encoding="utf-8-sig")
                except Exception:
                    shutil.copy2(src, dst)
                    copied.append(rel)
                    continue
            except Exception:
                shutil.copy2(src, dst)
                copied.append(rel)
                continue

            dst.write_text(redact_text(text, redact_urls=redact_urls), encoding="utf-8")
            copied.append(rel)
            redacted_files.append(rel)
            continue

        shutil.copy2(src, dst)
        copied.append(rel)

    return {"copied": copied, "redacted": redacted_files, "skipped": skipped}


def cli_repo_export(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills repo-export")
    parser.add_argument("--out", required=True, help="Output directory for the export bundle")
    parser.add_argument("--captures", default="captures", help="Path to captures/ (default: captures)")
    parser.add_argument("--docs", default="docs", help="Path to docs/ (default: docs)")
    parser.add_argument("--redact", action="store_true", help="Redact secrets (and optionally URLs)")
    parser.add_argument("--redact-urls", action="store_true", help="Also redact URLs when --redact is enabled")
    parser.add_argument("--max-file-bytes", type=int, default=25 * 1024 * 1024, help="Skip files larger than this (default: 25MB)")
    ns = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    out_dir = Path(ns.out)
    if not out_dir.is_absolute():
        out_dir = (repo_root / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    captures = Path(ns.captures)
    if not captures.is_absolute():
        captures = (repo_root / captures).resolve()
    docs = Path(ns.docs)
    if not docs.is_absolute():
        docs = (repo_root / docs).resolve()

    bundle_root = out_dir / f"repo_export_{utc_now_iso_z().replace(':', '').replace('-', '')}"
    bundle_root.mkdir(parents=True, exist_ok=True)

    exported: dict[str, Any] = {
        "schema_version": 1,
        "exported_at": utc_now_iso_z(),
        "repo_root": repo_root.as_posix(),
        "bundle_root": bundle_root.as_posix(),
        "redact": bool(ns.redact),
        "redact_urls": bool(ns.redact and ns.redact_urls),
        "max_file_bytes": int(ns.max_file_bytes or 0),
        "sources": [],
        "summary": {},
    }

    total_copied = 0
    total_redacted = 0
    total_skipped = 0

    for name, src in (("captures", captures), ("docs", docs)):
        if not src.exists():
            continue
        dst = bundle_root / name
        res = _copy_tree(
            src_root=src,
            dst_root=dst,
            redact=bool(ns.redact),
            redact_urls=bool(ns.redact and ns.redact_urls),
            max_file_bytes=int(ns.max_file_bytes or 0),
        )
        exported["sources"].append({"name": name, "src": src.as_posix(), "dst": dst.as_posix(), **res})
        total_copied += len(res.get("copied") or [])
        total_redacted += len(res.get("redacted") or [])
        total_skipped += len(res.get("skipped") or [])

    # Copy a few top-level plan/docs files for context (best-effort).
    for fn in ["README.md", "plan.md", "plan_githubagent.md"]:
        p = repo_root / fn
        if not p.exists() or not p.is_file():
            continue
        dst = bundle_root / fn
        dst.parent.mkdir(parents=True, exist_ok=True)
        if bool(ns.redact) and _is_text_path(p):
            dst.write_text(
                redact_text(
                    p.read_text(encoding="utf-8", errors="replace"),
                    redact_urls=bool(ns.redact and ns.redact_urls),
                ),
                encoding="utf-8",
            )
            total_redacted += 1
        else:
            shutil.copy2(p, dst)
        total_copied += 1

    exported["summary"] = {"files_copied": total_copied, "files_redacted": total_redacted, "files_skipped": total_skipped}
    (bundle_root / "export_manifest.json").write_text(json.dumps(exported, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"bundle": bundle_root.as_posix(), **exported["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_repo_export())
