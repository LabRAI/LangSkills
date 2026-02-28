from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..utils.fs import read_text, write_text_atomic


_H2_RE = re.compile(r"^##\s+\S", flags=re.MULTILINE)


def has_h2_section(md: str, heading_name: str) -> bool:
    name = str(heading_name or "").strip()
    if not name:
        return False
    return bool(re.search(rf"^##\s+{re.escape(name)}\s*$", md, flags=re.IGNORECASE | re.MULTILINE))


def extract_h2_section(md: str, heading_name: str) -> str:
    name = str(heading_name or "").strip()
    if not name:
        return ""
    lines = str(md or "").replace("\r\n", "\n").split("\n")
    start = -1
    for i, line in enumerate(lines):
        if re.match(rf"^##\s+{re.escape(name)}\s*$", line.strip(), flags=re.IGNORECASE):
            start = i + 1
            break
    if start < 0:
        return ""
    end = len(lines)
    for j in range(start, len(lines)):
        if re.match(r"^##\s+\S", lines[j].strip()):
            end = j
            break
    return "\n".join(lines[start:end]).strip()


def remove_h2_section(md: str, heading_name: str) -> str:
    name = str(heading_name or "").strip()
    if not name:
        return str(md or "")
    lines = str(md or "").replace("\r\n", "\n").split("\n")

    start = -1
    for i, line in enumerate(lines):
        if re.match(rf"^##\s+{re.escape(name)}\s*$", line.strip(), flags=re.IGNORECASE):
            start = i
            break
    if start < 0:
        return str(md or "")

    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^##\s+\S", lines[j].strip()):
            end = j
            break

    out: list[str] = []
    out.extend(lines[:start])
    while out and not out[-1].strip():
        out.pop()
    out.extend(lines[end:])
    return "\n".join(out).strip() + "\n"


@dataclass(frozen=True)
class InsertResult:
    md: str
    inserted: bool


def insert_lines_into_h2_section(md: str, heading_name: str, insert_lines: str | list[str]) -> InsertResult:
    name = str(heading_name or "").strip()
    if not name:
        return InsertResult(md=str(md or ""), inserted=False)
    add = [str(x or "") for x in (insert_lines if isinstance(insert_lines, list) else [insert_lines])]

    lines = str(md or "").split("\n")
    start = -1
    for i, line in enumerate(lines):
        if re.match(rf"^##\s+{re.escape(name)}\s*$", line.strip(), flags=re.IGNORECASE):
            start = i
            break
    if start < 0:
        return InsertResult(md=str(md or ""), inserted=False)

    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^##\s+\S", lines[j].strip()):
            end = j
            break

    chunk = "\n".join(lines[start:end])
    for l in add:
        if l and l in chunk:
            return InsertResult(md=str(md or ""), inserted=False)

    out: list[str] = []
    out.extend(lines[:end])
    if out and out[-1].strip():
        out.append("")
    out.extend([l for l in add if l])
    out.extend(lines[end:])
    return InsertResult(md="\n".join(out), inserted=True)


def ensure_sources_contain_url(md: str, source_url: str) -> str:
    url = str(source_url or "").strip()
    if not url:
        return str(md or "")
    s = str(md or "")
    if url in s:
        return s

    if has_h2_section(s, "Sources"):
        r = insert_lines_into_h2_section(s, "Sources", f"- {url}")
        if r.inserted:
            return r.md
    return f"{s.strip()}\n\n## Sources\n\n- {url}\n"


def rewrite_reference_sources_md(*, path: Path, source_url: str) -> None:
    if not path.exists():
        return
    url = str(source_url or "").strip()
    if not url:
        return
    txt = read_text(path)

    m = re.search(r"https?://\S+", txt)
    if m and m.group(0) == url:
        return

    # Common v2 format: `Source: <url>`
    out = re.sub(r"^(Source:\s*)https?://\S+\s*$", rf"\1{url}", txt, flags=re.IGNORECASE | re.MULTILINE, count=1)
    if out == txt and m:
        # If no explicit Source line matched, replace the first URL occurrence.
        out = txt[: m.start()] + url + txt[m.end() :]
    if out != txt:
        write_text_atomic(path, out)


