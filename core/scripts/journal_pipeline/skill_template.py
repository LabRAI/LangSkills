
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from core.utils.hashing import slugify
from core.utils.time import utc_now_iso_z
from core.utils.yaml_simple import write_metadata_yaml_text
from core.utils.fs import ensure_dir, write_text_atomic


@dataclass(frozen=True)
class JournalSkillOutput:
    skill_id: str
    skill_dir: str
    domain: str
    topic: str
    slug: str
    rel_dir: str
    title: str
    source_url: str
    doi: str
    generated_at: str


@dataclass(frozen=True)
class _SkillId:
    id: str
    topic: str
    slug: str


def _make_skill_id(*, domain, method, seq, base_slug):
    method = method or ""
    topic = str(method or "").strip()
    seq_part = str(int(seq)).rjust(4, "0")
    slug_part = slugify(base_slug, 40)
    slug = f"""{topic[:1] or 'x'}-{seq_part}-{slug_part}"""
    skill_id = f"""{domain}/{topic}/{slug}"""
    return _SkillId(id=skill_id, topic=topic, slug=slug)


def _paper_title_fallback(paper_title=None, doi=None):
    paper_title = paper_title or ""
    t = str(paper_title or "").strip()
    if t:
        return t
    doi = doi or ""
    d = str(doi or "").strip()
    if d:
        return f"""Paper {d}"""


