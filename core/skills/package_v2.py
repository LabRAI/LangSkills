from __future__ import annotations

import datetime as _dt
import re
import time
from dataclasses import dataclass
from pathlib import Path

from ..llm.types import LlmClient
from ..utils.fs import ensure_dir, read_text, write_text_atomic
from ..utils.fs import find_nearest_sources_dir
from ..utils.time import iso_date_part, utc_now_iso_z
from ..utils.yaml_simple import parse_metadata_yaml_text, write_metadata_yaml_text
from .coerce import coerce_markdown
from .prompts import make_skill_package_v2_prompt


def sanitize_raw_urls(md: str, *, allow_urls: list[str]) -> str:
    s = str(md or "")
    allow = {str(u or "").strip() for u in (allow_urls or []) if str(u or "").strip()}

    def repl(m: re.Match[str]) -> str:
        url = m.group(0)
        return url if url in allow else "<URL>"

    return re.sub(r"https?://\S+", repl, s)


def strip_url_placeholders(md: str) -> str:
    lines = str(md or "").replace("\r\n", "\n").split("\n")
    out = [line for line in lines if "<URL>" not in str(line or "")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).rstrip()


def remove_placeholder_todo_code_blocks(md: str) -> str:
    s = str(md or "")
    s = re.sub(r"```[a-zA-Z0-9_-]*\n#\s*TODO:\s*add a runnable example[\s\S]*?\n```", "", s)
    # Also drop standalone TODO lines (common placeholder output).
    lines = s.replace("\r\n", "\n").split("\n")
    lines = [line for line in lines if not re.search(r"\bTODO\b", line, flags=re.IGNORECASE)]
    s = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", s).rstrip()


def normalize_sources_md(*, sources_md: str, source_url: str, source_fetched_at: str, package_generated_at: str) -> str:
    allow_url = str(source_url or "").strip()
    access_iso = str(source_fetched_at or package_generated_at or "").strip()

    s = str(sources_md or "")
    s = remove_placeholder_todo_code_blocks(s)
    s = strip_url_placeholders(s)
    s = s.strip()

    if access_iso:
        if re.search(r"Accessed at[:：]", s, flags=re.IGNORECASE):
            s = re.sub(r"Accessed at[:：][^\n]*", f"Accessed at: {access_iso}", s, flags=re.IGNORECASE)
        else:
            s = f"{s}\n\nAccessed at: {access_iso}".strip()

    if allow_url and allow_url not in s:
        s = f"{s}\n\n- {allow_url}".strip()

    return s.rstrip() + "\n"


def normalize_changelog_md(*, changelog_md: str, package_generated_at: str) -> str:
    date = iso_date_part(package_generated_at) or iso_date_part(utc_now_iso_z())
    s = str(changelog_md or "").replace("\r\n", "\n").strip()
    s = remove_placeholder_todo_code_blocks(s)
    s = strip_url_placeholders(s)

    if not s:
        return f"# Changelog\n\n- **{date}**: initial package generation.\n"

    if re.search(r"\*\*20\d{2}-\d{2}-\d{2}\*\*", s):
        s = re.sub(r"\*\*20\d{2}-\d{2}-\d{2}\*\*", f"**{date}**", s)
        return s.rstrip() + "\n"

    if re.search(r"\b20\d{2}-\d{2}-\d{2}\b", s):
        s = re.sub(r"\b20\d{2}-\d{2}-\d{2}\b", date, s)
        return s.rstrip() + "\n"

    if re.search(r"^#+\s+", s, flags=re.MULTILINE):
        return f"{s.rstrip()}\n\n- **{date}**: initial package generation.\n"

    return f"# Changelog\n\n- **{date}**: initial package generation.\n\n{s.rstrip()}\n"


def replace_concrete_dates_with_placeholder(md: str) -> str:
    s = str(md or "")
    return re.sub(r"([\"'])20\d{2}-\d{2}-\d{2}([\"'])", r"\1YYYY-MM-DD\2", s)


def ensure_at_least_one_code_block_any(md: str) -> str:
    s = str(md or "")
    code_blocks = len(re.findall(r"```", s)) / 2
    if code_blocks >= 1:
        return s

    inline: list[str] = []
    for m in re.finditer(r"`([^`\n]{2,160})`", s):
        t = str(m.group(1) or "").strip()
        if not t:
            continue
        if not re.match(r"^[a-zA-Z_]", t):
            continue
        if not re.search(r"[a-zA-Z]", t):
            continue
        if len(t) < 4:
            continue
        if re.match(r"^https?://", t, flags=re.IGNORECASE):
            continue
        inline.append(t)
        if len(inline) >= 8:
            break

    picked = list(dict.fromkeys(inline))[:5]
    block = "\n".join(
        [
            "```bash",
            "# Auto-generated runnable snippet (model missed fenced code blocks)",
            *(picked if picked else ['echo "OK"']),
            "```",
        ]
    )
    return f"{s.strip()}\n\n{block}\n"