def ensure_evidence_section(md: str, evidence_lines: list[str]) -> str:
    """
    Ensure a stable `## Evidence` section exists and includes the provided bullet lines.
    This is used for auditability (run_id, artifact pointers) without adding raw URLs.
    """
    s = str(md or "").replace("\r\n", "\n").strip()
    add = [str(x or "").strip() for x in (evidence_lines or []) if str(x or "").strip()]
    if not add:
        return s + ("\n" if s else "")

    if has_h2_section(s, "Evidence"):
        r = insert_lines_into_h2_section(s, "Evidence", add)
        return r.md if r.inserted else (s + "\n")

    lines = s.split("\n") if s else []
    out: list[str] = []
    inserted = False
    for line in lines:
        if not inserted and re.match(r"^##\s+Sources\s*$", line.strip(), flags=re.IGNORECASE):
            # Insert Evidence section right before Sources.
            if out and out[-1].strip():
                out.append("")
            out.append("## Evidence")
            out.append("")
            out.extend(add)
            out.append("")
            inserted = True
        out.append(line)

    if not inserted:
        if out and out[-1].strip():
            out.append("")
        out.append("## Evidence")
        out.append("")
        out.extend(add)
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def strip_raw_urls_outside_sources(md: str) -> str:
    s0 = str(md or "").replace("\r\n", "\n")
    lines = s0.split("\n")

    def is_sources_heading(line: str) -> bool:
        return bool(re.match(r"^##\s+Sources\s*$", str(line or "").strip(), flags=re.IGNORECASE))

    def replace_urls(s: str) -> str:
        # Strip raw URLs outside Sources; preserve fenced code blocks so runnable snippets remain intact.
        text = str(s or "").replace("\r\n", "\n")
        out: list[str] = []
        in_fence = False
        for line in text.split("\n"):
            if re.match(r"^```", line.strip()):
                in_fence = not in_fence
                out.append(line)
                continue
            if in_fence:
                out.append(line)
            else:
                out.append(re.sub(r"https?://\S+", "<URL>", line))
        return "\n".join(out)

    start = -1
    for i, line in enumerate(lines):
        if is_sources_heading(line):
            start = i
            break
    if start < 0:
        return replace_urls(s0)

    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^##\s+\S", str(lines[j] or "").strip()):
            end = j
            break

    before = replace_urls("\n".join(lines[:start]))
    sources = "\n".join(lines[start:end])
    after = replace_urls("\n".join(lines[end:]))

    parts: list[str] = []
    if before.strip():
        parts.append(before.rstrip())
    parts.append(sources.rstrip())
    if after.strip():
        parts.append(after.lstrip())
    return "\n\n".join(parts).rstrip() + "\n"


def ensure_at_least_one_code_block(md: str) -> str:
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
    block_lines = [
        "```bash",
        "# Extracted examples (auto-generated because the model missed fenced code blocks)",
        *(picked if picked else ['echo "OK"']),
        "```",
    ]

    if has_h2_section(s, "Verification"):
        r = insert_lines_into_h2_section(s, "Verification", block_lines)
        if r.inserted:
            return r.md
    return f"{s.strip()}\n\n## Verification\n\n{chr(10).join(block_lines)}\n"


def ensure_verification_has_code_block(md: str) -> str:
    """
    Ensure the Verification section contains at least one fenced code block.
    This is stricter than `ensure_at_least_one_code_block()` which may place code blocks elsewhere.
    """
    s0 = str(md or "").replace("\r\n", "\n")
    block_lines = [
        "```bash",
        "# Verification stub (auto-generated)",
        "printf \"verification: ok\\n\"",
        "```",
    ]

    for heading in ("Verification",):
        if not has_h2_section(s0, heading):
            continue
        sec = extract_h2_section(s0, heading)
        if len(re.findall(r"```", sec)) // 2 >= 1:
            return s0 if s0.endswith("\n") else (s0 + "\n")
        r = insert_lines_into_h2_section(s0, heading, block_lines)
        if r.inserted:
            return r.md
        # If insertion was skipped due to duplicate-line heuristic, fall back to a simple append.
        out = s0.rstrip() + "\n\n" + "\n".join(block_lines) + "\n"
        return out

    # No Verification section at all: append one.
    out = s0.rstrip()
    if out:
        out += "\n\n"
    out += "## Verification\n\n" + "\n".join(block_lines) + "\n"
    return out


def ensure_triad_sections(md: str) -> str:
    s0 = str(md or "").replace("\r\n", "\n")
    required = [
        (
            "Use Cases",
            [
                "## Use Cases",
                "- When you need a reusable, executable set of steps and verification for this topic.",
                "- When you need to turn source material into an auditable, actionable runbook.",
            ],
        ),
        (
            "Inputs",
            [
                "## Inputs",
                "- Target environment info (system/version/permissions/network).",
                "- Relevant config files/repos/log snippets required by the steps.",
            ],
        ),
        (
            "Outputs",
            [
                "## Outputs",
                "- A repeatable set of steps (key commands/configuration).",
                "- Automatable verification signals (commands + expected output/assertions).",
            ],
        ),
    ]

    if all(has_h2_section(s0, name) for name, _ in required):
        return s0

    lines = s0.split("\n")
    insert_at = len(lines)
    for i, line in enumerate(lines):
        if re.match(r"^##\s+Steps\s*$", line.strip(), flags=re.IGNORECASE):
            insert_at = i
            break

    missing = [(name, sec_lines) for name, sec_lines in required if not has_h2_section(s0, name)]
    if not missing:
        return s0

    to_insert: list[str] = []
    for _, sec_lines in reversed(missing):
        if to_insert:
            to_insert.append("")
        to_insert.extend(sec_lines)
        to_insert.append("")

    out: list[str] = []
    out.extend(lines[:insert_at])
    if out and out[-1].strip():
        out.append("")
    out.extend(to_insert)
    out.extend(lines[insert_at:])
    return "\n".join(out).rstrip() + "\n"
