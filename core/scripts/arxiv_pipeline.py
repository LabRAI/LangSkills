from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from ..config import canonicalize_source_url
from ..env import load_dotenv
from ..llm.factory import create_llm_from_env
from ..llm.types import ChatMessage, LlmClient
from ..sources.arxiv import discover_arxiv_sources
from ..sources.artifacts import write_source_artifact
from ..sources.github import github_fetch_readme_excerpt_raw, parse_github_full_name_from_url
from ..sources.linker import link_github_repos_from_paper_entry
from ..sources.types import SourceInput
from ..skills.gate import run_skill_gate
from ..skills.generate import generate_one_skill
from ..utils.fs import ensure_dir, make_run_dir, write_json_atomic, write_text_atomic
from ..utils.hashing import slugify
from ..utils.text import truncate_text
from ..utils.time import utc_now_iso_z
try:
    from .validate_skills import validate_skills
except ImportError:
    validate_skills = None


def _write_manifest(run_dir: Path, topic: str, sources: list[SourceInput]) -> None:
    manifest = {
        "schema_version": 1,
        "topic": topic,
        "created_at": utc_now_iso_z(),
        "sources": [
            {
                "source_type": s.source_type,
                "url": s.url,
                "title": s.title,
                "skill_kind": s.extra.get("skill_kind"),
                "language": s.extra.get("language"),
            }
            for s in sources
        ],
    }
    write_json_atomic(run_dir / "manifest.json", manifest)


def _resolve_pdf_url(src: SourceInput) -> str:
    extra = src.extra if isinstance(src.extra, dict) else {}
    pdf_url = str(extra.get("pdf_url") or "").strip()
    arxiv_id = str(extra.get("arxiv_id") or "").strip()
    if not pdf_url and arxiv_id:
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    return pdf_url


