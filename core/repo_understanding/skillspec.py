from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cli_surface import CliArg, CliCommand, extract_cli_surface
from ..utils.hashing import sha256_hex, slugify
from ..utils.time import utc_now_iso_z


def _find_symbol(symbols: list[dict[str, Any]], qualified_name: str) -> dict[str, Any] | None:
    q = str(qualified_name or "").strip()
    if not q:
        return None
    for s in symbols:
        if str(s.get("qualified_name") or "").strip() == q:
            return s
    return None


def _first_source_context(*, symbols: list[dict[str, Any]]) -> tuple[str, str, str]:
    """
    Best-effort: detect whether the index came from a remote GitHub snapshot.
    Returns (source_type, source_url_base, source_fetched_at).
    """
    for s in symbols:
        repo_url = str(s.get("repo_url") or "").strip()
        git_commit = str(s.get("git_commit") or "").strip()
        fetched_at = str(s.get("source_fetched_at") or "").strip()
        if repo_url:
            base = f"{repo_url}/tree/{git_commit}" if git_commit else repo_url
            return "github_repo", base, fetched_at
    return "repo", "", ""


def _evidence_entry(*, rec: dict[str, Any], qualified_name: str, line: int | None = None) -> dict[str, Any]:
    ln = int(line or 0) or int(rec.get("start_line") or 1) or 1
    ev: dict[str, Any] = {
        "path": rec.get("path"),
        "line": ln,
        "qualified_name": str(qualified_name or "").strip(),
    }
    for k in ["source_type", "repo_url", "git_commit", "ref", "blob_sha"]:
        v = rec.get(k)
        if str(v or "").strip():
            ev[k] = v
    repo_url = str(rec.get("repo_url") or "").strip()
    git_commit = str(rec.get("git_commit") or "").strip()
    path = str(rec.get("path") or "").lstrip("/")
    ln = ln
    if repo_url and git_commit and path:
        ev["url"] = f"{repo_url}/blob/{git_commit}/{path}#L{ln}"
    return ev


def _yaml_escape(s: str) -> str:
    # Minimal safe scalar encoding.
    t = str(s or "")
    if not t:
        return "''"
    if re.search(r"[:#\n\r\t]", t) or t.strip() != t:
        return repr(t)
    return t


def dump_yaml(obj: Any, *, indent: int = 0) -> str:
    sp = "  " * indent
    if obj is None:
        return f"{sp}null\n"
    if isinstance(obj, bool):
        return f"{sp}{'true' if obj else 'false'}\n"
    if isinstance(obj, (int, float)):
        return f"{sp}{obj}\n"
    if isinstance(obj, str):
        return f"{sp}{_yaml_escape(obj)}\n"
    if isinstance(obj, list):
        if not obj:
            return f"{sp}[]\n"
        out = ""
        for it in obj:
            if isinstance(it, (dict, list)):
                out += f"{sp}-\n{dump_yaml(it, indent=indent + 1)}"
            else:
                out += f"{sp}- {dump_yaml(it, indent=0).strip()}\n"
        return out
    if isinstance(obj, dict):
        if not obj:
            return f"{sp}{{}}\n"
        out = ""
        for k, v in obj.items():
            key = str(k)
            if isinstance(v, (dict, list)):
                out += f"{sp}{key}:\n{dump_yaml(v, indent=indent + 1)}"
            else:
                out += f"{sp}{key}: {dump_yaml(v, indent=0).strip()}\n"
        return out
    return f"{sp}{_yaml_escape(str(obj))}\n"


def _read_repo_docs_text(repo_root: Path) -> str:
    parts: list[str] = []
    for p in [repo_root / "README.md", repo_root / "docs" / "verify_log.md", repo_root / "docs" / "repo_inventory.md", repo_root / "plan_githubagent.md"]:
        if p.exists():
            try:
                parts.append(p.read_text(encoding="utf-8"))
            except Exception:
                continue
    return "\n\n".join(parts)


