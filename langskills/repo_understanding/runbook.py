from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .ingest import summarize_env_presence
from ..utils.git import get_git_commit
from ..utils.redact import redact_text


SENSITIVE_ENV_KEY_RE = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD)", flags=re.IGNORECASE)


def _redact_env(env: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in env.items():
        if SENSITIVE_ENV_KEY_RE.search(k):
            out[k] = "<redacted>"
        else:
            out[k] = v
    return out


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    timestamp: str
    command: str
    args: list[str]
    cwd: str
    git_commit: str
    exit_code: int
    duration_ms: int
    env_presence: dict[str, bool]
    env_redacted: list[str]
    log_path: str
    artifacts: dict[str, str]
    key_logs: list[str]

    def to_json(self) -> str:
        return json.dumps(
            {
                "run_id": self.run_id,
                "timestamp": self.timestamp,
                "command": self.command,
                "args": self.args,
                "cwd": self.cwd,
                "git_commit": self.git_commit,
                "exit_code": self.exit_code,
                "duration_ms": self.duration_ms,
                "env_presence": self.env_presence,
                "env_redacted": self.env_redacted,
                "log_path": self.log_path,
                "artifacts": self.artifacts,
                "key_logs": self.key_logs,
            },
            ensure_ascii=False,
        )


def _make_run_id(prefix: str) -> str:
    stamp = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{stamp}"


def run_one(
    *,
    cmd: list[str],
    cwd: Path,
    out_dir: Path,
    env: dict[str, str] | None = None,
    timeout_s: int = 600,
    run_id_prefix: str = "run",
    env_presence_keys: list[str] | None = None,
) -> RunRecord:
    out_dir.mkdir(parents=True, exist_ok=True)
    started = _dt.datetime.now(tz=_dt.timezone.utc)
    ts = started.isoformat(timespec="seconds").replace("+00:00", "Z")
    run_id = _make_run_id(run_id_prefix)

    git_commit = get_git_commit(cwd)

    full_env = dict(os.environ)
    if env:
        full_env.update({k: str(v) for k, v in env.items()})

    p = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=full_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=max(1, int(timeout_s or 1)),
        check=False,
    )
    ended = _dt.datetime.now(tz=_dt.timezone.utc)
    duration_ms = int((ended - started).total_seconds() * 1000)

    redact_urls = str(os.environ.get("LANGSKILLS_REDACT_URLS") or "").strip() == "1"
    log_text = redact_text(p.stdout or "", redact_urls=redact_urls)
    log_path = out_dir / f"{run_id}.log"
    log_path.write_text(log_text, encoding="utf-8")

    # Key logs: keep it short and useful.
    tail_lines = [ln.strip() for ln in log_text.splitlines() if ln.strip()][-12:]

    env_presence = summarize_env_presence(env_presence_keys or [])
    env_redacted = [f"{k}={'<present>' if v else '<absent>'}" for k, v in env_presence.items()]
    record = RunRecord(
        run_id=run_id,
        timestamp=ts,
        command=str(cmd[0] if cmd else ""),
        args=[str(x) for x in (cmd[1:] if len(cmd) > 1 else [])],
        cwd=str(cwd),
        git_commit=git_commit,
        exit_code=int(p.returncode),
        duration_ms=duration_ms,
        env_presence=env_presence,
        env_redacted=env_redacted,
        log_path=str(log_path),
        artifacts={},
        key_logs=tail_lines,
    )
    return record


