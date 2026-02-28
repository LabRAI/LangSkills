from __future__ import annotations

import re


def extract_section(md: str, heading_name_regex: str) -> str:
    lines = str(md or "").replace("\r\n", "\n").split("\n")
    heading_re = re.compile(rf"^##\s+{heading_name_regex}\s*$", flags=re.IGNORECASE)

    start = -1
    in_fence = False
    for i, line in enumerate(lines):
        if re.match(r"^```", line.strip()):
            in_fence = not in_fence
        if in_fence:
            continue
        if heading_re.match(line.strip()):
            start = i + 1
            break
    if start < 0:
        return ""

    end = len(lines)
    in_fence = False
    for i in range(start, len(lines)):
        if re.match(r"^```", lines[i].strip()):
            in_fence = not in_fence
        if in_fence:
            continue
        if re.match(r"^##\s+\S", lines[i].strip()):
            end = i
            break
    return "\n".join(lines[start:end]).strip()


def count_fenced_code_blocks(md: str) -> int:
    return int(len(re.findall(r"```", str(md or ""))) // 2)


def _remove_fenced_code_blocks(md: str) -> str:
    """
    Remove fenced code blocks (```...```) from markdown.
    Used by linting to avoid flagging URLs that appear only inside runnable snippets.
    """
    lines = str(md or "").replace("\r\n", "\n").split("\n")
    out: list[str] = []
    in_fence = False
    for line in lines:
        if re.match(r"^```", line.strip()):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out)


def find_raw_urls(md: str) -> list[str]:
    """
    Find raw http(s) URLs in markdown *outside* fenced code blocks.

    Many runnable snippets (curl, wget, API endpoints) contain URLs and should not be
    flagged as "raw URLs" for skill linting/validation purposes.
    """
    text = _remove_fenced_code_blocks(str(md or ""))
    return re.findall(r"https?://\S+", text)


def lint_skill_markdown(skill_md: str) -> list[str]:
    md = str(skill_md or "")
    issues: list[str] = []

    def has_heading_any(names: list[str]) -> bool:
        for name in names:
            n = str(name or "").strip()
            if not n:
                continue
            if re.search(rf"^##\s+{re.escape(n)}\s*$", md, flags=re.IGNORECASE | re.MULTILINE):
                return True
        return False

    if not md.strip():
        issues.append("skill.md is empty")
    if not re.match(r"^#\s+", md.strip()):
        issues.append("Missing '# <Title>' heading")
    if not has_heading_any(["Steps"]):
        issues.append("Missing '## Steps' section")
    if not has_heading_any(["Verification"]):
        issues.append("Missing '## Verification' section")
    if not has_heading_any(["Safety"]):
        issues.append("Missing '## Safety' section")
    if not has_heading_any(["Evidence"]):
        issues.append("Missing '## Evidence' section")
    if not has_heading_any(["Sources"]):
        issues.append("Missing '## Sources' section")

    # Steps sanity: must be numbered, and keep <= 12 for readability.
    if has_heading_any(["Steps"]):
        lines = md.split("\n")
        start = -1
        for i, line in enumerate(lines):
            if re.match(r"^##\s+Steps\s*$", line.strip(), flags=re.IGNORECASE):
                start = i + 1
                break
        end = len(lines)
        if start >= 0:
            for j in range(start, len(lines)):
                if re.match(r"^##\s+\S", lines[j].strip()):
                    end = j
                    break
        steps_text = "\n".join(lines[start:end]) if start >= 0 else ""
        step_lines = [l.strip() for l in steps_text.split("\n") if re.match(r"^\d+\.\s+", l.strip())]
        if len(step_lines) == 0:
            issues.append("No numbered steps found (expected '1. ...')")
        if len(step_lines) > 12:
            issues.append(f"Too many steps ({len(step_lines)}); expected <= 12")

    if count_fenced_code_blocks(md) < 1:
        issues.append("No fenced code blocks found (expected at least 1 for commands/snippets)")

    sources_section = extract_section(md, "Sources")
    without_sources = md.replace(sources_section, "") if sources_section else md
    without_sources_no_code = _remove_fenced_code_blocks(without_sources)
    if find_raw_urls(without_sources_no_code):
        issues.append("Raw URLs found outside Sources section")

    return issues