def build_journal_skill_markdown(*, title, source_url, run_id, source_artifact_id, doi, journal, journal_family, pub_date):
    title = title or ""
    paper_title = str(title or "").strip()
    doi = doi or ""
    doi_s = str(doi or "").strip()
    journal = journal or ""
    journal_s = str(journal or "").strip()
    journal_family = journal_family or ""
    family_s = str(journal_family or "").strip()
    pub_date = pub_date or ""
    pub_s = str(pub_date or "").strip()
    lines = []
    lines.append(f"""# Extract figures and open data links from: {paper_title}""")
    lines.append("")
    lines.append("## Background")
    if doi_s:
        lines.append(f"""- DOI: `{doi_s}`""")
    if journal_s:
        lines.append(f"""- Journal: `{journal_s}`""")
    if family_s:
        lines.append(f"""- Family: `{family_s}`""")
    if pub_s:
        lines.append(f"""- Published: `{pub_s}`""")
    lines.append("")
    lines.append("## Use Cases")
    lines.append("- Build a dataset of paper figures + captions for downstream analysis.")
    lines.append("- Collect open data links (GEO/Zenodo/GitHub/Dryad/etc.) referenced by the paper.")
    lines.append("")
    lines.append("## Inputs")
    lines.append(f"""- Capture artifact (run): `captures/{run_id}/sources/{source_artifact_id}.json`""")
    lines.append("- Published artifact (library): `skills/by-skill/<skill_id>/source.json` (run from that directory).")
    lines.append("- Optional env vars: `RUN_DIR`, `OUT_DIR`, `DATA_JSON`, `REPORT_JSON`, `DOWNLOAD_FIGURES=0`.")
    lines.append("")
    lines.append("## Outputs")
    lines.append("- `figures/` directory populated with downloaded images (best-effort; failures are reported).")
    lines.append("- `data_links.json`: detected open data links (may be empty).")
    lines.append("- `download_report.json`: download summary + failures list.")
    lines.append("")
    lines.append("## Steps")
    lines.append("1. Pick an artifact source (published skill dir `source.json`, or a capture run dir).")
    lines.append("2. Inspect the counts of extracted figures and data links.")
    lines.append("3. Export `data_links.json` from the artifact (even if empty).")
    lines.append("4. Download figure images (best-effort, with retries).")
    lines.append("5. Review `download_report.json` for failures.")
    lines.append("")
    lines.append("```bash")
    lines.append("set -euo pipefail")
    lines.append("")
    lines.append("# If running from a published skill directory, `source.json` exists in the current folder.")
    lines.append('SKILL_DIR="${SKILL_DIR:-$(pwd)}"')
    lines.append('ARTIFACT=""')
    lines.append('BASE_OUT=""')
    lines.append("")
    lines.append('if [ -f "$SKILL_DIR/source.json" ]; then')
    lines.append('  ARTIFACT="$SKILL_DIR/source.json"')
    lines.append('  BASE_OUT="$SKILL_DIR/exports"')
    lines.append("else")
    lines.append(f"""  RUN_DIR="${{RUN_DIR:-var/captures/{run_id}}}" """.rstrip())
    lines.append(f"""  ARTIFACT="$RUN_DIR/sources/{source_artifact_id}.json" """.rstrip())
    lines.append('  BASE_OUT="$RUN_DIR/exports"')
    lines.append("fi")
    lines.append("")
    lines.append('OUT_DIR="${OUT_DIR:-$BASE_OUT/figures}"')
    lines.append('DATA_JSON="${DATA_JSON:-$BASE_OUT/data_links.json}"')
    lines.append('REPORT_JSON="${REPORT_JSON:-$BASE_OUT/download_report.json}"')
    lines.append('DOWNLOAD_FIGURES="${DOWNLOAD_FIGURES:-1}"')
    lines.append("export ARTIFACT OUT_DIR DATA_JSON REPORT_JSON DOWNLOAD_FIGURES")
    lines.append("")
    lines.append("python3 - <<'PY'")
    lines.append("import json")
    lines.append("import mimetypes")
    lines.append("import os")
    lines.append("import pathlib")
    lines.append("import re")
    lines.append("import time")
    lines.append("import urllib.parse")
    lines.append("import urllib.request")
    lines.append("")
    lines.append("artifact_path = pathlib.Path(os.environ['ARTIFACT']).resolve()")
    lines.append("out_dir = pathlib.Path(os.environ['OUT_DIR']).resolve()")
    lines.append("data_json = pathlib.Path(os.environ['DATA_JSON']).resolve()")
    lines.append("report_json = pathlib.Path(os.environ['REPORT_JSON']).resolve()")
    lines.append("download_figures = str(os.environ.get('DOWNLOAD_FIGURES') or '1').strip() != '0'")
    lines.append("")
    lines.append("if not artifact_path.exists():")
    lines.append("    raise SystemExit(f'missing artifact: {artifact_path}')")
    lines.append("out_dir.mkdir(parents=True, exist_ok=True)")
    lines.append("data_json.parent.mkdir(parents=True, exist_ok=True)")
    lines.append("report_json.parent.mkdir(parents=True, exist_ok=True)")
    lines.append("")
    lines.append("obj = json.loads(artifact_path.read_text(encoding='utf-8'))")
    lines.append("extra = obj.get('extra') or {}")
    lines.append("figs = extra.get('figures') or []")
    lines.append("data = extra.get('data_sources') or []")
    lines.append("print(f'figures={len(figs)} data_sources={len(data)}')")
    lines.append("")
    lines.append("data_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')")
    lines.append("")
    lines.append("def _safe_name(s: str) -> str:")
    lines.append("    s = str(s or '').strip() or 'fig'")
    lines.append("    s = re.sub(r'[^A-Za-z0-9_.-]+', '_', s)")
    lines.append("    return s[:80] if len(s) > 80 else s")
    lines.append("")
    lines.append("def _guess_ext(url: str, content_type: str) -> str:")
    lines.append("    ctype = str(content_type or '').split(';', 1)[0].strip().lower()")
    lines.append("    ext = mimetypes.guess_extension(ctype) if ctype else None")
    lines.append("    if not ext:")
    lines.append("        try:")
    lines.append("            path = urllib.parse.urlparse(url).path")
    lines.append("            ext = pathlib.Path(path).suffix")
    lines.append("        except Exception:")
    lines.append("            ext = ''")
    lines.append("    ext = str(ext or '').strip()")
    lines.append("    if not ext or len(ext) > 6:")
    lines.append("        return '.bin'")
    lines.append("    return ext")
    lines.append("")
    lines.append("headers = {")
    lines.append("    'User-Agent': 'langskills-journal-skill/1.0 (+https://example.invalid)',")
    lines.append("    'Accept': 'image/*,*/*;q=0.8',")
    lines.append("}")
    lines.append("")
    lines.append("# Download figure images (best-effort, with retries).")
    lines.append("downloaded = 0")
    lines.append("attempted = 0")
    lines.append("failures = []")
    lines.append("if download_figures:")
    lines.append("    for fig in figs:")
    lines.append("        url = str((fig or {}).get('full_size_url') or '').strip()")
    lines.append("        if not url:")
    lines.append("            continue")
    lines.append("        attempted += 1")
    lines.append("        fid = _safe_name(str((fig or {}).get('figure_id') or 'fig'))")
    lines.append("        last_err = ''")
    lines.append("        for attempt in range(3):")
    lines.append("            try:")
    lines.append("                req = urllib.request.Request(url, headers=headers)")
    lines.append("                with urllib.request.urlopen(req, timeout=30) as resp:")
    lines.append("                    blob = resp.read()")
    lines.append("                    ext = _guess_ext(url, resp.headers.get('Content-Type', ''))")
    lines.append("                dest = out_dir / f\"{fid}{ext}\"")
    lines.append("                dest.write_bytes(blob)")
    lines.append("                downloaded += 1")
    lines.append("                last_err = ''")
    lines.append("                break")
    lines.append("            except Exception as e:")
    lines.append("                last_err = f\"{type(e).__name__}: {e}\"")
    lines.append("                time.sleep(0.6 * (attempt + 1))")
    lines.append("        if last_err:")
    lines.append("            failures.append({'figure_id': fid, 'url': url, 'error': last_err})")
    lines.append("")
    lines.append("report = {")
    lines.append("    'artifact': str(artifact_path),")
    lines.append("    'figures': int(len(figs)),")
    lines.append("    'data_sources': int(len(data)),")
    lines.append("    'attempted': int(attempted),")
    lines.append("    'downloaded': int(downloaded),")
    lines.append("    'failed': int(len(failures)),")
    lines.append("    'failures': failures,")
    lines.append("}")
    lines.append("report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')")
    lines.append("print(f'downloaded={downloaded}/{attempted} wrote={data_json} report={report_json}')")
    lines.append("PY")
    lines.append("```")
    lines.append("")
    lines.append("## Verification")
    lines.append("```bash")
    lines.append("set -euo pipefail")
    lines.append(': "${ARTIFACT:=source.json}"')
    lines.append(': "${REPORT_JSON:=}"')
    lines.append("export ARTIFACT REPORT_JSON")
    lines.append("python3 - <<'PY'")
    lines.append("import json")
    lines.append("import os")
    lines.append("from pathlib import Path")
    lines.append("")
    lines.append("artifact = Path(os.environ.get('ARTIFACT') or 'source.json')")
    lines.append("obj = json.loads(artifact.read_text(encoding='utf-8'))")
    lines.append("extra = obj.get('extra') or {}")
    lines.append("figs = extra.get('figures') or []")
    lines.append("data = extra.get('data_sources') or []")
    lines.append("assert isinstance(figs, list) and isinstance(data, list)")
    lines.append("report_path = Path(os.environ.get('REPORT_JSON') or '')")
    lines.append("if report_path.is_file():")
    lines.append("    rep = json.loads(report_path.read_text(encoding='utf-8'))")
    lines.append("    assert int(rep.get('attempted') or 0) == int(rep.get('downloaded') or 0) + int(rep.get('failed') or 0)")
    lines.append("print('OK', 'figures', len(figs), 'data_sources', len(data), 'report', report_path.as_posix() if report_path.is_file() else '-')")
    lines.append("PY")
    lines.append("```")
    lines.append("")
    lines.append("## Safety")
    lines.append("- Downloading many large images can consume bandwidth and disk space.")
    lines.append("- Treat all downloaded files as untrusted input; avoid auto-opening them.")
    lines.append("")
    lines.append("## Evidence")
    lines.append(f"""- run_id: {run_id}""")
    lines.append(f"""- source_artifact: captures/{run_id}/sources/{source_artifact_id}.json""")
    lines.append("")
    lines.append("## Sources")
    if source_url:
        lines.append(f"""- {source_url}""")
    return "\n".join(lines).rstrip() + "\n"