@dataclass(frozen=True)
class PackageV2:
    library_md: str
    reference: dict[str, str]


def build_skill_package_v2_with_llm(
    *,
    llm: LlmClient,
    domain: str,
    method: str,
    skill_id: str,
    title: str,
    source_url: str,
    source_fetched_at: str,
    package_generated_at: str,
    license_spdx: str,
    license_risk: str,
    skill_md: str,
    source_excerpt: str,
    max_attempts: int = 3,
) -> PackageV2:
    messages = make_skill_package_v2_prompt(
        domain=domain,
        method=method,
        skill_id=skill_id,
        title=title,
        source_url=source_url,
        source_fetched_at=source_fetched_at,
        package_generated_at=package_generated_at,
        license_spdx=license_spdx,
        license_risk=license_risk,
        skill_md=skill_md,
        source_excerpt=source_excerpt,
    )

    out: dict | None = None
    last_err: Exception | None = None
    for attempt in range(0, max(1, int(max_attempts or 1))):
        try:
            out = llm.chat_json(messages=messages, temperature=0.2 if attempt == 0 else 0.0, timeout_ms=300_000)
            last_err = None
            break
        except Exception as e:
            last_err = e
            time.sleep(0.6 * (attempt + 1))

    if not isinstance(out, dict):
        raise RuntimeError("Failed to generate package v2") from last_err

    library_md_raw = coerce_markdown(out.get("library_md"))
    ref = out.get("reference") if isinstance(out.get("reference"), dict) else {}
    ref_sources_raw = coerce_markdown(ref.get("sources_md"))
    ref_trouble_raw = coerce_markdown(ref.get("troubleshooting_md"))
    ref_edge_raw = coerce_markdown(ref.get("edge_cases_md"))
    ref_examples_raw = coerce_markdown(ref.get("examples_md"))
    ref_changelog_raw = coerce_markdown(ref.get("changelog_md"))

    allow = [str(source_url or "").strip()] if str(source_url or "").strip() else []

    # library.md must not contain raw URLs.
    library_md = sanitize_raw_urls(library_md_raw, allow_urls=[])
    library_md = ensure_at_least_one_code_block_any(library_md)
    library_md = strip_url_placeholders(library_md).rstrip() + "\n"

    sources_md0 = sanitize_raw_urls(ref_sources_raw, allow_urls=allow)
    sources_md = normalize_sources_md(
        sources_md=sources_md0,
        source_url=allow[0] if allow else "",
        source_fetched_at=str(source_fetched_at or "").strip(),
        package_generated_at=str(package_generated_at or "").strip(),
    )

    troubleshooting_md = sanitize_raw_urls(ref_trouble_raw, allow_urls=[])
    troubleshooting_md = replace_concrete_dates_with_placeholder(troubleshooting_md)
    troubleshooting_md = remove_placeholder_todo_code_blocks(troubleshooting_md)
    troubleshooting_md = strip_url_placeholders(troubleshooting_md).rstrip() + "\n"

    edge_cases_md = sanitize_raw_urls(ref_edge_raw, allow_urls=[])
    edge_cases_md = replace_concrete_dates_with_placeholder(edge_cases_md)
    edge_cases_md = remove_placeholder_todo_code_blocks(edge_cases_md)
    edge_cases_md = strip_url_placeholders(edge_cases_md).rstrip() + "\n"

    examples_md = sanitize_raw_urls(ref_examples_raw, allow_urls=[])
    examples_md = remove_placeholder_todo_code_blocks(examples_md)
    examples_md = ensure_at_least_one_code_block_any(examples_md)
    examples_md = strip_url_placeholders(examples_md).rstrip() + "\n"

    changelog_md = sanitize_raw_urls(ref_changelog_raw, allow_urls=[])
    changelog_md = normalize_changelog_md(changelog_md=changelog_md, package_generated_at=str(package_generated_at or "").strip())

    if not library_md.strip():
        library_md = "# Library\n\n```bash\necho \"OK\"\n```\n"
    if not sources_md.strip():
        sources_md = normalize_sources_md(
            sources_md="# Sources\n",
            source_url=allow[0] if allow else "",
            source_fetched_at=str(source_fetched_at or "").strip(),
            package_generated_at=str(package_generated_at or "").strip(),
        )
    if not troubleshooting_md.strip():
        troubleshooting_md = "# Troubleshooting\n\n- Add common failures and fixes.\n"
    if not edge_cases_md.strip():
        edge_cases_md = "# Edge Cases\n\n- Add non-obvious pitfalls and safe handling.\n"
    if not examples_md.strip():
        examples_md = "# Examples\n\n```bash\necho \"example\"\n```\n"
    if not changelog_md.strip():
        changelog_md = normalize_changelog_md(changelog_md="", package_generated_at=str(package_generated_at or "").strip())

    return PackageV2(
        library_md=library_md,
        reference={
            "sources_md": sources_md,
            "troubleshooting_md": troubleshooting_md,
            "edge_cases_md": edge_cases_md,
            "examples_md": examples_md,
            "changelog_md": changelog_md,
        },
    )