def append_jsonl(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")


def run_golden_workflows(
    *,
    repo_root: str | Path,
    out_jsonl: str | Path,
    mode: str = "smoke",
    provider: str = "openai",
) -> list[RunRecord]:
    repo_root = Path(repo_root).resolve()
    # Load .env so env presence and downstream commands behave consistently.
    try:
        from ..env import load_dotenv

        load_dotenv(repo_root)
    except Exception:
        pass
    out_jsonl = Path(out_jsonl)
    if not out_jsonl.is_absolute():
        out_jsonl = (repo_root / out_jsonl).resolve()
    logs_dir = out_jsonl.parent / "runbook_logs"

    py = str(Path(repo_root) / ".venv" / "bin" / "python")
    if not Path(py).exists():
        py = "python3"

    env_presence_keys = [
        "LLM_PROVIDER",
        "OPENAI_BASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "TAVILY_API_KEY",
        "GITHUB_TOKEN",
    ]

    steps: list[tuple[str, list[str], dict[str, str], int]] = []
    steps.append(("self-check", [py, "langskills_cli.py", "self-check", "--skip-remote"], {}, 120))
    steps.append(("validate-library", [py, "langskills_cli.py", "validate", "--strict", "--package"], {}, 300))

    # Capture pipeline: always run with a real provider.
    if mode == "full":
        steps.append(
            (
                "capture-real",
                [py, "langskills_cli.py", "journalctl@3", "--domain", "linux", "--per-source", "3"],
                {"LLM_PROVIDER": str(provider)},
                1200,
            )
        )
    else:
        steps.append(
            (
                "capture-smoke",
                [py, "langskills_cli.py", "verify@2", "--domain", "devtools", "--per-source", "1"],
                {"LLM_PROVIDER": str(provider)},
                600,
            )
        )

    steps.append(("build-site", [py, "langskills_cli.py", "build-site"], {}, 300))
    steps.append(("auto-pr-dry", [py, "langskills_cli.py", "auto-pr"], {}, 300))

    records: list[RunRecord] = []
    for name, cmd, env, timeout_s in steps:
        rec0 = run_one(
            cmd=cmd,
            cwd=repo_root,
            out_dir=logs_dir,
            env=env,
            timeout_s=timeout_s,
            run_id_prefix=name,
            env_presence_keys=env_presence_keys,
        )
        artifacts = _infer_artifacts(repo_root=repo_root, step_name=name, record=rec0)
        rec = replace(rec0, artifacts=artifacts)
        append_jsonl(out_jsonl, rec.to_json())
        records.append(rec)

    # Append a human-readable summary for audit (best-effort).
    try:
        _append_verify_log(repo_root=repo_root, records=records, mode=str(mode))
    except Exception:
        pass

    return records


def _infer_artifacts(*, repo_root: Path, step_name: str, record: RunRecord) -> dict[str, str]:
    """
    Best-effort extraction of artifact pointers for auditability.
    """
    name = str(step_name or "")
    log_path = Path(record.log_path)
    text = ""
    try:
        text = log_path.read_text(encoding="utf-8")
    except Exception:
        text = ""

    artifacts: dict[str, str] = {}

    if name.startswith("capture"):
        # capture prints absolute run dir path on the last line.
        last = ""
        for ln in [x.strip() for x in text.splitlines() if x.strip()][-5:]:
            if "/captures/run-" in ln or ln.replace("\\", "/").endswith("/captures") or "captures/run-" in ln:
                last = ln
        run_dir = Path(last) if last else None
        if run_dir and not run_dir.is_absolute():
            run_dir = (repo_root / run_dir).resolve()
        if run_dir and run_dir.exists():
            try:
                rel = run_dir.relative_to(repo_root).as_posix()
            except Exception:
                rel = run_dir.as_posix()
            artifacts["run_dir"] = rel
            for key, fn in (("manifest", "manifest.json"), ("quality_report", "quality_report.md")):
                p = run_dir / fn
                if p.exists():
                    try:
                        artifacts[key] = p.relative_to(repo_root).as_posix()
                    except Exception:
                        artifacts[key] = p.as_posix()
            skills_dir = run_dir / "skills"
            if skills_dir.exists():
                try:
                    artifacts["output_dir"] = skills_dir.relative_to(repo_root).as_posix()
                except Exception:
                    artifacts["output_dir"] = skills_dir.as_posix()

    if name == "build-site":
        # build-site prints "Wrote: dist/index.json" and "Wrote: dist/index.html"
        wrote = []
        for ln in text.splitlines():
            m = re.search(r"\bWrote:\s+(\S+)", ln.strip())
            if m:
                wrote.append(m.group(1))
        if wrote:
            artifacts["wrote"] = ", ".join(wrote[:5])

    return artifacts


def _append_verify_log(*, repo_root: Path, records: list[RunRecord], mode: str) -> None:
    """
    Append a runbook summary block into docs/verify_log.md.
    This keeps auditing simple without requiring parsing JSONL.
    """
    docs_path = repo_root / "docs" / "verify_log.md"
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    day = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%d")

    lines: list[str] = []
    lines.append(f"## {day} (runbook {mode})")
    for r in records:
        lines.append(f"- run_id: `{r.run_id}` exit={r.exit_code} git={r.git_commit or 'unknown'}")
        lines.append(f"  - command: `{r.command}`")
        if r.args:
            lines.append(f"  - args: `{shlex.join(r.args)}`")
        lines.append(f"  - log: `{Path(r.log_path).relative_to(repo_root).as_posix()}`")
        if r.artifacts:
            for k, v in r.artifacts.items():
                lines.append(f"  - artifact.{k}: `{v}`")
    existing = ""
    if docs_path.exists():
        try:
            existing = docs_path.read_text(encoding="utf-8")
        except Exception:
            existing = ""
    block = "\n".join(lines).rstrip() + "\n"
    if existing and not existing.endswith("\n"):
        existing += "\n"
    docs_path.write_text(existing + "\n" + block, encoding="utf-8")