def _download_pdf_to_temp(
    pdf_url: str,
    *,
    timeout_ms: int,
    max_mb: int,
    dest_path: Path | None = None,
) -> Path:
    import requests

    timeout_sec = max(1.0, float(timeout_ms or 45_000) / 1000.0)
    max_bytes = 0
    try:
        max_bytes = int(max_mb) * 1024 * 1024 if int(max_mb) > 0 else 0
    except Exception:
        max_bytes = 0

    tmp = tempfile.NamedTemporaryFile(prefix="langskills-arxiv-", suffix=".pdf", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()

    total = 0
    with requests.get(pdf_url, stream=True, timeout=timeout_sec) as resp:
        resp.raise_for_status()
        with tmp_path.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=128 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if max_bytes and total > max_bytes:
                    raise RuntimeError(f"PDF too large (>{max_mb} MB): {pdf_url}")
                f.write(chunk)
    if dest_path:
        ensure_dir(dest_path.parent)
        try:
            os.replace(tmp_path, dest_path)
            return dest_path
        except Exception:
            pass
    return tmp_path


def _extract_pdf_text(path: Path, *, max_chars: int) -> str:
    text = ""
    err: Exception | None = None
    try:
        from pdfminer.high_level import extract_text

        text = extract_text(str(path))
    except Exception as e:
        err = e

    if not text:
        pdftotext = shutil.which("pdftotext")
        if pdftotext:
            try:
                out = subprocess.check_output(
                    [pdftotext, "-layout", "-nopgbrk", str(path), "-"],
                    stderr=subprocess.STDOUT,
                )
                text = out.decode("utf-8", errors="replace")
            except Exception as e:
                err = e

    if not text:
        if err:
            raise RuntimeError(f"PDF text extraction failed: {err}") from err
        raise RuntimeError("PDF text extraction failed: no text output")

    text = text.replace("\x00", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return truncate_text(text, int(max_chars or 200_000))


def _extract_abstract_from_src_text(src_text: str) -> str:
    s = str(src_text or "")
    if not s:
        return ""
    m = re.search(r"ABSTRACT:\n(.+)", s, flags=re.DOTALL | re.IGNORECASE)
    if not m:
        return ""
    abstract = m.group(1).strip()
    if "COMMENT:" in abstract:
        abstract = abstract.split("COMMENT:", 1)[0].strip()
    return abstract


def _seen_key_for_source(src: SourceInput) -> str:
    extra = src.extra if isinstance(src.extra, dict) else {}
    arxiv_id = str(extra.get("arxiv_id") or "").strip()
    if arxiv_id:
        return arxiv_id
    url = canonicalize_source_url(str(src.url or "").strip()) or str(src.url or "").strip()
    return url


def _open_seen_db(path: Path) -> sqlite3.Connection:
    ensure_dir(path.parent)
    conn = sqlite3.connect(path.as_posix())
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS arxiv_seen (
            key TEXT PRIMARY KEY,
            arxiv_id TEXT,
            topic TEXT,
            first_seen_at TEXT,
            last_status TEXT,
            last_run_id TEXT,
            updated_at TEXT
        )
        """
    )
    conn.commit()
    return conn


def _filter_seen_sources(
    *,
    conn: sqlite3.Connection,
    sources: list[SourceInput],
    topic: str,
    max_new: int | None,
    run_id: str,
) -> tuple[list[SourceInput], list[str]]:
    groups: list[tuple[str, list[SourceInput]]] = []
    index: dict[str, int] = {}
    for src in sources:
        key = _seen_key_for_source(src)
        if key not in index:
            index[key] = len(groups)
            groups.append((key, []))
        groups[index[key]][1].append(src)

    claimed: list[str] = []
    kept: list[tuple[str, list[SourceInput]]] = []
    for key, group in groups:
        if max_new is not None and max_new > 0 and len(kept) >= max_new:
            continue
        if not key:
            kept.append((key, group))
            continue
        try:
            cur = conn.execute(
                "INSERT OR IGNORE INTO arxiv_seen (key, arxiv_id, topic, first_seen_at, last_status, last_run_id, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    key,
                    key,
                    topic,
                    utc_now_iso_z(),
                    "claimed",
                    run_id,
                    utc_now_iso_z(),
                ),
            )
            conn.commit()
        except Exception:
            # If DB fails, keep the group to avoid dropping data.
            kept.append((key, group))
            continue
        if getattr(cur, "rowcount", 0) <= 0:
            # already seen by another process
            continue
        claimed.append(key)
        kept.append((key, group))

    flat: list[SourceInput] = []
    for _, group in kept:
        flat.extend(group)
    return flat, claimed


def _mark_seen_done(conn: sqlite3.Connection, keys: list[str], run_id: str) -> None:
    if not keys:
        return
    now = utc_now_iso_z()
    for k in keys:
        try:
            conn.execute(
                "UPDATE arxiv_seen SET last_status = ?, last_run_id = ?, updated_at = ? WHERE key = ?",
                ("done", run_id, now, k),
            )
        except Exception:
            continue
    try:
        conn.commit()
    except Exception:
        pass


def _chunk_text(text: str, *, chunk_chars: int) -> list[str]:
    cleaned = str(text or "").strip()
    if not cleaned:
        return []
    lim = max(500, int(chunk_chars or 4000))
    paras = [p.strip() for p in re.split(r"\n{2,}", cleaned) if p.strip()]
    if not paras:
        paras = [cleaned]
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for p in paras:
        if len(p) > lim:
            if buf:
                chunks.append("\n\n".join(buf))
                buf = []
                size = 0
            for i in range(0, len(p), lim):
                chunks.append(p[i : i + lim])
            continue
        next_size = size + len(p) + (2 if buf else 0)
        if buf and next_size > lim:
            chunks.append("\n\n".join(buf))
            buf = [p]
            size = len(p)
            continue
        buf.append(p)
        size = next_size
    if buf:
        chunks.append("\n\n".join(buf))
    return chunks


def _summarize_text_in_chunks(
    *,
    llm: LlmClient | None,
    text: str,
    title: str,
    source_url: str,
    language: str,
    chunk_chars: int,
    max_chunks: int,
    timeout_ms: int,
    run_dir: Path,
    summary_basename: str,
) -> tuple[str, str, str, int]:
    if not llm:
        return "", "missing_llm", "", 0
    cleaned = str(text or "").strip()
    if not cleaned:
        return "", "empty", "", 0

    chunks = _chunk_text(cleaned, chunk_chars=chunk_chars)
    if len(chunks) <= 1:
        return "", "single_chunk", "", len(chunks)

    truncated = False
    if max_chunks > 0 and len(chunks) > max_chunks:
        chunks = chunks[: max(1, int(max_chunks))]
        truncated = True

    total = len(chunks)
    lang = str(language or "en").strip() or "en"

    def _summarize_one_chunk(idx: int, chunk: str) -> tuple[int, str]:
        system = (
            "You are a careful research summarizer. "
            f"Write in {lang}. "
            "Summarize the given chunk into ONE detailed paragraph (5-10 sentences). "
            "Preserve concrete details like datasets, metrics, model sizes, and steps. "
            "Do not invent; if something is missing, say 'not provided'. "
            "Output ONLY a JSON object with key: summary."
        )
        user = json.dumps(
            {
                "title": title,
                "source_url": source_url,
                "chunk_index": idx,
                "chunk_total": total,
                "text": chunk,
            },
            ensure_ascii=False,
            indent=2,
        )
        out = llm.chat_json(
            messages=[ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)],
            temperature=0.0,
            timeout_ms=int(timeout_ms or 60_000),
        )
        summary = str(out.get("summary") or "").strip()
        if not summary:
            raise RuntimeError(f"chunk_summary_empty idx={idx}")
        return idx, summary

    with ThreadPoolExecutor(max_workers=min(len(chunks), 8)) as pool:
        futures = {pool.submit(_summarize_one_chunk, idx, chunk): idx for idx, chunk in enumerate(chunks, start=1)}
        results: dict[int, str] = {}
        for f in as_completed(futures):
            idx, summary = f.result()
            results[idx] = summary
    summaries = [results[i] for i in sorted(results)]

    summary_text = "\n\n".join(summaries).strip()
    if not summary_text:
        return "", "empty_summary", "", len(chunks)

    summary_dir = run_dir / "summaries"
    ensure_dir(summary_dir)
    out_path = summary_dir / f"{summary_basename}.chunked_summary.txt"
    write_text_atomic(out_path, summary_text)
    try:
        rel_path = out_path.relative_to(run_dir).as_posix()
    except Exception:
        rel_path = out_path.as_posix()
    status = "ok_truncated" if truncated else "ok"
    return summary_text, status, rel_path, len(chunks)


def _resolve_extractthinker_python(repo_root: Path, override: str | None) -> Path | None:
    if override:
        return Path(override).expanduser()
    try:
        py = Path(sys.executable).resolve()
        return py if py.exists() else None
    except Exception:
        return None


def _run_extractthinker(
    *,
    repo_root: Path,
    pdf_path: Path,
    out_path: Path,
    model: str | None,
    python_bin: Path | None,
    env_path: Path | None,
) -> tuple[str, str]:
    if not pdf_path or not pdf_path.exists():
        return "missing_pdf", ""
    if not python_bin or not python_bin.exists():
        return "missing_python", ""

    env = os.environ.copy()
    if env_path:
        env["ET_ENV_PATH"] = str(env_path)
    env["ET_PDF_PATH"] = str(pdf_path)
    env["ET_OUT_PATH"] = str(out_path)
    if model:
        env["ET_MODEL"] = str(model)

    script = textwrap.dedent(
        """
        import json
        import os
        from dotenv import load_dotenv
        from pydantic import Field
        from extract_thinker import Extractor, DocumentLoaderPyPdf, Contract

        env_path = os.environ.get("ET_ENV_PATH", "")
        if env_path:
            load_dotenv(env_path)
        else:
            load_dotenv()

        class PaperContract(Contract):
            title: str = Field(..., description="Paper title")
            topics: list[str] = Field(..., description="3-8 topical keywords or phrases")
            github_urls: list[str] = Field(..., description="All GitHub repository URLs mentioned in the paper")
            introduction_writing: str = Field(
                ..., description="One paragraph: introduction with concrete writing guidance"
            )
            method_innovation_summary: str = Field(..., description="One paragraph: summarize method innovation")
            experiment_design_analysis: str = Field(..., description="One paragraph: experimental design and analysis")
            method_paragraph: str = Field(..., description="One paragraph: method description")
            figure_captions: list[str] = Field(..., description="All figure captions found in the paper")

        pdf_path = os.environ["ET_PDF_PATH"]
        out_path = os.environ["ET_OUT_PATH"]
        model = (
            os.environ.get("ET_MODEL")
            or os.environ.get("LITELLM_CHAT_MODEL")
            or os.environ.get("OPENAI_MODEL")
            or "gpt-4o-mini"
        )

        extractor = Extractor()
        extractor.load_document_loader(DocumentLoaderPyPdf())
        extractor.load_llm(model)

        result = extractor.extract(pdf_path, PaperContract)
        try:
            payload = result.model_dump()
        except AttributeError:
            payload = result.dict()

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=True, indent=2)
        """
    ).strip()

    try:
        subprocess.run(
            [str(python_bin), "-c", script],
            check=True,
            text=True,
            capture_output=True,
            env=env,
        )
        return "ok", out_path.as_posix()
    except subprocess.CalledProcessError as e:
        msg = (e.stderr or e.stdout or "").strip()
        if msg:
            msg = msg.splitlines()[-1]
        if msg and "No module named" in msg:
            m = re.search(r"No module named '([^']+)'", msg)
            mod = m.group(1) if m else ""
            if mod == "extract_thinker":
                hint = "install: pip install extract-thinker (or -e external/ExtractThinker; or pass --extractthinker-python)"
                return f"missing_dependency: {mod} ({hint})"[:200], ""
        return f"error: {msg[:200] if msg else 'extractthinker_failed'}", ""
    except Exception as e:
        return f"error: {e}", ""


def _paper_text_from_pdf(
    *,
    src: SourceInput,
    use_pdf: bool,
    timeout_ms: int,
    max_mb: int,
    max_chars: int,
    keep_pdf: bool,
    pdf_dir: Path | None,
) -> tuple[str, str, str, Path | None, bool]:
    pdf_url = _resolve_pdf_url(src) if use_pdf else ""
    if not pdf_url:
        return src.text, "", "no_pdf_url", None, False

    pdf_path: Path | None = None
    keep_path: Path | None = None
    delete_after = False
    try:
        if keep_pdf and pdf_dir:
            safe_id = str((src.extra or {}).get("arxiv_id") or "").strip()
            if not safe_id:
                safe_id = slugify(src.title or "arxiv", 32)
            keep_path = Path(pdf_dir) / f"{safe_id}.pdf"
            if keep_path.exists():
                pdf_path = keep_path
            else:
                pdf_path = _download_pdf_to_temp(
                    pdf_url, timeout_ms=timeout_ms, max_mb=max_mb, dest_path=keep_path
                )
        else:
            pdf_path = _download_pdf_to_temp(pdf_url, timeout_ms=timeout_ms, max_mb=max_mb)
            delete_after = True
        pdf_text = _extract_pdf_text(pdf_path, max_chars=max_chars)
        if not pdf_text.strip():
            return src.text, pdf_url, "empty", pdf_path, delete_after

        extra = src.extra if isinstance(src.extra, dict) else {}
        authors = extra.get("authors") if isinstance(extra.get("authors"), list) else []
        comment = str(extra.get("comment") or "").strip()
        abstract = _extract_abstract_from_src_text(src.text)
        header_lines: list[str] = []
        if str(src.title or "").strip():
            header_lines.append(f"TITLE: {src.title}")
        if authors:
            header_lines.append(f"AUTHORS: {', '.join([str(a) for a in authors if str(a).strip()])}")
        if abstract:
            header_lines.append(f"ABSTRACT: {abstract}")
        if comment:
            header_lines.append(f"COMMENT: {comment}")
        header = "\n".join([l for l in header_lines if l])
        full_text = f"{header}\n\n{pdf_text}" if header else pdf_text
        return full_text, pdf_url, "ok", pdf_path, delete_after
    except Exception as e:
        return src.text, pdf_url, f"error: {e}", pdf_path, delete_after


def _process_one_source(
    i: int,
    src: SourceInput,
    ctx: dict[str, Any],
) -> dict[str, Any]:
    run_dir = ctx["run_dir"]
    llm = ctx["llm"]
    ns = ctx["ns"]
    repo_root = ctx["repo_root"]
    use_pdf = ctx["use_pdf"]
    keep_pdf = ctx["keep_pdf"]
    pdf_dir = ctx["pdf_dir"]
    use_extractthinker = ctx["use_extractthinker"]
    extractthinker_dir = ctx["extractthinker_dir"]
    extractthinker_python = ctx["extractthinker_python"]
    extractthinker_model = ctx["extractthinker_model"]
    pdf_cache = ctx["pdf_cache"]
    extractthinker_cache = ctx["extractthinker_cache"]
    cache_lock = ctx.get("cache_lock")

    base_slug = f"arxiv-{slugify(src.extra.get('arxiv_id') or src.title, 24)}-{src.extra.get('skill_kind')}"
    if ns.dry_run:
        return {"source_url": src.url, "skill": None, "status": "dry-run"}

    summary_text = ""
    summary_status = "skipped"
    summary_path_rel = ""
    summary_chunks = 0
    paper_text = src.text
    pdf_url = ""
    pdf_text_status = "skipped"
    pdf_path_rel = ""
    pdf_path: Path | None = None
    delete_pdf_after = False
    extractthinker_status = "skipped"
    extractthinker_path_rel = ""

    if use_pdf:
        pdf_url = _resolve_pdf_url(src)
        if cache_lock:
            with cache_lock:
                cached = pdf_cache.get(pdf_url) if pdf_url else None
        else:
            cached = pdf_cache.get(pdf_url) if pdf_url else None
        if cached:
            paper_text = cached.get("paper_text", src.text)
            pdf_text_status = cached.get("pdf_text_status", "cached")
            pdf_path_rel = cached.get("pdf_path_rel", "")
        else:
            paper_text, pdf_url, pdf_text_status, pdf_path, delete_pdf_after = _paper_text_from_pdf(
                src=src,
                use_pdf=use_pdf,
                timeout_ms=int(ns.pdf_timeout_ms),
                max_mb=int(ns.pdf_max_mb),
                max_chars=int(ns.pdf_max_chars),
                keep_pdf=keep_pdf,
                pdf_dir=pdf_dir,
            )
            if pdf_url:
                if keep_pdf and pdf_dir:
                    safe_id = str((src.extra or {}).get("arxiv_id") or "").strip()
                    if not safe_id:
                        safe_id = slugify(src.title or "arxiv", 32)
                    keep_path = pdf_dir / f"{safe_id}.pdf"
                    if keep_path.exists():
                        try:
                            pdf_path_rel = keep_path.relative_to(run_dir).as_posix()
                        except Exception:
                            pdf_path_rel = keep_path.as_posix()
                if cache_lock:
                    with cache_lock:
                        pdf_cache[pdf_url] = {
                            "paper_text": paper_text,
                            "pdf_text_status": pdf_text_status,
                            "pdf_path_rel": pdf_path_rel,
                        }
                else:
                    pdf_cache[pdf_url] = {
                        "paper_text": paper_text,
                        "pdf_text_status": pdf_text_status,
                        "pdf_path_rel": pdf_path_rel,
                    }

    if ns.summarize_chunks:
        safe_id = str((src.extra or {}).get("arxiv_id") or "").strip() or slugify(src.title or "arxiv", 32)
        try:
            summary_text, summary_status, summary_path_rel, summary_chunks = _summarize_text_in_chunks(
                llm=llm,
                text=paper_text,
                title=src.title,
                source_url=src.url,
                language=str(src.extra.get("language") or "en"),
                chunk_chars=int(ns.summary_chunk_chars),
                max_chunks=int(ns.summary_max_chunks),
                timeout_ms=int(ns.summary_timeout_ms),
                run_dir=run_dir,
                summary_basename=safe_id,
            )
        except Exception as e:
            summary_status = f"error: {e}"

    if use_extractthinker:
        if not pdf_url:
            extractthinker_status = "no_pdf_url"
        else:
            if cache_lock:
                with cache_lock:
                    cached_et = extractthinker_cache.get(pdf_url)
            else:
                cached_et = extractthinker_cache.get(pdf_url)
            if cached_et:
                extractthinker_status = cached_et.get("status", "cached")
                extractthinker_path_rel = cached_et.get("path", "")
            else:
                safe_id = str((src.extra or {}).get("arxiv_id") or "").strip()
                if not safe_id:
                    safe_id = slugify(src.title or "arxiv", 32)
                out_path = (extractthinker_dir or run_dir) / f"{safe_id}.extractthinker.json"
                if pdf_path and pdf_path.exists():
                    status, out_path_str = _run_extractthinker(
                        repo_root=repo_root,
                        pdf_path=pdf_path,
                        out_path=out_path,
                        model=extractthinker_model,
                        python_bin=extractthinker_python,
                        env_path=repo_root / ".env",
                    )
                    extractthinker_status = status
                    if out_path_str:
                        try:
                            extractthinker_path_rel = Path(out_path_str).relative_to(run_dir).as_posix()
                        except Exception:
                            extractthinker_path_rel = out_path_str
                else:
                    extractthinker_status = "missing_pdf"
                if cache_lock:
                    with cache_lock:
                        extractthinker_cache[pdf_url] = {
                            "status": extractthinker_status,
                            "path": extractthinker_path_rel,
                        }
                else:
                    extractthinker_cache[pdf_url] = {
                        "status": extractthinker_status,
                        "path": extractthinker_path_rel,
                    }

    artifact = write_source_artifact(
        run_dir=run_dir,
        source_type="arxiv",
        url=src.url,
        title=src.title,
        raw_text=paper_text,
        extracted_text=paper_text,
        license_spdx="",
        license_risk="unknown",
        extra={
            "arxiv_id": src.extra.get("arxiv_id"),
            "pdf_url": pdf_url,
            "pdf_text_status": pdf_text_status,
            "pdf_path": pdf_path_rel,
            "extractthinker_status": extractthinker_status,
            "extractthinker_path": extractthinker_path_rel,
            "summary_status": summary_status,
            "summary_path": summary_path_rel,
            "summary_chunks": summary_chunks,
            "summary_chunk_chars": int(ns.summary_chunk_chars),
            "skill_kind": src.extra.get("skill_kind"),
            "language": src.extra.get("language"),
            "tags": src.extra.get("tags") if isinstance(src.extra.get("tags"), list) else [],
        },
    )
    text_path_rel = ""
    if str(paper_text or "").strip():
        txt_path = run_dir / "sources" / f"{artifact.source_id}.txt"
        write_text_atomic(txt_path, paper_text)
        try:
            text_path_rel = txt_path.relative_to(run_dir).as_posix()
        except Exception:
            text_path_rel = txt_path.as_posix()

    linked_repos: list[dict[str, str]] = []
    source_refs = [
        {"source_id": artifact.source_id, "source_url": artifact.url, "source_type": "arxiv"},
    ]
    repo_urls = link_github_repos_from_paper_entry(
        {
            "title": src.title,
            "summary": _extract_abstract_from_src_text(src.text),
            "comment": src.extra.get("comment") if isinstance(src.extra, dict) else "",
            "full_text": paper_text,
        }
    )
    extra_text = ""
    for rurl in repo_urls[:3]:
        try:
            full_name = parse_github_full_name_from_url(rurl)
            readme_text = github_fetch_readme_excerpt_raw(full_name=full_name, default_branch="main")
        except Exception:
            readme_text = ""
        linked_repos.append({"url": rurl, "readme_excerpt": readme_text})
        if readme_text:
            extra_text += f"\n\n[GitHub Repo] {rurl}\n{readme_text[:1500]}"
        try:
            repo_artifact = write_source_artifact(
                run_dir=run_dir,
                source_type="github",
                url=rurl,
                title="",
                raw_text=readme_text,
                extracted_text=readme_text,
                license_spdx="",
                license_risk="unknown",
                extra={"source_url_raw": rurl},
            )
            repo_ref = {"source_id": repo_artifact.source_id, "source_url": repo_artifact.url, "source_type": "github"}
            source_refs.append(repo_ref)
            if ns.with_repo_index and full_name:
                from ..scripts.repo_index import cli_repo_index as repo_index_main

                snapshot_dir = run_dir / "repo-index" / repo_artifact.source_id
                ensure_dir(snapshot_dir)
                repo_index_main(
                    [
                        "--out-dir",
                        snapshot_dir.as_posix(),
                        "--repo",
                        full_name,
                        "--max-files",
                        str(ns.repo_index_max_files),
                    ]
                )
                sym_excerpt = _load_symbol_index_excerpt(snapshot_dir, max_lines=120)
                if sym_excerpt:
                    extra_text += f"\n\n[Repo Index Symbols]\n{sym_excerpt[:4000]}"
        except Exception:
            continue

    base_text = summary_text.strip() if summary_text.strip() else artifact.extracted_text
    enriched_text = f"{base_text}{extra_text}" if extra_text else base_text

    try:
        gate = run_skill_gate(
            run_dir=run_dir,
            domain=ns.profile,
            method="arxiv",
            source_id=artifact.source_id,
            source_url=artifact.url,
            source_title=artifact.title,
            extracted_text=enriched_text,
            llm=llm,
        )
        if not bool(gate.get("allow_generate")):
            result = {
                "source_url": src.url,
                "skill": None,
                "status": f"skipped: gate({gate.get('verdict')})",
                "linked_repo_urls": repo_urls,
                "pdf_url": pdf_url,
                "pdf_text_status": pdf_text_status,
                "pdf_path": pdf_path_rel,
                "text_path": text_path_rel,
                "extractthinker_status": extractthinker_status,
                "extractthinker_path": extractthinker_path_rel,
            }
        else:
            out_skill = generate_one_skill(
                run_dir=run_dir,
                domain=ns.profile,
                method="arxiv",
                seq=i,
                base_slug=base_slug,
                source=SourceInput(
                    source_type="arxiv",
                    url=artifact.url,
                    title=artifact.title,
                    text=enriched_text,
                    fetched_at=artifact.fetched_at,
                    extra={
                        "source_artifact_id": artifact.source_id,
                        "skill_kind": src.extra.get("skill_kind"),
                        "language": src.extra.get("language"),
                        "license_spdx": artifact.license_spdx,
                        "license_risk": artifact.license_risk,
                        "linked_repos": linked_repos,
                        "source_refs": source_refs,
                        "tags": src.extra.get("tags") if isinstance(src.extra.get("tags"), list) else [],
                    },
                ),
                llm=llm,
            )
            result = {
                "source_url": src.url,
                "skill": out_skill,
                "status": "ok",
                "linked_repo_urls": repo_urls,
                "pdf_url": pdf_url,
                "pdf_text_status": pdf_text_status,
                "pdf_path": pdf_path_rel,
                "text_path": text_path_rel,
                "extractthinker_status": extractthinker_status,
                "extractthinker_path": extractthinker_path_rel,
            }
    except Exception as e:
        result = {
            "source_url": src.url,
            "skill": None,
            "status": f"error: {e}",
            "linked_repo_urls": repo_urls,
            "pdf_url": pdf_url,
            "pdf_text_status": pdf_text_status,
            "pdf_path": pdf_path_rel,
            "text_path": text_path_rel,
            "extractthinker_status": extractthinker_status,
            "extractthinker_path": extractthinker_path_rel,
        }
    finally:
        if delete_pdf_after and pdf_path and pdf_path.exists():
            try:
                pdf_path.unlink()
            except Exception:
                pass
    return result


def cli_arxiv_pipeline(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills-rai arxiv-pipeline")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--max-results", type=int, default=3)
    parser.add_argument("--profile", default="research")
    parser.add_argument("--provider", default=None, help="LLM provider override")
    parser.add_argument("--dry-run", action="store_true", help="Only discover and write manifest, no LLM generation")
    parser.add_argument("--offline", action="store_true", help="Do not call arXiv; emit placeholder sources")
    parser.add_argument("--with-repo-index", action="store_true", help="Index linked GitHub repos for richer evidence (requires network)")
    parser.add_argument("--repo-index-max-files", type=int, default=400)
    parser.add_argument("--no-pdf", action="store_true", help="Skip downloading and extracting PDF text")
    parser.add_argument("--pdf-timeout-ms", type=int, default=45_000)
    parser.add_argument("--pdf-max-mb", type=int, default=40)
    parser.add_argument("--pdf-max-chars", type=int, default=200_000)
    parser.add_argument("--keep-pdf", action="store_true", help="Keep downloaded PDFs under captures/<run-id>/pdf/")
    parser.add_argument(
        "--extractthinker",
        action="store_true",
        help="Run ExtractThinker on each PDF to extract structured JSON",
    )
    parser.add_argument(
        "--extractthinker-python",
        default=None,
        help="Python executable used to run ExtractThinker (default: current interpreter)",
    )
    parser.add_argument(
        "--extractthinker-model",
        default=None,
        help="Override LLM model for ExtractThinker",
    )
    parser.add_argument("--max-new", type=int, default=0, help="Limit to N new papers (after de-dup)")
    parser.add_argument("--seen-db", default=None, help="SQLite DB path to avoid re-processing the same arXiv paper")
    parser.add_argument(
        "--summarize-chunks",
        action="store_true",
        help="Split long paper text into chunks, summarize each chunk, then concatenate summaries for LLM generation.",
    )
    parser.add_argument("--summary-chunk-chars", type=int, default=4000)
    parser.add_argument("--summary-max-chunks", type=int, default=12)
    parser.add_argument("--summary-timeout-ms", type=int, default=300_000)
    parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="Process N papers in parallel per worker (default 8; env LANGSKILLS_ARXIV_CONCURRENCY)",
    )
    ns = parser.parse_args(argv)
    if ns.concurrency is None:
        try:
            ns.concurrency = max(1, int(os.environ.get("LANGSKILLS_ARXIV_CONCURRENCY", "8")))
        except (TypeError, ValueError):
            ns.concurrency = 8
    ns.concurrency = max(1, min(ns.concurrency, 128))

    repo_root = Path(__file__).resolve().parents[2]
    load_dotenv(repo_root)

    topic = ns.topic.strip()
    run_dir = make_run_dir(repo_root, topic)
    ensure_dir(run_dir)

    offline = ns.offline or (str(os.environ.get("LANGSKILLS_OFFLINE") or "").strip() == "1")
    if offline:
        raise RuntimeError("Offline mode is disabled; remove LANGSKILLS_OFFLINE or --offline.")
    use_pdf = not bool(ns.no_pdf)
    keep_pdf = bool(ns.keep_pdf)
    pdf_dir = run_dir / "pdf" if keep_pdf else None
    use_extractthinker = bool(ns.extractthinker)
    extractthinker_dir = run_dir / "extractthinker" if use_extractthinker else None
    if extractthinker_dir:
        ensure_dir(extractthinker_dir)
    extractthinker_python = (
        _resolve_extractthinker_python(repo_root, ns.extractthinker_python) if use_extractthinker else None
    )
    extractthinker_model = str(ns.extractthinker_model or "").strip() or None
    sources = discover_arxiv_sources(topic, max_results=ns.max_results)

    seen_keys: list[str] = []
    conn: sqlite3.Connection | None = None
    seen_db_path = str(ns.seen_db or "").strip()
    max_new = int(ns.max_new or 0)
    if seen_db_path:
        conn = _open_seen_db(Path(seen_db_path))
        sources, seen_keys = _filter_seen_sources(
            conn=conn,
            sources=sources,
            topic=topic,
            max_new=max_new or None,
            run_id=run_dir.name,
        )
    elif max_new > 0:
        groups: list[tuple[str, list[SourceInput]]] = []
        idx: dict[str, int] = {}
        for src in sources:
            key = _seen_key_for_source(src)
            if key not in idx:
                idx[key] = len(groups)
                groups.append((key, []))
            groups[idx[key]][1].append(src)
        groups = groups[:max_new]
        sources = [s for _, group in groups for s in group]

    _write_manifest(run_dir, topic, sources)

    if ns.dry_run:
        print(f"Dry-run only. Manifest written to {run_dir}/manifest.json sources={len(sources)}")
        if conn is not None:
            _mark_seen_done(conn, seen_keys, run_dir.name)
            conn.close()
        return 0
    if not sources:
        print(f"No new sources. Manifest written to {run_dir}/manifest.json sources=0")
        if conn is not None:
            _mark_seen_done(conn, seen_keys, run_dir.name)
            conn.close()
        return 0

    llm = create_llm_from_env(provider_override=ns.provider)

    start_time = time.monotonic()
    print(
        f"PROGRESS: source_i=0 total_sources={len(sources)} skills_ok=0 skills_fail=0 elapsed_s=0",
        flush=True,
    )
    print(f"ARXIV_CONCURRENCY={ns.concurrency}", flush=True)
    pdf_cache: dict[str, dict[str, str]] = {}
    extractthinker_cache: dict[str, dict[str, str]] = {}
    results: list[dict[str, Any]] = []

    ctx: dict[str, Any] = {
        "run_dir": run_dir,
        "llm": llm,
        "ns": ns,
        "repo_root": repo_root,
        "use_pdf": use_pdf,
        "keep_pdf": keep_pdf,
        "pdf_dir": pdf_dir,
        "use_extractthinker": use_extractthinker,
        "extractthinker_dir": extractthinker_dir,
        "extractthinker_python": extractthinker_python,
        "extractthinker_model": extractthinker_model,
        "pdf_cache": pdf_cache,
        "extractthinker_cache": extractthinker_cache,
    }

    if ns.concurrency <= 1:
        for i, src in enumerate(sources, start=1):
            res = _process_one_source(i, src, ctx)
            results.append(res)
            n_ok = sum(1 for r in results if r.get("skill") is not None)
            n_fail = len(results) - n_ok
            elapsed_s = int(time.monotonic() - start_time)
            print(
                f"PROGRESS: source_i={i} total_sources={len(sources)} skills_ok={n_ok} skills_fail={n_fail} elapsed_s={elapsed_s}",
                flush=True,
            )
    else:
        cache_lock = threading.Lock()
        ctx["cache_lock"] = cache_lock
        results = [None] * len(sources)  # type: ignore[list-item]
        with ThreadPoolExecutor(max_workers=ns.concurrency) as executor:
            futures = {executor.submit(_process_one_source, i, src, ctx): i for i, src in enumerate(sources, start=1)}
            for future in as_completed(futures):
                i = futures[future]
                try:
                    res = future.result()
                    results[i - 1] = res
                except Exception as e:
                    results[i - 1] = {
                        "source_url": sources[i - 1].url,
                        "skill": None,
                        "status": f"error: {e}",
                        "linked_repo_urls": [],
                        "pdf_url": "",
                        "pdf_text_status": "",
                        "pdf_path": "",
                        "text_path": "",
                        "extractthinker_status": "",
                        "extractthinker_path": "",
                    }
                n_ok = sum(1 for r in results if r is not None and r.get("skill") is not None)
                n_fail = sum(1 for r in results if r is not None) - n_ok
                elapsed_s = int(time.monotonic() - start_time)
                print(
                    f"PROGRESS: source_i={i} total_sources={len(sources)} skills_ok={n_ok} skills_fail={n_fail} elapsed_s={elapsed_s}",
                    flush=True,
                )
        results = [r for r in results if r is not None]

    write_json_atomic(run_dir / "arxiv_results.json", {"results": results, "created_at": utc_now_iso_z()})
    if conn is not None:
        _mark_seen_done(conn, seen_keys, run_dir.name)
        conn.close()

    if validate_skills is not None:
        errors, warnings = validate_skills(repo_root=repo_root, root=run_dir / "skills", strict=True, check_package=True)
        for w in warnings:
            print(f"WARN: {w}")
        for e in errors:
            print(f"FAIL: {e}")
    else:
        errors, warnings = [], []
        print("SKIP: validate_skills module not available; skipping validation.")
    print(f"Run dir: {run_dir.as_posix()} total_sources={len(sources)} errors={len(errors)} warnings={len(warnings)}")
    return 1 if errors else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_arxiv_pipeline())
def _load_symbol_index_excerpt(snapshot_dir: Path, max_lines: int = 80) -> str:
    """
    Load a short excerpt from repo-index symbol_index.jsonl for LLM context.
    """
    path = snapshot_dir / "symbol_index.jsonl"
    if not path.exists():
        return ""
    out: list[str] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                out.append(line.strip())
    except Exception:
        return ""
    return "\n".join(out)
