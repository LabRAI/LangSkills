from __future__ import annotations

from pathlib import Path
from typing import Any

from ..utils.time import utc_now_iso_z_seconds


def build_contracts_markdown(*, symbols: list[dict[str, Any]], repo_root: str | Path) -> str:
    repo_root = Path(repo_root).resolve()
    env_keys: set[str] = set()
    network_touch: list[str] = []
    entrypoints: list[str] = []
    stable_outputs: list[str] = []
    repo_url = ""
    git_commit = ""

    for s in symbols:
        if not repo_url and str(s.get("repo_url") or "").strip():
            repo_url = str(s.get("repo_url") or "").strip()
            git_commit = str(s.get("git_commit") or "").strip()
        for k in s.get("reads_env") or []:
            ks = str(k or "").strip()
            if ks:
                env_keys.add(ks)
        if bool(s.get("network")):
            qn = str(s.get("qualified_name") or "").strip()
            if qn:
                network_touch.append(qn)
        if str(s.get("qualified_name") or "").endswith(".main") or str(s.get("qualified_name") or "") in {"core.cli.main"}:
            qn = str(s.get("qualified_name") or "").strip()
            if qn:
                entrypoints.append(qn)
        for w in s.get("writes") or []:
            ws = str(w or "").strip()
            if ws:
                stable_outputs.append(ws)

    # Keep short and actionable; more detail lives in symbol_index.jsonl.
    lines: list[str] = []
    lines.append("# Contracts\n")
    lines.append(f"- Generated at: {utc_now_iso_z_seconds()}")
    if repo_url:
        if git_commit:
            lines.append(f"- Repo: `{repo_url}` @ `{git_commit}`")
        else:
            lines.append(f"- Repo: `{repo_url}`")
    lines.append(f"- Repo root: `{repo_root.as_posix()}`\n")

    lines.append("## Environment")
    if env_keys:
        for k in sorted(env_keys):
            lines.append(f"- `{k}`")
    else:
        lines.append("- (none detected)")
    lines.append("")

    lines.append("## Network Touchpoints")
    if network_touch:
        for qn in sorted(set(network_touch))[:40]:
            lines.append(f"- `{qn}`")
        if len(set(network_touch)) > 40:
            lines.append(f"- … and {len(set(network_touch)) - 40} more")
    else:
        lines.append("- (none detected)")
    lines.append("")

    lines.append("## Stable Outputs")
    outs = sorted(set(stable_outputs))
    if outs:
        for o in outs[:60]:
            lines.append(f"- `{o}`")
        if len(outs) > 60:
            lines.append(f"- … and {len(outs) - 60} more")
    else:
        lines.append("- (none detected)")
    lines.append("")

    lines.append("## Entrypoints")
    eps = sorted(set(entrypoints))
    if eps:
        for qn in eps[:40]:
            lines.append(f"- `{qn}`")
        if len(eps) > 40:
            lines.append(f"- … and {len(eps) - 40} more")
    else:
        lines.append("- (none detected)")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_contracts(*, repo_root: str | Path, symbols: list[dict[str, Any]], out_path: str | Path) -> str:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = build_contracts_markdown(symbols=symbols, repo_root=repo_root)
    p.write_text(text, encoding="utf-8")
    return p.resolve().as_posix()
