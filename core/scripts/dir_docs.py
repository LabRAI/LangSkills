from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..utils.fs import write_text_atomic
from ..utils.time import utc_now_iso_z


_MARKER_ID = "langskills-dir-docs"
_BEGIN = f"<!-- AUTO-GENERATED: BEGIN {_MARKER_ID} -->"
_END = f"<!-- AUTO-GENERATED: END {_MARKER_ID} -->"


@dataclass(frozen=True)
class FunctionInfo:
    name: str
    signature: str
    doc: str


@dataclass(frozen=True)
class ClassInfo:
    name: str
    doc: str
    methods: list[FunctionInfo]


@dataclass(frozen=True)
class FileInfo:
    rel_path: str
    module_doc: str
    functions: list[FunctionInfo]
    classes: list[ClassInfo]
    parse_error: str = ""


def _first_line(s: str) -> str:
    t = str(s or "").strip()
    if not t:
        return ""
    return t.splitlines()[0].strip()


def _format_annotation(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node).strip()
    except Exception:
        return ""


def _format_args(args: ast.arguments) -> str:
    parts: list[str] = []

    def fmt_arg(a: ast.arg) -> str:
        ann = _format_annotation(a.annotation)
        return f"{a.arg}: {ann}" if ann else a.arg

    posonly = [fmt_arg(a) for a in getattr(args, "posonlyargs", []) or []]
    if posonly:
        parts.extend(posonly)
        parts.append("/")

    parts.extend(fmt_arg(a) for a in (args.args or []))

    if args.vararg:
        parts.append("*" + fmt_arg(args.vararg))
    elif args.kwonlyargs:
        parts.append("*")

    parts.extend(fmt_arg(a) for a in (args.kwonlyargs or []))

    if args.kwarg:
        parts.append("**" + fmt_arg(args.kwarg))

    return ", ".join([p for p in parts if p])


