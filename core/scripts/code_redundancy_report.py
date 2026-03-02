from __future__ import annotations

import argparse
import ast
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..utils.paths import repo_root


@dataclass(frozen=True)
class DefRef:
    path: Path
    line: int
    name: str


def _iter_py_files(base: Path) -> Iterable[Path]:
    for p in base.rglob("*.py"):
        if p.is_file():
            yield p


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    if body and isinstance(body[0], ast.Expr):
        v = body[0].value
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            return body[1:]
    return body


def _is_trivial_body(body: list[ast.stmt]) -> bool:
    if not body:
        return True
    if len(body) == 1 and isinstance(body[0], ast.Pass):
        return True
    if len(body) == 1 and isinstance(body[0], ast.Expr):
        v = body[0].value
        if isinstance(v, ast.Constant) and v.value is Ellipsis:
            return True
    return False


def _func_signature(node: ast.AST) -> str:
    import copy

    n = copy.deepcopy(node)
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
        n.name = "__fn__"
        n.body = _strip_docstring(n.body)
        if _is_trivial_body(n.body):
            return ""
    return ast.dump(n, include_attributes=False)


def _collect_regex_patterns(node: ast.AST, *, path: Path) -> list[tuple[str, int]]:
    patterns: list[tuple[str, int]] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            fn = sub.func
            if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) and fn.value.id == "re" and fn.attr == "compile":
                if sub.args and isinstance(sub.args[0], ast.Constant) and isinstance(sub.args[0].value, str):
                    pat = str(sub.args[0].value)
                    patterns.append((pat, getattr(sub, "lineno", 1)))
    return patterns


def _collect_url_literals(node: ast.AST, *, path: Path) -> list[tuple[str, int]]:
    urls: list[tuple[str, int]] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            s = str(sub.value)
            if s in {"http://", "https://"}:
                continue
            if s.startswith("http://") or s.startswith("https://"):
                urls.append((s, getattr(sub, "lineno", 1)))
    return urls


def _format_refs(refs: list[DefRef]) -> list[str]:
    out: list[str] = []
    for r in sorted(refs, key=lambda x: (str(x.path), x.line, x.name)):
        rel = r.path.as_posix()
        out.append(f"  - `{rel}`:{r.line} ({r.name})")
    return out


