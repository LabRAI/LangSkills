from __future__ import annotations

import re
from pathlib import Path


_LICENSE_FILENAMES = [
    "LICENSE",
    "LICENSE.md",
    "LICENSE.txt",
    "COPYING",
    "COPYING.txt",
    "COPYRIGHT",
]


def detect_spdx_from_license_text(text: str) -> str:
    s = str(text or "").strip().lower()
    if not s:
        return ""
    # Very small, conservative heuristics (enough to avoid "unknown" for common repos).
    if "mit license" in s:
        return "MIT"
    # BSD family: many repos use the canonical text without naming "BSD-3-Clause".
    if "redistribution and use in source and binary forms" in s and "this software is provided by the copyright holders and contributors" in s:
        if "neither the name of" in s and "contributors may be used to endorse or promote" in s:
            return "BSD-3-Clause"
        return "BSD-2-Clause"
    if "apache license" in s and ("version 2.0" in s or "apache license, version 2.0" in s):
        return "Apache-2.0"
    if "mozilla public license" in s and ("version 2.0" in s or "mpl 2.0" in s or "mpl-2.0" in s):
        return "MPL-2.0"
    if "isc license" in s:
        return "ISC"
    if "the unlicense" in s or "unlicense" in s:
        return "Unlicense"
    if "bsd 3-clause" in s or "new bsd license" in s:
        return "BSD-3-Clause"
    if "bsd 2-clause" in s or "simplified bsd license" in s:
        return "BSD-2-Clause"
    return ""


def detect_repo_license_spdx(repo_root: str | Path) -> str:
    root = Path(repo_root).resolve()
    for fn in _LICENSE_FILENAMES:
        p = root / fn
        if not p.exists() or not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")[:200_000]
        except Exception:
            continue
        spdx = detect_spdx_from_license_text(text)
        if spdx:
            return spdx
    # Also check for an SPDX header hint in README.
    readme = root / "README.md"
    if readme.exists():
        try:
            text = readme.read_text(encoding="utf-8", errors="replace")[:60_000]
        except Exception:
            text = ""
        m = re.search(r"(?i)SPDX-License-Identifier:\\s*([A-Za-z0-9.-]+)", text)
        if m:
            return str(m.group(1)).strip()
    return ""