def write_journal_skill(*, run_dir, domain, seq, base_slug, paper_title, source_url, source_fetched_at, source_artifact_id, doi, journal, journal_family, pub_date, skill_kind, license_spdx, license_risk, language):
    domain = domain or ""
    base_slug = base_slug or ""
    domain = str(domain or "").strip()
    sid = _make_skill_id(domain=domain, method="journal", seq=int(seq), base_slug=slugify(paper_title, 40))
    skill_dir = (Path(run_dir) / "skills" / domain / sid.topic / sid.slug).resolve()
    ensure_dir(skill_dir)
    title = _paper_title_fallback(paper_title, doi)
    source_url = source_url or ""
    source_artifact_id = source_artifact_id or ""
    skill_md = build_journal_skill_markdown(title=title, source_url=str(source_url or "").strip(), run_id=str(Path(run_dir).name), source_artifact_id=str(source_artifact_id or "").strip(), doi=doi, journal=journal, journal_family=journal_family, pub_date=pub_date)
    generated_at = utc_now_iso_z()
    meta: dict[str, Any] = {
        "id": sid.id,
        "title": title or sid.id,
        "domain": domain,
        "topic": sid.topic,
        "slug": sid.slug,
        "source_type": "journal",
        "source_url": str(source_url or "").strip(),
        "source_fetched_at": str(source_fetched_at or "").strip(),
        "generated_at": generated_at,
        "source_artifact_id": str(source_artifact_id or "").strip(),
        "doi": str(doi or "").strip(),
        "journal": str(journal or "").strip(),
        "journal_family": str(journal_family or "").strip(),
        "pub_date": str(pub_date or "").strip(),
        "skill_kind": str(skill_kind or "journal_figure_data_mining").strip(),
        "license_spdx": str(license_spdx or "").strip(),
        "license_risk": str(license_risk or "unknown").strip(),
        "language": str(language or "en").strip(),
    }
    write_text_atomic(skill_dir / "skill.md", skill_md)
    write_text_atomic(skill_dir / "metadata.yaml", write_metadata_yaml_text(meta))
    return JournalSkillOutput(
        skill_id=sid.id,
        skill_dir=str(skill_dir),
        domain=domain,
        topic=sid.topic,
        slug=sid.slug,
        rel_dir=skill_dir.relative_to(Path(run_dir).resolve()).as_posix(),
        title=title or sid.id,
        source_url=str(source_url or "").strip(),
        doi=str(doi or "").strip(),
        generated_at=generated_at,
    )
