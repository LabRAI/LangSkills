from __future__ import annotations

from dataclasses import dataclass

from .hashing import sha256_hex
from .text import normalize_for_fingerprint


@dataclass(frozen=True)
class Fingerprint:
    algo: str
    shingle_size: int
    step: int
    text_len: int
    hashes: list[str]

    def to_dict(self) -> dict:
        return {
            "algo": self.algo,
            "shingle_size": self.shingle_size,
            "step": self.step,
            "text_len": self.text_len,
            "hashes": list(self.hashes),
        }


def build_fingerprint(
    text: str,
    *,
    shingle_size: int = 24,
    step: int = 8,
    max_hashes: int = 2000,
) -> Fingerprint:
    s = normalize_for_fingerprint(text)
    size = max(8, int(shingle_size or 24))
    stride = max(1, int(step or 8))
    limit = max(50, int(max_hashes or 2000))

    hashes: list[str] = []
    seen: set[str] = set()
    for i in range(0, max(0, len(s) - size + 1), stride):
        h = sha256_hex(s[i : i + size])[:16]
        if h in seen:
            continue
        seen.add(h)
        hashes.append(h)
        if len(hashes) >= limit:
            break

    return Fingerprint(
        algo="sha256-shingle",
        shingle_size=size,
        step=stride,
        text_len=len(s),
        hashes=hashes,
    )

