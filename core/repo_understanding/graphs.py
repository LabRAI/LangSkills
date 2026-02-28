from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def build_import_graph(symbols: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Conservative import graph:
    - Nodes: module qualified_name
    - Edges: module -> imported module string
    """
    modules = [s for s in symbols if str(s.get("kind") or "") == "module"]
    edges: list[dict[str, str]] = []
    nodes: set[str] = set()

    for m in modules:
        src = str(m.get("qualified_name") or "").strip()
        if not src:
            continue
        nodes.add(src)
        for imp in m.get("imports") or []:
            dst = str(imp or "").strip()
            if not dst:
                continue
            edges.append({"from": src, "to": dst})
            nodes.add(dst)

    return {"nodes": sorted(nodes), "edges": edges}


def build_call_graph(symbols: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Conservative call graph:
    - Nodes: function/method qualified_name
    - Edges: qualified_name -> called expression (string; may be unresolved)
    """
    funcs = [s for s in symbols if str(s.get("kind") or "") in {"function", "method"}]
    edges: list[dict[str, str]] = []
    nodes: set[str] = set()

    for fn in funcs:
        src = str(fn.get("qualified_name") or "").strip()
        if not src:
            continue
        nodes.add(src)
        for call in fn.get("calls") or []:
            dst = str(call or "").strip()
            if not dst:
                continue
            edges.append({"from": src, "to": dst})

    return {"nodes": sorted(nodes), "edges": edges}