def _format_signature(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = _format_args(fn.args)
    ret = _format_annotation(getattr(fn, "returns", None))
    sig = f"({args})"
    if ret:
        sig = f"{sig} -> {ret}"
    return sig


def _function_info(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionInfo:
    name = str(getattr(fn, "name", "") or "").strip()
    sig = _format_signature(fn)
    doc = _first_line(ast.get_docstring(fn) or "")
    return FunctionInfo(name=name, signature=sig, doc=doc)


def _class_info(cls: ast.ClassDef) -> ClassInfo:
    name = str(getattr(cls, "name", "") or "").strip()
    doc = _first_line(ast.get_docstring(cls) or "")
    methods: list[FunctionInfo] = []
    for item in cls.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.append(_function_info(item))
    return ClassInfo(name=name, doc=doc, methods=methods)


def _parse_python_file(path: Path, *, repo_root: Path) -> FileInfo:
    rel = path.resolve().relative_to(repo_root).as_posix()
    try:
        src = path.read_text(encoding="utf-8")
    except Exception:
        src = path.read_text(encoding="utf-8", errors="replace")

    try:
        mod = ast.parse(src, filename=rel)
    except Exception as e:
        return FileInfo(rel_path=rel, module_doc="", functions=[], classes=[], parse_error=f"{type(e).__name__}: {e}")

    module_doc = _first_line(ast.get_docstring(mod) or "")
    functions: list[FunctionInfo] = []
    classes: list[ClassInfo] = []

    for node in mod.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(_function_info(node))
        elif isinstance(node, ast.ClassDef):
            classes.append(_class_info(node))

    return FileInfo(rel_path=rel, module_doc=module_doc, functions=functions, classes=classes)


def _render_dir_block(*, dir_path: Path, repo_root: Path, files: list[FileInfo]) -> str:
    rel_dir = dir_path.resolve().relative_to(repo_root).as_posix()
    py_files = [f for f in files if f.rel_path.endswith(".py")]

    total_funcs = sum(len(f.functions) for f in py_files)
    total_classes = sum(len(f.classes) for f in py_files)
    total_methods = sum(sum(len(c.methods) for c in f.classes) for f in py_files)

    heavy: list[tuple[str, int]] = []
    for f in py_files:
        for c in f.classes:
            heavy.append((f"{Path(f.rel_path).name}:{c.name}", len(c.methods)))
    heavy = sorted(heavy, key=lambda x: x[1], reverse=True)
    heavy = [x for x in heavy if x[1] >= 15][:10]

    lines: list[str] = []
    lines.append("## Auto-generated\n")
    lines.append(f"- generated_at: `{utc_now_iso_z()}`")
    lines.append(f"- dir: `{rel_dir}`")
    lines.append(f"- python_files: `{len(py_files)}`")
    lines.append(f"- top_level_functions: `{total_funcs}`")
    lines.append(f"- classes: `{total_classes}`")
    lines.append(f"- class_methods: `{total_methods}`\n")

    if heavy:
        lines.append("### Refactor hotspots (classes with many methods)\n")
        for key, n in heavy:
            lines.append(f"- `{key}`: `{n}` methods")
        lines.append("")

    lines.append("### File inventory\n")
    for f in py_files:
        file_name = Path(f.rel_path).name
        lines.append(f"#### `{file_name}`\n")
        if f.parse_error:
            lines.append(f"- parse_error: `{f.parse_error}`\n")
            continue
        if f.module_doc:
            lines.append(f"- module: {f.module_doc}")
        else:
            lines.append("- module: (no docstring)")

        if f.functions:
            lines.append(f"- functions: `{len(f.functions)}`")
            for fn in f.functions:
                doc = f" — {fn.doc}" if fn.doc else ""
                lines.append(f"  - `{fn.name}{fn.signature}`{doc}")
        else:
            lines.append("- functions: `0`")

        if f.classes:
            lines.append(f"- classes: `{len(f.classes)}`")
            for cls in f.classes:
                cdoc = f" — {cls.doc}" if cls.doc else ""
                lines.append(f"  - `class {cls.name}`{cdoc}")
                if cls.methods:
                    for m in cls.methods:
                        mdoc = f" — {m.doc}" if m.doc else ""
                        lines.append(f"    - `{m.name}{m.signature}`{mdoc}")
                else:
                    lines.append("    - (no methods)")
        else:
            lines.append("- classes: `0`")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _update_text_with_block(existing: str, *, block: str, title: str) -> str:
    text = str(existing or "")
    if _BEGIN in text and _END in text:
        pre, rest = text.split(_BEGIN, 1)
        _old, post = rest.split(_END, 1)
        return f"{pre}{_BEGIN}\n{block}{_END}{post}".rstrip() + "\n"

    if text.strip():
        sep = "\n\n" if not text.endswith("\n") else "\n"
        return f"{text.rstrip()}{sep}{_BEGIN}\n{block}{_END}\n"

    # New file.
    clean_title = str(title or "Directory").strip() or "Directory"
    header = (
        f"# {clean_title} Directory Docs\n\n"
        "> This file contains an auto-generated index of Python code in this directory (classes/functions).\n"
        "> You can add manual notes above this block.\n\n"
    )
    return f"{header}{_BEGIN}\n{block}{_END}\n"


def _should_skip_dir(path: Path) -> bool:
    parts = [p.lower() for p in path.parts]
    if "__pycache__" in parts:
        return True
    if ".git" in parts:
        return True
    if any(p == "node_modules" for p in parts):
        return True
    if any(p in {".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache"} for p in parts):
        return True
    if any(p == ".venv" or p.startswith(".venv") or p == "venv" for p in parts):
        return True
    return False


def run_dir_docs(
    *,
    repo_root: str | Path,
    roots: Iterable[str | Path],
    filename: str = "DIR_DOCS.md",
    dry_run: bool = False,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    root_paths: list[Path] = []
    for r in roots:
        p = Path(str(r))
        if not p.is_absolute():
            p = (repo_root / p).resolve()
        if p.exists() and p.is_dir():
            root_paths.append(p)

    dirs: set[Path] = set()
    for root in root_paths:
        for py in root.rglob("*.py"):
            if not py.is_file():
                continue
            d = py.parent
            if _should_skip_dir(d):
                continue
            dirs.add(d)

    written: list[str] = []
    parsed_files = 0
    for d in sorted(dirs, key=lambda x: x.as_posix()):
        rel_dir = d.resolve().relative_to(repo_root).as_posix()
        py_files = sorted([p for p in d.glob("*.py") if p.is_file()], key=lambda x: x.name)
        infos: list[FileInfo] = []
        for p in py_files:
            parsed_files += 1
            infos.append(_parse_python_file(p, repo_root=repo_root))
        block = _render_dir_block(dir_path=d, repo_root=repo_root, files=infos)
        out_path = d / filename
        if dry_run:
            written.append(out_path.resolve().relative_to(repo_root).as_posix())
            continue
        existing = ""
        if out_path.exists():
            try:
                existing = out_path.read_text(encoding="utf-8")
            except Exception:
                existing = out_path.read_text(encoding="utf-8", errors="replace")
        updated = _update_text_with_block(existing, block=block, title=rel_dir)
        write_text_atomic(out_path, updated)
        written.append(out_path.resolve().relative_to(repo_root).as_posix())

    return {
        "ok": True,
        "repo_root": repo_root.as_posix(),
        "roots": [p.relative_to(repo_root).as_posix() for p in root_paths],
        "dirs": len(dirs),
        "parsed_files": parsed_files,
        "written": written,
        "dry_run": bool(dry_run),
        "filename": filename,
    }
