from __future__ import annotations

import re


def extract_regex_symbols(*, text: str, language: str) -> list[tuple[str, str, int]]:
    """
    Multi-language, dependency-free symbol extraction for non-Python files.
    Returns a list of (kind, name, start_line).

    This is intentionally conservative; it is used for discovery and evidence, not correctness.
    """
    lang = str(language or "").strip().lower()
    lines = str(text or "").replace("\r\n", "\n").split("\n")

    out: list[tuple[str, str, int]] = []

    def add(kind: str, name: str, ln: int) -> None:
        n = str(name or "").strip()
        if not n:
            return
        out.append((str(kind), n, int(ln)))

    if lang in {"javascript", "typescript"}:
        re_fn = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(")
        re_cls = re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_$][A-Za-z0-9_$]*)\b")
        re_arrow = re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?.*=>")
        for i, ln in enumerate(lines, start=1):
            m = re_fn.match(ln)
            if m:
                add("function", m.group(1), i)
                continue
            m = re_cls.match(ln)
            if m:
                add("class", m.group(1), i)
                continue
            m = re_arrow.match(ln)
            if m:
                add("function", m.group(1), i)
                continue

    elif lang == "go":
        re_fn = re.compile(r"^\s*func\s+(?:\([^)]+\)\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\(")
        re_type = re.compile(r"^\s*type\s+([A-Za-z_][A-Za-z0-9_]*)\s+(?:struct|interface)\b")
        for i, ln in enumerate(lines, start=1):
            m = re_fn.match(ln)
            if m:
                add("function", m.group(1), i)
                continue
            m = re_type.match(ln)
            if m:
                add("type", m.group(1), i)
                continue

    elif lang == "rust":
        re_fn = re.compile(r"^\s*(?:pub\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")
        re_struct = re.compile(r"^\s*(?:pub\s+)?struct\s+([A-Za-z_][A-Za-z0-9_]*)\b")
        re_enum = re.compile(r"^\s*(?:pub\s+)?enum\s+([A-Za-z_][A-Za-z0-9_]*)\b")
        for i, ln in enumerate(lines, start=1):
            m = re_fn.match(ln)
            if m:
                add("function", m.group(1), i)
                continue
            m = re_struct.match(ln)
            if m:
                add("type", m.group(1), i)
                continue
            m = re_enum.match(ln)
            if m:
                add("type", m.group(1), i)
                continue

    elif lang == "java":
        re_type = re.compile(r"^\s*(?:public|protected|private)?\s*(?:final\s+)?(?:class|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)\b")
        for i, ln in enumerate(lines, start=1):
            m = re_type.match(ln)
            if m:
                add("type", m.group(1), i)
                continue

    # De-dupe while preserving order.
    seen: set[tuple[str, str, int]] = set()
    deduped: list[tuple[str, str, int]] = []
    for it in out:
        if it in seen:
            continue
        seen.add(it)
        deduped.append(it)
    return deduped

