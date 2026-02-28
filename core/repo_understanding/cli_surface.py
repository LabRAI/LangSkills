from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CliArg:
    """
    Best-effort extracted CLI argument metadata from argparse construction.
    """

    flags: list[str]
    dest: str
    action: str
    default: str
    type_name: str
    defined_at_line: int


@dataclass(frozen=True)
class CliCommand:
    name: str
    help: str
    defined_at_line: int
    handler_qualified_name: str
    handler_defined_at_line: int
    args: list[CliArg]


def _resolve_import_from(*, base_pkg: str, module: str | None, level: int) -> str:
    """
    Resolve `ast.ImportFrom` into a fully-qualified module name.

    `ast.ImportFrom` represents relative imports via `level` (number of leading dots) and `module`
    WITHOUT leading dots.
    """
    mod = str(module or "").strip()
    lvl = int(level or 0)
    if lvl <= 0:
        return mod

    base_parts = [p for p in str(base_pkg or "").split(".") if p]
    # level=1 means "from .<module>" (current package). level=2 means parent, etc.
    drop = max(0, lvl - 1)
    if drop:
        base_parts = base_parts[: max(0, len(base_parts) - drop)]
    prefix = ".".join(base_parts)
    if not prefix:
        return mod
    return f"{prefix}.{mod}" if mod else prefix


def _const_str(node: ast.AST | None) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return str(node.value)
    return ""


def _call_attr_name(node: ast.AST) -> tuple[str, str]:
    """
    Return (receiver_name, attr) for expressions like `p_capture.add_argument`.
    """
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return (str(node.value.id), str(node.attr))
    return ("", "")


def extract_cli_surface(*, cli_py_path: str | Path, base_pkg: str = "langskills") -> list[CliCommand]:
    """
    Extract CLI commands (subcommands) and their handler mapping from `langskills/cli.py`.

    This is conservative and designed to stay stable across minor refactors:
    - Detects `p_x = sub.add_parser("cmd", help=...)`
    - Collects `p_x.add_argument(...)` calls
    - Resolves handler by parsing `if ns.cmd == "cmd": from .mod import fn as alias; return alias(...)`
    """
    path = Path(cli_py_path)
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)

    # cmd -> parser var name + help + line
    cmd_by_parser_var: dict[str, dict[str, Any]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        recv, attr = _call_attr_name(node.value.func)
        if attr != "add_parser":
            continue
        if not node.value.args:
            continue
        cmd = _const_str(node.value.args[0]).strip()
        if not cmd:
            continue
        help_text = ""
        for kw in node.value.keywords or []:
            if kw.arg == "help":
                help_text = _const_str(kw.value).strip()
        for t in node.targets:
            if isinstance(t, ast.Name):
                cmd_by_parser_var[t.id] = {"cmd": cmd, "help": help_text, "line": int(getattr(node, "lineno", 1) or 1)}

    # parser var -> args
    args_by_cmd: dict[str, list[CliArg]] = {v["cmd"]: [] for v in cmd_by_parser_var.values()}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        recv, attr = _call_attr_name(node.func)
        if attr != "add_argument" or recv not in cmd_by_parser_var:
            continue
        cmd = str(cmd_by_parser_var[recv]["cmd"])

        flags = []
        for a in node.args or []:
            s = _const_str(a).strip()
            if not s:
                continue
            flags.append(s)

        dest = ""
        action = ""
        default = ""
        type_name = ""
        for kw in node.keywords or []:
            if kw.arg == "dest":
                dest = _const_str(kw.value).strip()
            if kw.arg == "action":
                action = _const_str(kw.value).strip()
            if kw.arg == "default":
                default = str(getattr(kw.value, "value", "")) if isinstance(kw.value, ast.Constant) else ""
            if kw.arg == "type":
                try:
                    type_name = ast.unparse(kw.value)
                except Exception:
                    type_name = ""

        args_by_cmd.setdefault(cmd, []).append(
            CliArg(
                flags=flags,
                dest=dest,
                action=action,
                default=default,
                type_name=type_name,
                defined_at_line=int(getattr(node, "lineno", 1) or 1),
            )
        )

    # cmd -> handler
    handler_by_cmd: dict[str, tuple[str, int]] = {}

    def _is_ns_cmd_eq(test: ast.AST) -> str:
        if not isinstance(test, ast.Compare):
            return ""
        if not isinstance(test.left, ast.Attribute):
            return ""
        if not (isinstance(test.left.value, ast.Name) and test.left.value.id == "ns" and test.left.attr == "cmd"):
            return ""
        if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
            return ""
        if len(test.comparators) != 1:
            return ""
        return _const_str(test.comparators[0]).strip()

    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        cmd = _is_ns_cmd_eq(node.test)
        if not cmd:
            continue

        imports: dict[str, tuple[str, str, int]] = {}
        for st in node.body:
            if isinstance(st, ast.ImportFrom):
                mod = _resolve_import_from(base_pkg=base_pkg, module=st.module, level=int(getattr(st, "level", 0) or 0))
                for alias in st.names or []:
                    asname = str(alias.asname or alias.name or "").strip()
                    name = str(alias.name or "").strip()
                    if asname and mod and name:
                        imports[asname] = (mod, name, int(getattr(st, "lineno", 1) or 1))

        # Pick the "main" handler call inside the cmd block:
        # - Often `return handler_main([...])`
        # - Sometimes `out = handler(...); ... return 0`
        tokens = [t for t in re.split(r"[^a-z0-9]+", cmd.lower()) if t]
        candidates: list[tuple[int, int, int, str]] = []
        body_mod = ast.Module(body=node.body, type_ignores=[])
        for sub in ast.walk(body_mod):
            if not isinstance(sub, ast.Call) or not isinstance(sub.func, ast.Name):
                continue
            alias = str(sub.func.id or "").strip()
            if alias not in imports:
                continue
            mod, name, import_ln = imports[alias]
            qn = f"{mod}.{name}"
            match = sum(1 for t in tokens if t and t in qn.lower())
            call_ln = int(getattr(sub, "lineno", 1) or 1)
            candidates.append((match, call_ln, int(import_ln or 1), qn))

        if candidates:
            candidates.sort(key=lambda x: (-x[0], x[1], x[2], x[3]))
            best = candidates[0]
            handler_by_cmd[cmd] = (best[3], best[2])

    commands: list[CliCommand] = []
    for parser_var, meta in cmd_by_parser_var.items():
        cmd = str(meta["cmd"])
        help_text = str(meta.get("help") or "")
        line = int(meta.get("line") or 1)
        handler, handler_line = handler_by_cmd.get(cmd, ("", 0))
        commands.append(
            CliCommand(
                name=cmd,
                help=help_text,
                defined_at_line=line,
                handler_qualified_name=str(handler or ""),
                handler_defined_at_line=int(handler_line or 0),
                args=args_by_cmd.get(cmd, []),
            )
        )

    commands.sort(key=lambda c: c.name)
    return commands