def cli_code_redundancy_report(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills-rai code-redundancy-report")
    parser.add_argument("--root", default=None, help="Repo root (defaults to detected)")
    parser.add_argument("--out", default="docs/code_redundancy_report.md")
    ns = parser.parse_args(argv)

    root_dir = Path(ns.root).resolve() if ns.root else repo_root()
    base = root_dir / "langskills"
    py_files = sorted(_iter_py_files(base))

    hash_map: dict[str, list[Path]] = defaultdict(list)
    func_name_map: dict[str, list[DefRef]] = defaultdict(list)
    class_name_map: dict[str, list[DefRef]] = defaultdict(list)
    func_sig_map: dict[str, list[DefRef]] = defaultdict(list)
    regex_map: dict[str, list[DefRef]] = defaultdict(list)
    url_map: dict[str, list[DefRef]] = defaultdict(list)

    for p in py_files:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        hash_map[_file_hash(p)].append(p)

        try:
            tree = ast.parse(text)
        except Exception:
            continue

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_name_map[node.name].append(DefRef(path=p.relative_to(root_dir), line=int(node.lineno), name=node.name))
                sig = _func_signature(node)
                if sig:
                    func_sig_map[sig].append(DefRef(path=p.relative_to(root_dir), line=int(node.lineno), name=node.name))
            elif isinstance(node, ast.ClassDef):
                class_name_map[node.name].append(DefRef(path=p.relative_to(root_dir), line=int(node.lineno), name=node.name))

        for pat, line in _collect_regex_patterns(tree, path=p):
            regex_map[pat].append(DefRef(path=p.relative_to(root_dir), line=line, name="re.compile"))

        for url, line in _collect_url_literals(tree, path=p):
            url_map[url].append(DefRef(path=p.relative_to(root_dir), line=line, name="url"))

    file_dupes = {h: ps for h, ps in hash_map.items() if len(ps) > 1}
    func_dupes = {name: refs for name, refs in func_name_map.items() if len(refs) > 1}
    class_dupes = {name: refs for name, refs in class_name_map.items() if len(refs) > 1}
    func_body_dupes = {sig: refs for sig, refs in func_sig_map.items() if len(refs) > 1}

    regex_dupes = {}
    for pat, refs in regex_map.items():
        uniq_files = {r.path for r in refs}
        if len(refs) > 1 and len(uniq_files) > 1 and len(pat) >= 6:
            regex_dupes[pat] = refs

    url_dupes = {}
    for url, refs in url_map.items():
        uniq_files = {r.path for r in refs}
        if len(refs) > 1 and len(uniq_files) > 1:
            url_dupes[url] = refs

    lines: list[str] = []
    lines.append("# Code Redundancy Report")
    lines.append("")
    lines.append("Notes: This report counts only top-level function/class definitions. Methods and nested defs are ignored. CLI entrypoint is `langskills/cli.py:main`.")
    lines.append("")

    lines.append("## Exact Duplicate Code Files (SHA256)")
    lines.append("")
    if not file_dupes:
        lines.append("- None found.")
    else:
        for h, paths in sorted(file_dupes.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            lines.append(f"- {h} ({len(paths)} files)")
            for p in sorted(paths):
                lines.append(f"  - {p.as_posix()}")

    lines.append("## Duplicate Function Names (Top-level)")
    lines.append("")
    if not func_dupes:
        lines.append("- None found.")
    else:
        for name, refs in sorted(func_dupes.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            lines.append(f"- `{name}` ({len(refs)} defs)")
            lines.extend(_format_refs(refs))
            lines.append("")

    lines.append("## Duplicate Class Names (Top-level)")
    lines.append("")
    if not class_dupes:
        lines.append("- None found.")
    else:
        for name, refs in sorted(class_dupes.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            lines.append(f"- `{name}` ({len(refs)} defs)")
            lines.extend(_format_refs(refs))
            lines.append("")

    lines.append("## Duplicate Function Bodies (AST Signature)")
    lines.append("")
    if not func_body_dupes:
        lines.append("- None found.")
    else:
        for sig, refs in sorted(func_body_dupes.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:50]:
            lines.append(f"- Signature hash `{hashlib.sha256(sig.encode('utf-8')).hexdigest()[:12]}` ({len(refs)} defs)")
            lines.extend(_format_refs(refs))
            lines.append("")
        if len(func_body_dupes) > 50:
            lines.append(f"- … and {len(func_body_dupes) - 50} more")

    lines.append("## Duplicate Regex Patterns (re.compile)")
    lines.append("")
    if not regex_dupes:
        lines.append("- None found.")
    else:
        for pat, refs in sorted(regex_dupes.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:50]:
            preview = pat if len(pat) <= 120 else pat[:117] + "..."
            lines.append(f"- `{preview}` ({len(refs)} refs)")
            lines.extend(_format_refs(refs))
            lines.append("")
        if len(regex_dupes) > 50:
            lines.append(f"- … and {len(regex_dupes) - 50} more")

    lines.append("## Duplicate URL Literals")
    lines.append("")
    if not url_dupes:
        lines.append("- None found.")
    else:
        for url, refs in sorted(url_dupes.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:50]:
            preview = url if len(url) <= 120 else url[:117] + "..."
            lines.append(f"- `{preview}` ({len(refs)} refs)")
            lines.extend(_format_refs(refs))
            lines.append("")
        if len(url_dupes) > 50:
            lines.append(f"- … and {len(url_dupes) - 50} more")

    lines.append("## Thin Wrapper Scripts (likely redundant by design)")
    lines.append("")
    for name in [
        "scripts/auto-pr.py",
        "scripts/backfill-package-v2.py",
        "scripts/build-site.py",
        "scripts/runner.py",
        "scripts/self-check.py",
        "scripts/validate-skills.py",
    ]:
        lines.append(f"- `{name}`")
    lines.append("")

    out_path = Path(ns.out)
    if not out_path.is_absolute():
        out_path = (root_dir / out_path).resolve()
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_code_redundancy_report())