def _score_cli_command(*, cmd: CliCommand, handler_rec: dict[str, Any] | None, docs_text: str) -> tuple[int, list[str]]:
    score = 0
    signals: list[str] = []

    score += 40
    signals.append("cli:+40")

    if handler_rec:
        writes = handler_rec.get("writes") if isinstance(handler_rec.get("writes"), list) else []
        if writes:
            score += 25
            signals.append("writes:+25")
        if bool(handler_rec.get("network")):
            score += 15
            signals.append("network:+15")
        tags = handler_rec.get("tags") if isinstance(handler_rec.get("tags"), list) else []
        if "entrypoint" in tags:
            score += 10
            signals.append("entrypoint:+10")

    t = str(docs_text or "").lower()
    if cmd.name and cmd.name.lower() in t:
        score += 10
        signals.append("docs:+10")

    return score, signals


def _arg_inputs(args: list[CliArg]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for a in args:
        out.append(
            {
                "flags": list(a.flags),
                "dest": str(a.dest or ""),
                "action": str(a.action or ""),
                "default": str(a.default or ""),
                "type": str(a.type_name or ""),
                "defined_at_line": int(a.defined_at_line or 0),
            }
        )
    return out


def validate_skillspec(spec: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for k in ["id", "name", "goal", "slug", "source_type", "source_url"]:
        if not str(spec.get(k) or "").strip():
            issues.append(f"missing {k}")
    if not isinstance(spec.get("entrypoints"), list) or not spec.get("entrypoints"):
        issues.append("missing entrypoints")
    if not isinstance(spec.get("steps"), list) or not spec.get("steps"):
        issues.append("missing steps")
    ev = spec.get("evidence")
    if not isinstance(ev, list) or not ev:
        issues.append("missing evidence")
    return issues


def build_cli_skillspecs(
    *, repo_root: str | Path, symbols: list[dict[str, Any]], top_n: int = 12, index_path: str = "captures/symbol_index.jsonl"
) -> list[dict[str, Any]]:
    repo_root = Path(repo_root).resolve()
    now = utc_now_iso_z()

    cli_path = repo_root / "core" / "cli.py"
    if not cli_path.exists():
        return []
    cli_cmds = extract_cli_surface(cli_py_path=cli_path)
    docs_text = _read_repo_docs_text(repo_root)
    source_type, source_url_base, source_fetched_at = _first_source_context(symbols=symbols)

    scored: list[tuple[int, str, CliCommand, dict[str, Any] | None, list[str]]] = []
    for c in cli_cmds:
        handler_rec = _find_symbol(symbols, c.handler_qualified_name) if c.handler_qualified_name else None
        sc, signals = _score_cli_command(cmd=c, handler_rec=handler_rec, docs_text=docs_text)
        scored.append((sc, c.name, c, handler_rec, signals))

    scored.sort(key=lambda x: (-x[0], x[1]))
    picked = scored[: max(1, int(top_n or 1))]

    out: list[dict[str, Any]] = []
    for sc, _, c, handler_rec, signals in picked:
        spec_id = f"repo/cli/{c.name}"
        slug = slugify(c.name, 48)

        evidence: list[dict[str, Any]] = [
            {"path": "core/cli.py", "line": int(c.defined_at_line or 1), "qualified_name": "core.cli.main"},
        ]
        if c.handler_qualified_name and handler_rec:
            evidence.append(_evidence_entry(rec=handler_rec, qualified_name=c.handler_qualified_name))

        outputs: list[str] = ["Console output"]
        if handler_rec and isinstance(handler_rec.get("writes"), list):
            outputs.extend([str(x) for x in handler_rec.get("writes") if str(x or "").strip()])

        spec: dict[str, Any] = {
            "schema_version": 1,
            "id": spec_id,
            "name": f"langskills {c.name}",
            "goal": c.help.strip() or f"Run `langskills {c.name}`",
            "persona": "developer",
            "entrypoints": [f"./.venv/bin/python langskills_cli.py {c.name} --help"],
            "prerequisites": ["Python 3.10+", "Repo root available"],
            "inputs": _arg_inputs(c.args),
            "steps": [
                f"Run `./.venv/bin/python langskills_cli.py {c.name} --help` to review flags.",
                f"Run `./.venv/bin/python langskills_cli.py {c.name} ...` with the desired arguments.",
            ],
            "outputs": outputs,
            "failure_modes": [
                "Missing required env vars (provider credentials).",
                "Network failures when using remote sources/providers.",
            ],
            "observability": [
                "captures/run_index.jsonl (runbook)",
                "captures/run-*/manifest.json (capture)",
                "captures/run-*/quality_report.md (capture)",
            ],
            "evidence": evidence,
            "score": int(sc),
            "score_signals": signals,
            "generated_at": now,
            "slug": slug,
            "source_url": f"{source_url_base}#{spec_id}" if source_url_base else f"file://{repo_root.as_posix()}#{spec_id}",
            "source_fetched_at": source_fetched_at or now,
            "source_type": source_type,
        }

        issues = validate_skillspec(spec)
        if issues:
            spec["spec_issues"] = issues

        out.append(spec)

    return out


def build_workflow_skillspecs(
    *, repo_root: str | Path, symbols: list[dict[str, Any]], top_n: int = 12, index_path: str = "captures/symbol_index.jsonl"
) -> list[dict[str, Any]]:
    repo_root = Path(repo_root).resolve()
    now = utc_now_iso_z()
    source_type, source_url_base, source_fetched_at = _first_source_context(symbols=symbols)

    candidates: list[tuple[int, dict[str, Any], list[str]]] = []
    for r in symbols:
        if str(r.get("kind") or "") not in {"function", "method"}:
            continue
        tags = r.get("tags") if isinstance(r.get("tags"), list) else []
        if not (("io_write" in tags) or ("entrypoint" in tags) or bool(r.get("network"))):
            continue
        score = 0
        signals: list[str] = []
        if "entrypoint" in tags:
            score += 20
            signals.append("entrypoint:+20")
        if isinstance(r.get("writes"), list) and r.get("writes"):
            score += 25
            signals.append("writes:+25")
        if bool(r.get("network")):
            score += 15
            signals.append("network:+15")
        if str(r.get("path") or "").replace("\\", "/").startswith("core/skills/"):
            score += 10
            signals.append("pipeline:+10")
        candidates.append((score, r, signals))

    candidates.sort(key=lambda x: (-x[0], str(x[1].get("qualified_name") or "")))
    picked = [(r, sc, sig) for sc, r, sig in candidates[: max(1, int(top_n or 1))]]

    out: list[dict[str, Any]] = []
    for r, sc, signals in picked:
        qn = str(r.get("qualified_name") or "").strip()
        path = str(r.get("path") or "").strip()
        line = int(r.get("start_line") or 1)
        spec_id = f"repo/workflow/{qn}@{path}:{line}"
        slug = slugify(qn.split(".")[-1] or qn, 48)
        out.append(
            {
                "schema_version": 1,
                "id": spec_id,
                "name": f"Workflow: {qn}",
                "goal": (str((r.get("summary_5_10_lines") or [""])[0]) or "").strip() or f"Understand and exercise {qn}",
                "persona": "developer",
                "entrypoints": [f"./.venv/bin/python langskills_cli.py repo-query \"{qn}\" --json --index {index_path}"],
                "prerequisites": ["Repo root available"],
                "inputs": [],
                "steps": [
                    f"Locate `{qn}` at `{path}:{line}`.",
                    "Trace its callers/callees via `repo-query --json` context expansion.",
                    "Exercise the relevant CLI command(s) and inspect artifacts under `captures/`.",
                ],
                "outputs": [str(x) for x in (r.get("writes") or []) if str(x or "").strip()] or ["Console output"],
                "failure_modes": ["Misconfigured env vars", "Network failures (if applicable)"],
                "observability": ["captures/run_index.jsonl", "captures/run-*/manifest.json"],
                "evidence": [_evidence_entry(rec=r, qualified_name=qn)],
                "score": int(sc),
                "score_signals": signals,
                "generated_at": now,
                "slug": slug,
                "source_url": f"{source_url_base}#{spec_id}" if source_url_base else f"file://{repo_root.as_posix()}#{spec_id}",
                "source_fetched_at": source_fetched_at or now,
                "source_type": source_type,
            }
        )
    return out


def build_module_skillspecs(
    *, repo_root: str | Path, symbols: list[dict[str, Any]], top_n: int = 12, index_path: str = "captures/symbol_index.jsonl"
) -> list[dict[str, Any]]:
    repo_root = Path(repo_root).resolve()
    now = utc_now_iso_z()
    source_type, source_url_base, source_fetched_at = _first_source_context(symbols=symbols)

    candidates: list[tuple[int, dict[str, Any], list[str]]] = []
    for r in symbols:
        if str(r.get("kind") or "") != "module":
            continue
        score = 0
        signals: list[str] = []
        tags = r.get("tags") if isinstance(r.get("tags"), list) else []
        if bool(r.get("network")):
            score += 15
            signals.append("network:+15")
        if isinstance(r.get("reads_env"), list) and r.get("reads_env"):
            score += 10
            signals.append("env:+10")
        if isinstance(r.get("writes"), list) and r.get("writes"):
            score += 10
            signals.append("writes:+10")
        if "source" in tags:
            score += 10
            signals.append("source:+10")
        if "pipeline" in tags:
            score += 10
            signals.append("pipeline:+10")
        if score <= 0:
            continue
        candidates.append((score, r, signals))

    candidates.sort(key=lambda x: (-x[0], str(x[1].get("qualified_name") or "")))
    picked = [(r, sc, sig) for sc, r, sig in candidates[: max(1, int(top_n or 1))]]

    out: list[dict[str, Any]] = []
    for r, sc, signals in picked:
        qn = str(r.get("qualified_name") or "").strip()
        path = str(r.get("path") or "").strip()
        spec_id = f"repo/module/{qn}@{path}"
        slug = slugify(qn, 48)
        out.append(
            {
                "schema_version": 1,
                "id": spec_id,
                "name": f"Module: {qn}",
                "goal": (str((r.get("summary_5_10_lines") or [""])[0]) or "").strip() or f"Understand {qn}",
                "persona": "developer",
                "entrypoints": [f"./.venv/bin/python langskills_cli.py repo-query \"{qn}\" --json --index {index_path}"],
                "prerequisites": ["Repo root available"],
                "inputs": [],
                "steps": [
                    f"Open `{r.get('path')}:1` and review module responsibilities.",
                    "Use `repo-query` to locate key functions/classes and their evidence context.",
                ],
                "outputs": [],
                "failure_modes": [],
                "observability": [],
                "evidence": [_evidence_entry(rec=r, qualified_name=qn)],
                "score": int(sc),
                "score_signals": signals,
                "generated_at": now,
                "slug": slug,
                "source_url": f"{source_url_base}#{spec_id}" if source_url_base else f"file://{repo_root.as_posix()}#{spec_id}",
                "source_fetched_at": source_fetched_at or now,
                "source_type": source_type,
            }
        )
    return out


def build_troubleshooting_skillspecs(
    *, repo_root: str | Path, symbols: list[dict[str, Any]], top_n: int = 3, index_path: str = "captures/symbol_index.jsonl"
) -> list[dict[str, Any]]:
    repo_root = Path(repo_root).resolve()
    now = utc_now_iso_z()
    source_type, source_url_base, source_fetched_at = _first_source_context(symbols=symbols)
    if source_type == "github_repo":
        return []

    validate = _find_symbol(symbols, "core.scripts.validate_skills.validate_skills")
    capture = _find_symbol(symbols, "core.skills.generate.capture")

    evidence: list[dict[str, Any]] = []
    if validate:
        evidence.append(_evidence_entry(rec=validate, qualified_name="core.scripts.validate_skills.validate_skills"))
    if capture:
        evidence.append(_evidence_entry(rec=capture, qualified_name="core.skills.generate.capture"))

    spec = {
        "schema_version": 1,
        "id": "repo/troubleshooting/capture-manifest-missing",
        "name": "Troubleshoot: manifest missing after capture",
        "goal": "Diagnose why a capture run did not produce a complete manifest/package output and how to recover evidence for audit.",
        "persona": "operator",
        "entrypoints": ["./.venv/bin/python langskills_cli.py repo-runbook --mode smoke", "./.venv/bin/python langskills_cli.py validate --strict --package"],
        "prerequisites": ["Repo root available"],
        "inputs": [],
        "steps": [
            "Re-run with `PYTHONUNBUFFERED=1` and redirect stderr to a log file.",
            "Check `captures/run-*/manifest.json` and `captures/run-*/quality_report.md` exist for the latest run.",
            "If generation stopped early, inspect `captures/runbook_logs/*.log` and the run directory for partial artifacts.",
            "Run `validate --strict --package` to surface structural issues.",
        ],
        "outputs": ["captures/run-*/manifest.json", "captures/run-*/quality_report.md", "captures/runbook_logs/*.log"],
        "failure_modes": ["LLM/network timeouts", "filesystem permission issues"],
        "observability": ["captures/run_index.jsonl"],
        "evidence": evidence or [{"path": "core/skills/generate.py", "line": 645, "qualified_name": "core.skills.generate.capture"}],
        "score": 0,
        "score_signals": [],
        "generated_at": now,
        "slug": "capture-manifest-missing",
        "source_url": f"{source_url_base}#repo/troubleshooting/capture-manifest-missing" if source_url_base else f"file://{repo_root.as_posix()}#repo/troubleshooting/capture-manifest-missing",
        "source_fetched_at": source_fetched_at or now,
        "source_type": source_type,
    }

    return [spec][: max(1, int(top_n or 1))]


def build_skillspecs(
    *, repo_root: str | Path, symbols: list[dict[str, Any]], target: str, top_n: int, index_path: str = "captures/symbol_index.jsonl"
) -> list[dict[str, Any]]:
    t = str(target or "").strip().lower()
    if t == "cli":
        return build_cli_skillspecs(repo_root=repo_root, symbols=symbols, top_n=top_n, index_path=index_path)
    if t == "workflow":
        return build_workflow_skillspecs(repo_root=repo_root, symbols=symbols, top_n=top_n, index_path=index_path)
    if t == "module":
        return build_module_skillspecs(repo_root=repo_root, symbols=symbols, top_n=top_n, index_path=index_path)
    if t == "troubleshooting":
        return build_troubleshooting_skillspecs(repo_root=repo_root, symbols=symbols, top_n=min(3, int(top_n or 3)), index_path=index_path)
    return build_cli_skillspecs(repo_root=repo_root, symbols=symbols, top_n=top_n, index_path=index_path)


def build_skillspecs_from_llm_candidates(
    *,
    repo_root: str | Path,
    symbols: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    target: str,
    index_path: str = "captures/symbol_index.jsonl",
) -> list[dict[str, Any]]:
    repo_root = Path(repo_root).resolve()
    now = utc_now_iso_z()
    source_type, source_url_base, source_fetched_at = _first_source_context(symbols=symbols)

    def find_symbol_for_ev(ev: dict[str, Any]) -> dict[str, Any] | None:
        qn = str(ev.get("qualified_name") or "").strip()
        path = str(ev.get("path") or "").strip()
        line = int(ev.get("line") or 0)
        if qn:
            rec = _find_symbol(symbols, qn)
            if rec:
                return rec
        for r in symbols:
            if str(r.get("path") or "") != path:
                continue
            start = int(r.get("start_line") or 0)
            end = int(r.get("end_line") or 0)
            if end and start and start <= line <= end:
                return r
            if not end and start and abs(start - line) <= 12:
                return r
        return None

    specs: list[dict[str, Any]] = []
    for cand in candidates:
        qn = None
        evidence_rec = None
        evidence_items = cand.get("evidence") if isinstance(cand.get("evidence"), list) else []
        first_ev_line = 0
        if evidence_items:
            for ev in evidence_items:
                if not isinstance(ev, dict):
                    continue
                try:
                    first_ev_line = int(ev.get("line") or 0)
                except Exception:
                    first_ev_line = 0
                evidence_rec = find_symbol_for_ev(ev)
                if evidence_rec:
                    qn = evidence_rec.get("qualified_name")
                    break
        if not qn and evidence_items:
            qn = evidence_items[0].get("qualified_name")

        goal = str(cand.get("goal") or "").strip() or "not provided"
        name = str(cand.get("name") or qn or cand.get("id") or "Repo Skill").strip()
        slug = slugify(name, 48)
        entrypoints_in = cand.get("entrypoints") if isinstance(cand.get("entrypoints"), list) else []
        entrypoints = [str(x or "").strip() for x in entrypoints_in if str(x or "").strip()]
        steps_in = cand.get("steps") if isinstance(cand.get("steps"), list) else []
        steps = [str(x or "").strip() for x in steps_in if str(x or "").strip()]

        if not entrypoints:
            raise RuntimeError(f"LLM candidate missing entrypoints: {cand.get('id') or name}")
        if not steps:
            raise RuntimeError(f"LLM candidate missing steps: {cand.get('id') or name}")

        if not evidence_items and evidence_rec:
            evidence_items = [_evidence_entry(rec=evidence_rec, qualified_name=qn or "")]

        out_evidence: list[dict[str, Any]] = []
        for ev in evidence_items:
            if not isinstance(ev, dict):
                continue
            rec = find_symbol_for_ev(ev)
            if not rec:
                continue
            try:
                ln = int(ev.get("line") or 0)
            except Exception:
                ln = 0
            out_evidence.append(
                _evidence_entry(
                    rec=rec,
                    qualified_name=str(ev.get("qualified_name") or rec.get("qualified_name") or ""),
                    line=ln or int(rec.get("start_line") or 1),
                )
            )
        if not out_evidence:
            raise RuntimeError(f"LLM candidate missing usable evidence: {cand.get('id') or name}")

        spec = {
            "schema_version": 1,
            "id": str(cand.get("id") or slug),
            "name": name,
            "goal": goal,
            "persona": "developer",
            "index_path": str(index_path or "captures/symbol_index.jsonl"),
            "entrypoints": entrypoints,
            "prerequisites": ["Repo root available"],
            "inputs": [],
            "steps": steps,
            "outputs": ["Console output"],
            "failure_modes": ["Misconfigured env vars", "Network failures (if applicable)"],
            "observability": ["captures/run_index.jsonl", "captures/run-*/manifest.json"],
            "evidence": out_evidence,
            "score": int(cand.get("priority_score") or 50),
            "score_signals": [f"llm:+{int(cand.get('priority_score') or 50)}"],
            "generated_at": now,
            "slug": slug,
            "source_url": f"{source_url_base}#{str(cand.get('id') or slug)}" if source_url_base else f"file://{repo_root.as_posix()}#{str(cand.get('id') or slug)}",
            "source_fetched_at": source_fetched_at or now,
            "source_type": source_type,
            "selection_source": "llm",
        }

        issues = validate_skillspec(spec)
        if issues:
            spec["spec_issues"] = issues
        specs.append(spec)

    return specs


def write_skillspecs(*, out_dir: str | Path, specs: list[dict[str, Any]]) -> list[str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for s in specs:
        sid = str(s.get("id") or "")
        slug = str(s.get("slug") or "").strip() or sha256_hex(sid)[:8]
        h = sha256_hex(sid)[:8]
        p = out_dir / f"{slug}-{h}.yaml"
        p.write_text(dump_yaml(s), encoding="utf-8")
        written.append(p.as_posix())
    return written
