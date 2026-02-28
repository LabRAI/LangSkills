from __future__ import annotations

import html as _html
import re
import unicodedata


def truncate_label(text: str, max_len: int = 80) -> str:
    s = str(text or "")
    if len(s) <= max_len:
        return s
    return f"{s[: max_len - 3]}..."


def truncate_text(text: str, max_chars: int) -> str:
    s = str(text or "")
    n = max(0, int(max_chars or 0))
    if n == 0:
        return ""
    if len(s) <= n:
        return s
    return f"{s[:n]}\n\n[TRUNCATED]"


def html_to_text(html: str) -> str:
    s = str(html or "")
    if not s:
        return ""
    s = s.replace("\r\n", "\n")

    s = re.sub(r"<script[\s\S]*?</script>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<style[\s\S]*?</style>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<noscript[\s\S]*?</noscript>", "\n", s, flags=re.IGNORECASE)

    s = re.sub(r"<!--([\s\S]*?)-->", "\n", s)

    s = re.sub(r"<(h[1-6]|p|pre|li|ul|ol|br|hr|section|article|div|tr|td|th|table)\b[^>]*>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</(h[1-6]|p|pre|li|ul|ol|section|article|div|tr|td|th|table)\s*>", "\n", s, flags=re.IGNORECASE)

    s = re.sub(r"<[^>]+>", " ", s)

    # Decode entities (legacy version only decoded a few; html.unescape is fine and simpler).
    s = _html.unescape(s)

    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


_URL_RE = re.compile(r"https?://\S+", flags=re.IGNORECASE)


def normalize_for_fingerprint(text: str) -> str:
    s = str(text or "")
    s = unicodedata.normalize("NFKC", s).lower()
    s = _URL_RE.sub(" ", s)
    # Keep only letters + numbers (Unicode categories L* and N*).
    kept = []
    for ch in s:
        cat = unicodedata.category(ch)
        if cat and (cat[0] == "L" or cat[0] == "N"):
            kept.append(ch)
    return "".join(kept).strip()
