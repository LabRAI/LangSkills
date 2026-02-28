from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def overlap_ratio_by_fingerprint(fp_a: dict | None, fp_b: dict | None) -> float:
    a = [str(x) for x in (fp_a.get("hashes") if isinstance(fp_a, dict) else []) or []]
    b = [str(x) for x in (fp_b.get("hashes") if isinstance(fp_b, dict) else []) or []]
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    denom = min(len(set_a), len(set_b))
    if denom <= 0:
        return 0.0
    hit = sum(1 for h in set_a if h in set_b)
    return float(hit) / float(denom)


@dataclass(frozen=True)
class SkillFp:
    id: str
    title: str
    rel_dir: str
    fingerprint: dict[str, Any]


def build_dedupe_clusters(*, skills: list[SkillFp], threshold: float = 0.25) -> dict[str, Any]:
    arr = list(skills or [])
    n = len(arr)
    parent = list(range(n))

    def find(x: int) -> int:
        p = x
        while parent[p] != p:
            p = parent[p]
        while parent[x] != x:
            nxt = parent[x]
            parent[x] = p
            x = nxt
        return p

    def union(a: int, b: int) -> None:
        ra = find(a)
        rb = find(b)
        if ra != rb:
            parent[rb] = ra

    sims: list[dict[str, Any]] = []
    t = max(0.0, min(1.0, float(threshold or 0.25)))
    for i in range(0, n):
        for j in range(i + 1, n):
            r = overlap_ratio_by_fingerprint(arr[i].fingerprint, arr[j].fingerprint)
            if r >= t:
                union(i, j)
                sims.append({"a": arr[i].id, "b": arr[j].id, "ratio": float(f"{r:.4f}")})

    by_root: dict[int, list[SkillFp]] = {}
    for i in range(0, n):
        root = find(i)
        by_root.setdefault(root, []).append(arr[i])

    clusters = [
        sorted(group, key=lambda x: x.id)
        for group in by_root.values()
        if len(group) >= 2
    ]
    clusters.sort(key=lambda g: (-len(g), g[0].id))

    return {
        "threshold": t,
        "clusters": [
            [{"id": s.id, "title": s.title, "rel_dir": s.rel_dir, "fingerprint": s.fingerprint} for s in group] for group in clusters
        ],
        "similar_pairs": sims,
    }

