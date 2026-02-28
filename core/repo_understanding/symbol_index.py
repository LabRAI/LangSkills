from __future__ import annotations

import ast
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ingest import DEFAULT_BIG_FILE_BYTES, RepoFile, detect_language, is_binary_file
from .lang_extract import extract_regex_symbols


_SOURCE_EXT_RE = re.compile(r"\.(py|js|ts|go|rs|java)$", flags=re.IGNORECASE)


def _safe_rel_module_name(rel_path: str) -> str:
    p = str(rel_path).replace("\\", "/")
    p = _SOURCE_EXT_RE.sub("", p)
    p = p.replace("/", ".")
    p = re.sub(r"[^a-zA-Z0-9_.]+", "_", p)
    return p.strip(".")


def _signature_from_args(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = node.args
    parts: list[str] = []

    def fmt_arg(a: ast.arg) -> str:
        name = a.arg
        if a.annotation is None:
            return name
        try:
            ann = ast.unparse(a.annotation)
        except Exception:
            ann = ""
        return f"{name}: {ann}" if ann else name

    posonly = [fmt_arg(a) for a in getattr(args, "posonlyargs", [])]
    normal = [fmt_arg(a) for a in args.args]
    vararg = f"*{args.vararg.arg}" if args.vararg else ""
    kwonly = [fmt_arg(a) for a in args.kwonlyargs]
    kwarg = f"**{args.kwarg.arg}" if args.kwarg else ""

    if posonly:
        parts.extend(posonly)
        parts.append("/")
    parts.extend(normal)
    if vararg:
        parts.append(vararg)
    elif kwonly:
        parts.append("*")
    parts.extend(kwonly)
    if kwarg:
        parts.append(kwarg)

    ret = ""
    if node.returns is not None:
        try:
            ret = ast.unparse(node.returns)
        except Exception:
            ret = ""
    sig = f"({', '.join([p for p in parts if p])})"
    return f"{sig} -> {ret}" if ret else sig


def _first_doc_line(doc: str) -> str:
    s = str(doc or "").strip().replace("\r\n", "\n")
    return s.split("\n", 1)[0].strip() if s else ""


def _summary_lines_for_symbol(*, kind: str, qualified_name: str, doc: str, imports: list[str], calls: list[str]) -> list[str]:
    # Deterministic, short summaries (LLM-free). Designed to be indexable, not perfect prose.
    out: list[str] = []
    first = _first_doc_line(doc)
    if first:
        out.append(first)

    base = qualified_name.split(".")[-1]
    if not out:
        if kind == "module":
            out.append(f"Module {qualified_name} ({len(imports)} imports).")
        elif kind == "class":
            out.append(f"Class {base}.")
        else:
            out.append(f"{kind.capitalize()} {base}.")

    if calls:
        out.append(f"Calls: {', '.join(calls[:8])}{'…' if len(calls) > 8 else ''}.")
    return out[:10]


_OUTPUT_NAME_RE = re.compile(r"\.(jsonl?|md|ya?ml|txt|html|csv|tsv|py)$", flags=re.IGNORECASE)


def _string_literals_in(node: ast.AST, *, max_items: int = 6) -> list[str]:
    out: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            s = str(sub.value).strip()
            if not s:
                continue
            if len(s) > 260:
                continue
            if _OUTPUT_NAME_RE.search(s) or "/" in s:
                out.append(s)
                if len(out) >= max_items:
                    break
    return out


def _normalize_write_targets(items: list[str]) -> list[str]:
    out: list[str] = []
    for raw in items:
        s = str(raw or "").strip()
        if not s:
            continue
        # Normalize common repo artifacts into stable patterns for auditability.
        if s.endswith("manifest.json"):
            out.append("captures/run-*/manifest.json")
            continue
        if s.endswith("quality_report.md"):
            out.append("captures/run-*/quality_report.md")
            continue
        if s.endswith("repo_tree.json"):
            out.append("captures/repo_tree.json")
            continue
        if s.endswith("repo_state.json"):
            out.append("captures/repo_state.json")
            continue
        if s.endswith("repo_index_summary.json"):
            out.append("captures/repo_index_summary.json")
            continue
        if s.endswith("symbol_index.jsonl"):
            out.append("captures/symbol_index.jsonl")
            continue
        if s.endswith("import_graph.json"):
            out.append("captures/import_graph.json")
            continue
        if s.endswith("call_graph.json"):
            out.append("captures/call_graph.json")
            continue
        if s.endswith("run_index.jsonl"):
            out.append("captures/run_index.jsonl")
            continue
        out.append(s)
    return _dedupe_preserve_order(out)


def _network_hints(imports: list[str], calls: list[str]) -> list[str]:
    blob = " ".join(imports + calls).lower()
    hints: list[str] = []
    if "tavily" in blob:
        if "client.search" in blob or "search_web_urls_with_tavily" in blob:
            hints.append("tavily.search")
        if "client.extract" in blob or "fetch_webpage_text" in blob:
            hints.append("tavily.extract")
        if not hints:
            hints.append("tavily")
    if "api.github.com" in blob or "github_search_top_repos" in blob:
        hints.append("github.api")
    if "raw.githubusercontent.com" in blob or "github_fetch_readme" in blob:
        hints.append("github.raw")
    if "stackoverflow" in blob or "stack_" in blob:
        hints.append("stackoverflow.api")
    if "openai" in blob or "ollama" in blob:
        hints.append("llm.api")
    if "fetch_with_retries" in blob or "urlopen" in blob:
        hints.append("http.fetch")
    return _dedupe_preserve_order(hints)


def _tags_for_record(
    *,
    kind: str,
    qualified_name: str,
    path: str,
    reads_env: list[str],
    writes: list[str],
    network: bool,
) -> list[str]:
    tags: list[str] = []
    k = str(kind or "")
    if k:
        tags.append(k)
    qn = str(qualified_name or "")
    if qn.endswith(".main") or qn in {"core.cli.main"}:
        tags.append("entrypoint")
    if reads_env:
        tags.append("env")
    if writes:
        tags.append("io_write")
        if any("manifest.json" in w for w in writes):
            tags.append("manifest")
        if any("quality_report.md" in w for w in writes):
            tags.append("quality_report")
    if network:
        tags.append("network")
    # Repo-specific tags
    if path.replace("\\", "/").startswith("core/skills/"):
        tags.append("pipeline")
    if path.replace("\\", "/").startswith("core/sources/"):
        tags.append("source")
    return _dedupe_preserve_order(tags)


class _SymbolVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.imports: list[str] = []
        self.calls: list[str] = []
        self.reads_env: list[str] = []
        self.writes: list[str] = []
        self._name_to_outputs: dict[str, list[str]] = {}

    def visit_Import(self, node: ast.Import) -> Any:
        for n in node.names:
            name = str(getattr(n, "name", "") or "").strip()
            if name:
                self.imports.append(name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        mod = str(getattr(node, "module", "") or "").strip()
        if mod:
            self.imports.append(mod)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> Any:
        # Track simple "output path variables" like:
        #   manifest_path = Path(run_dir) / "manifest.json"
        # so later `write_json_atomic(manifest_path, ...)` can be attributed.
        outs = _string_literals_in(node.value)
        if outs:
            for t in node.targets:
                if isinstance(t, ast.Name):
                    name = str(t.id or "").strip()
                    if name:
                        self._name_to_outputs[name] = outs
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> Any:
        # Calls
        name = ""
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            try:
                name = ast.unparse(node.func)
            except Exception:
                name = node.func.attr
        if name:
            self.calls.append(name)

        # Env reads
        # os.getenv("X"), os.environ.get("X"), environ.get("X")
        try:
            func_text = ast.unparse(node.func)
        except Exception:
            func_text = ""

        if func_text.endswith("os.getenv") or func_text.endswith("getenv") or func_text.endswith("os.environ.get") or func_text.endswith("environ.get"):
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                self.reads_env.append(str(node.args[0].value))

        # Writes (best-effort): record output file targets for known writers.
        writer = name.lower()
        if writer.endswith("write_json_atomic") or writer.endswith("write_text_atomic") or writer == "open":
            if node.args:
                target = node.args[0]
                lits: list[str] = []
                if isinstance(target, ast.Name):
                    lits = list(self._name_to_outputs.get(str(target.id or "").strip(), []))
                if not lits:
                    lits = _string_literals_in(target)
                if lits:
                    self.writes.extend(lits)
                else:
                    try:
                        self.writes.append(ast.unparse(target))
                    except Exception:
                        pass
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> Any:
        # os.environ["X"]
        try:
            base = ast.unparse(node.value)
        except Exception:
            base = ""
        if base.endswith("os.environ") or base.endswith("environ"):
            key = None
            sl = node.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                key = sl.value
            if key:
                self.reads_env.append(str(key))
        self.generic_visit(node)


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for x in items:
        s = str(x or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _network_flag(imports: list[str], calls: list[str]) -> bool:
    blob = " ".join(imports + calls).lower()
    return any(
        k in blob
        for k in (
            "urllib",
            "requests",
            "httpx",
            "tavily",
            "openai",
            "fetch_with_retries",
            "urlopen",
            "github",
            "stack",
        )
    )


def analyze_python_source(*, rel_path: str, text: str) -> list[dict[str, Any]]:
    try:
        mod = ast.parse(text)
    except SyntaxError:
        return []

    module_name = _safe_rel_module_name(rel_path)
    v = _SymbolVisitor()
    v.visit(mod)
    imports = _dedupe_preserve_order(v.imports)
    calls = _dedupe_preserve_order(v.calls)
    reads_env = _dedupe_preserve_order(v.reads_env)
    writes = _normalize_write_targets(_dedupe_preserve_order(v.writes))
    network_hints = _network_hints(imports, calls)

    records: list[dict[str, Any]] = []

    records.append(
        {
            "path": rel_path,
            "language": "python",
            "start_line": 1,
            "end_line": int(text.count("\n") + 1),
            "kind": "module",
            "qualified_name": module_name,
            "signature": "",
            "summary_5_10_lines": _summary_lines_for_symbol(kind="module", qualified_name=module_name, doc=ast.get_docstring(mod) or "", imports=imports, calls=calls),
            "imports": imports,
            "calls": calls,
            "reads_env": reads_env,
            "writes": writes,
            "network": _network_flag(imports, calls),
            "network_hints": network_hints,
            "tags": _tags_for_record(kind="module", qualified_name=module_name, path=rel_path, reads_env=reads_env, writes=writes, network=_network_flag(imports, calls)),
        }
    )

    class_stack: list[str] = []

    def handle_func(node: ast.FunctionDef | ast.AsyncFunctionDef, *, kind: str) -> None:
        qn = ".".join([module_name, *class_stack, node.name])
        doc = ast.get_docstring(node) or ""
        local_v = _SymbolVisitor()
        local_v.visit(node)
        imports2 = []  # local imports are rare; keep module imports only.
        calls2 = _dedupe_preserve_order(local_v.calls)
        reads2 = _dedupe_preserve_order(local_v.reads_env)
        writes2 = _normalize_write_targets(_dedupe_preserve_order(local_v.writes))
        net2 = _network_flag(imports, calls2)
        records.append(
            {
                "path": rel_path,
                "language": "python",
                "start_line": int(getattr(node, "lineno", 1) or 1),
                "end_line": int(getattr(node, "end_lineno", getattr(node, "lineno", 1) or 1) or 1),
                "kind": kind,
                "qualified_name": qn,
                "signature": f"{node.name}{_signature_from_args(node)}",
                "summary_5_10_lines": _summary_lines_for_symbol(kind=kind, qualified_name=qn, doc=doc, imports=imports2, calls=calls2),
                "imports": [],
                "calls": calls2,
                "reads_env": reads2,
                "writes": writes2,
                "network": net2,
                "network_hints": _network_hints(imports, calls2),
                "tags": _tags_for_record(kind=kind, qualified_name=qn, path=rel_path, reads_env=reads2, writes=writes2, network=net2),
            }
        )

    class _Walk(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef) -> Any:
            qn = ".".join([module_name, *class_stack, node.name])
            doc = ast.get_docstring(node) or ""
            local_v = _SymbolVisitor()
            local_v.visit(node)
            calls2 = _dedupe_preserve_order(local_v.calls)
            reads2 = _dedupe_preserve_order(local_v.reads_env)
            writes2 = _normalize_write_targets(_dedupe_preserve_order(local_v.writes))
            net2 = _network_flag(imports, calls2)
            records.append(
                {
                    "path": rel_path,
                    "language": "python",
                    "start_line": int(getattr(node, "lineno", 1) or 1),
                    "end_line": int(getattr(node, "end_lineno", getattr(node, "lineno", 1) or 1) or 1),
                    "kind": "class",
                    "qualified_name": qn,
                    "signature": node.name,
                    "summary_5_10_lines": _summary_lines_for_symbol(kind="class", qualified_name=qn, doc=doc, imports=[], calls=calls2),
                    "imports": [],
                    "calls": calls2,
                    "reads_env": reads2,
                    "writes": writes2,
                    "network": net2,
                    "network_hints": _network_hints(imports, calls2),
                    "tags": _tags_for_record(kind="class", qualified_name=qn, path=rel_path, reads_env=reads2, writes=writes2, network=net2),
                }
            )

            class_stack.append(node.name)
            for child in node.body:
                self.visit(child)
            class_stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
            handle_func(node, kind=("method" if class_stack else "function"))

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
            handle_func(node, kind=("method" if class_stack else "function"))

    _Walk().visit(mod)
    return records


def _module_record_for_unparsed_file(*, rel_path: str, text_line_count: int = 1) -> dict[str, Any]:
    module_name = _safe_rel_module_name(rel_path)
    return {
        "path": rel_path,
        "language": detect_language(rel_path),
        "start_line": 1,
        "end_line": max(1, int(text_line_count or 1)),
        "kind": "module",
        "qualified_name": module_name,
        "signature": "",
        "summary_5_10_lines": [f"Module {module_name} (structure-only; skipped deep parse)."],
        "imports": [],
        "calls": [],
        "reads_env": [],
        "writes": [],
        "network": False,
        "network_hints": [],
        "tags": _tags_for_record(kind="module", qualified_name=module_name, path=rel_path, reads_env=[], writes=[], network=False),
        "analysis": "structure_only",
    }


def analyze_regex_source(*, rel_path: str, text: str, language: str) -> list[dict[str, Any]]:
    """
    Multi-language, dependency-free symbol extraction for non-Python source files.
    This is conservative and intended for discovery + evidence pointers, not correctness.
    """
    lang = str(language or "").strip().lower()
    module_name = _safe_rel_module_name(rel_path)
    lines = str(text or "").replace("\r\n", "\n").split("\n")
    line_count = len(lines) if lines else 1

    records: list[dict[str, Any]] = []
    records.append(
        {
            "path": rel_path,
            "language": lang,
            "start_line": 1,
            "end_line": int(max(1, line_count)),
            "kind": "module",
            "qualified_name": module_name,
            "signature": "",
            "summary_5_10_lines": [f"Module {module_name} ({lang}; regex-indexed; structure-only imports/calls)."],
            "imports": [],
            "calls": [],
            "reads_env": [],
            "writes": [],
            "network": False,
            "network_hints": [],
            "tags": _tags_for_record(kind="module", qualified_name=module_name, path=rel_path, reads_env=[], writes=[], network=False),
            "analysis": "regex",
        }
    )

    for kind, name, ln in extract_regex_symbols(text=text, language=lang):
        qn = ".".join([module_name, str(name)])
        records.append(
            {
                "path": rel_path,
                "language": lang,
                "start_line": int(ln),
                "end_line": int(ln),
                "kind": str(kind),
                "qualified_name": qn,
                "signature": str(name),
                "summary_5_10_lines": [f"{kind.capitalize()} {name} ({lang}; regex-extracted)."],
                "imports": [],
                "calls": [],
                "reads_env": [],
                "writes": [],
                "network": False,
                "network_hints": [],
                "tags": _tags_for_record(kind=str(kind), qualified_name=qn, path=rel_path, reads_env=[], writes=[], network=False),
                "analysis": "regex",
            }
        )

    return records


def write_symbol_index_jsonl(*, repo_root: str | Path, files: list[RepoFile], out_path: str | Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    # Optional incremental mode: reuse previous records for unchanged paths.
    prev_index_path = out_file if out_file.exists() else None
    prev_records_by_path: dict[str, list[dict[str, Any]]] = {}
    if prev_index_path and prev_index_path.exists():
        try:
            for rec in load_symbol_index_jsonl(prev_index_path):
                p = str(rec.get("path") or "").strip()
                if not p:
                    continue
                prev_records_by_path.setdefault(p, []).append(rec)
        except Exception:
            prev_records_by_path = {}

    # When present, `LANGSKILLS_REPO_INDEX_CHANGED` is a newline-separated list of changed rel paths.
    changed_env = str(os.environ.get("LANGSKILLS_REPO_INDEX_CHANGED") or "").strip()
    changed_paths: set[str] | None = None
    if changed_env:
        changed_paths = {ln.strip() for ln in changed_env.splitlines() if ln.strip()}

    big_raw = str(os.environ.get("LANGSKILLS_REPO_INDEX_BIG_FILE_BYTES") or "").strip()
    try:
        big_file_bytes = int(big_raw) if big_raw else int(DEFAULT_BIG_FILE_BYTES)
    except Exception:
        big_file_bytes = int(DEFAULT_BIG_FILE_BYTES)

    count_files = 0
    count_records = 0
    env_hits: set[str] = set()

    with out_file.open("w", encoding="utf-8") as f:
        for rf in files:
            lang = detect_language(rf.rel_path)
            if changed_paths is not None and rf.rel_path not in changed_paths and rf.rel_path in prev_records_by_path:
                # Reuse previous records for this file.
                for r in prev_records_by_path[rf.rel_path]:
                    for k in r.get("reads_env") or []:
                        env_hits.add(str(k))
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                    count_records += 1
                continue

            # Large/binary safety: keep a structure-only module record.
            if int(rf.size_bytes or 0) > int(big_file_bytes) or is_binary_file(rf.abs_path):
                count_files += 1
                rec = _module_record_for_unparsed_file(rel_path=rf.rel_path)
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                count_records += 1
                continue

            try:
                text = rf.abs_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                try:
                    text = rf.abs_path.read_text(encoding="utf-8-sig")
                except Exception:
                    count_files += 1
                    rec = _module_record_for_unparsed_file(rel_path=rf.rel_path)
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    count_records += 1
                    continue
            except Exception:
                continue

            if lang == "python":
                recs = analyze_python_source(rel_path=rf.rel_path, text=text)
            elif lang in {"javascript", "typescript", "go", "rust", "java"}:
                recs = analyze_regex_source(rel_path=rf.rel_path, text=text, language=lang)
            else:
                recs = [
                    {
                        "path": rf.rel_path,
                        "language": lang,
                        "start_line": 1,
                        "end_line": int(text.count("\n") + 1),
                        "kind": "module",
                        "qualified_name": _safe_rel_module_name(rf.rel_path),
                        "signature": "",
                        "summary_5_10_lines": [f"Module {_safe_rel_module_name(rf.rel_path)} ({lang}; structure-only)."],
                        "imports": [],
                        "calls": [],
                        "reads_env": [],
                        "writes": [],
                        "network": False,
                        "network_hints": [],
                        "tags": _tags_for_record(kind="module", qualified_name=_safe_rel_module_name(rf.rel_path), path=rf.rel_path, reads_env=[], writes=[], network=False),
                        "analysis": "structure_only",
                    }
                ]
            if not recs:
                continue
            count_files += 1
            for r in recs:
                for k in r.get("reads_env") or []:
                    env_hits.add(str(k))
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                count_records += 1

    return {
        "files_analyzed": count_files,
        "records_written": count_records,
        "env_keys_detected": sorted(env_hits),
        "output": out_file.resolve().as_posix(),
        "repo_root": root.as_posix(),
    }


def load_symbol_index_jsonl(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out