def generate_package_v2_for_skill_dir(*, skill_dir: str | Path, llm: LlmClient) -> None:
    d = Path(skill_dir)
    if not d.exists():
        raise FileNotFoundError(f"skill_dir not found: {d}")

    meta_path = d / "metadata.yaml"
    if not meta_path.exists():
        raise FileNotFoundError(f"metadata.yaml not found: {d}")

    md_path = d / "skill.md"
    if not md_path.exists():
        raise FileNotFoundError(f"skill.md not found: {d}")

    meta = parse_metadata_yaml_text(read_text(meta_path))
    domain = str(meta.get("domain") or "").strip()
    method = str(meta.get("source_type") or "").strip()
    skill_id = str(meta.get("id") or "").strip()
    title = str(meta.get("title") or "").strip()
    source_url = str(meta.get("source_url") or "").strip()
    skill_md = read_text(md_path)

    source_excerpt = ""
    source_fetched_at = ""
    src_path = d / "source.json"
    if src_path.exists():
        try:
            import json

            src = json.loads(src_path.read_text(encoding="utf-8-sig"))
            if isinstance(src, dict):
                source_excerpt = str(src.get("extracted_text") or "")
                source_fetched_at = str(src.get("fetched_at") or "").strip()
        except Exception:
            source_excerpt = ""
            source_fetched_at = ""
    else:
        artifact_id = str(meta.get("source_artifact_id") or "").strip()
        sources_dir = find_nearest_sources_dir(d) if artifact_id else None
        artifact_path = (sources_dir / f"{artifact_id}.json") if sources_dir and artifact_id else None
        if artifact_path and artifact_path.exists():
            try:
                import json

                src = json.loads(artifact_path.read_text(encoding="utf-8-sig"))
                if isinstance(src, dict):
                    source_excerpt = str(src.get("extracted_text") or "")
                    source_fetched_at = str(src.get("fetched_at") or "").strip()
            except Exception:
                source_excerpt = ""
                source_fetched_at = ""

    now_iso = utc_now_iso_z()
    pkg = build_skill_package_v2_with_llm(
        llm=llm,
        domain=domain,
        method=method,
        skill_id=skill_id,
        title=title,
        source_url=source_url,
        source_fetched_at=source_fetched_at,
        package_generated_at=now_iso,
        license_spdx=str(meta.get("license_spdx") or ""),
        license_risk=str(meta.get("license_risk") or ""),
        skill_md=skill_md,
        source_excerpt=source_excerpt,
    )

    write_text_atomic(d / "library.md", pkg.library_md)
    ref_dir = d / "reference"
    ensure_dir(ref_dir)
    write_text_atomic(ref_dir / "sources.md", pkg.reference["sources_md"])
    write_text_atomic(ref_dir / "troubleshooting.md", pkg.reference["troubleshooting_md"])
    write_text_atomic(ref_dir / "edge-cases.md", pkg.reference["edge_cases_md"])
    write_text_atomic(ref_dir / "examples.md", pkg.reference["examples_md"])
    write_text_atomic(ref_dir / "changelog.md", pkg.reference["changelog_md"])

    meta_out = dict(meta)
    meta_out["package_schema_version"] = 2
    meta_out["package_generated_at"] = now_iso
    meta_out["package_llm_provider"] = getattr(llm, "provider", "")
    meta_out["package_llm_model"] = getattr(llm, "model", "")
    write_text_atomic(meta_path, write_metadata_yaml_text(meta_out))
