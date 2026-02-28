from __future__ import annotations

from typing import Any


def _strip_yaml_comment(line: str) -> str:
    s = str(line or "")
    if "#" not in s:
        return s
    out: list[str] = []
    in_single = False
    in_double = False
    for ch in s:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            break
        out.append(ch)
    return "".join(out)


def _split_key_value(raw: str) -> tuple[str, str | None, bool]:
    s = str(raw or "")
    in_single = False
    in_double = False
    for i, ch in enumerate(s):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == ":" and not in_single and not in_double:
            nxt = s[i + 1 : i + 2]
            if nxt and not nxt.isspace():
                continue
            key = s[:i].strip()
            rest = s[i + 1 :].strip()
            return key, (rest if rest != "" else None), True
    return s.strip(), None, False


def _split_inline_list_items(s: str) -> list[str]:
    items: list[str] = []
    buf: list[str] = []
    in_single = False
    in_double = False
    for ch in str(s or ""):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        if ch == "," and not in_single and not in_double:
            items.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail or items:
        items.append(tail)
    return [x for x in items if x != ""]


def _parse_scalar(raw: str) -> Any:
    s = str(raw or "").strip()
    if s == "":
        return ""
    if s in {"null", "Null", "NULL", "~"}:
        return None
    if s in {"true", "True", "TRUE"}:
        return True
    if s in {"false", "False", "FALSE"}:
        return False
    if s == "[]":
        return []
    if s == "{}":
        return {}
    if len(s) >= 2 and ((s[0] == s[-1] == "'") or (s[0] == s[-1] == '"')):
        # Best-effort unquote; keep escapes as-is.
        return s[1:-1]
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(x) for x in _split_inline_list_items(inner)]
    try:
        if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
            return int(s)
    except Exception:
        pass
    try:
        # Handle simple floats like 0.1 / -1.5
        if any(c in s for c in [".", "e", "E"]) and not any(c.isspace() for c in s):
            return float(s)
    except Exception:
        pass
    return s


def safe_load_yaml_text(text: str) -> Any:
    """
    Very small YAML subset loader (dependency-free).

    Supports the formats used by this repo:
    - top-level mapping with nested mappings/lists
    - lists of scalars or dict items
    - inline lists like: [a, b, c]

    Not a general-purpose YAML parser.
    """
    raw_lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines: list[tuple[int, str]] = []
    for raw in raw_lines:
        cleaned = _strip_yaml_comment(raw).rstrip()
        if not cleaned.strip():
            continue
        indent = len(cleaned) - len(cleaned.lstrip(" "))
        lines.append((indent, cleaned.lstrip(" ")))

    def parse_block(i: int, indent: int) -> tuple[Any, int]:
        if i >= len(lines):
            return {}, i
        cur_indent, cur = lines[i]
        if cur_indent != indent:
            return {}, i

        # Sequence block
        if cur.startswith("- "):
            arr: list[Any] = []
            while i < len(lines):
                li_indent, li = lines[i]
                if li_indent != indent or not li.startswith("- "):
                    break
                rest = li[2:].strip()
                i += 1
                if rest == "":
                    # Nested item
                    if i < len(lines) and lines[i][0] > indent:
                        child, i = parse_block(i, lines[i][0])
                        arr.append(child)
                    else:
                        arr.append({})
                    continue

                k, v, has_delim = _split_key_value(rest)
                item: Any
                if has_delim and k:
                    if v is None:
                        item = {k: {}}
                        if i < len(lines) and lines[i][0] > indent:
                            child, i = parse_block(i, lines[i][0])
                            item[k] = child
                    else:
                        item = {k: _parse_scalar(v)}
                else:
                    item = _parse_scalar(rest)

                if i < len(lines) and lines[i][0] > indent:
                    child, i = parse_block(i, lines[i][0])
                    if isinstance(item, dict) and isinstance(child, dict):
                        item.update(child)
                    elif rest == "":
                        item = child
                arr.append(item)
            return arr, i

        # Mapping block
        obj: dict[str, Any] = {}
        while i < len(lines):
            li_indent, li = lines[i]
            if li_indent != indent or li.startswith("- "):
                break
            key, v, has_delim = _split_key_value(li)
            i += 1
            if not key or not has_delim:
                continue
            if v is None:
                # Nested mapping/list (or empty)
                if i < len(lines) and lines[i][0] > indent:
                    child, i = parse_block(i, lines[i][0])
                    obj[key] = child
                else:
                    obj[key] = {}
                continue
            obj[key] = _parse_scalar(v)
        return obj, i

    if not lines:
        return {}
    root, _ = parse_block(0, lines[0][0])
    return root
