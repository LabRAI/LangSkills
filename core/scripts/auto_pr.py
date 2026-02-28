from __future__ import annotations

import argparse
import datetime as _dt
import shlex
import subprocess
from pathlib import Path


def _utc_stamp() -> str:
    iso = _dt.datetime.now(tz=_dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return iso.replace(":", "").replace(".", "").replace("T", "-")


def _run(cmd: str, *, cwd: Path, dry_run: bool) -> str:
    if dry_run:
        print(f"[dry-run] {cmd}")
        return ""
    p = subprocess.run(cmd, cwd=str(cwd), shell=True, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stdout or "").strip() or f"Command failed: {cmd}")
    return (p.stdout or "").strip()


def _has_command(name: str, *, cwd: Path) -> bool:
    try:
        p = subprocess.run([name, "--version"], cwd=str(cwd), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return p.returncode == 0
    except Exception:
        return False


def cli_auto_pr(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="langskills auto-pr")
    parser.add_argument("--dry-run", action="store_true", default=True, dest="dry_run", help=argparse.SUPPRESS)
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--pr", action="store_true")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--base", default="")
    parser.add_argument("--branch", default="")
    parser.add_argument("--message", default="chore(skills): update generated skills")
    parser.add_argument("--paths", default="skills,docs,dist")
    ns = parser.parse_args(argv)

    # `--push` or `--pr` implies execute mode.
    dry_run = bool(ns.dry_run and not (ns.push or ns.pr))
    repo_root = Path(__file__).resolve().parents[2]

    cur_branch = _run("git rev-parse --abbrev-ref HEAD", cwd=repo_root, dry_run=False).strip()
    base_branch = ns.base.strip() or cur_branch
    branch = ns.branch.strip() or f"bot/{_utc_stamp()}/skills"
    paths = [p.strip() for p in str(ns.paths or "").split(",") if p.strip()]

    print(f"repo: {repo_root}")
    print(f"base: {base_branch}")
    print(f"branch: {branch}")
    print(f"remote: {ns.remote}")
    print(f"paths: {', '.join(paths)}")
    print(f"mode: {'dry-run' if dry_run else 'execute'}")

    status = _run("git status --porcelain", cwd=repo_root, dry_run=False).strip()
    if not status:
        print("OK: working tree clean")
    else:
        print("WARN: working tree has changes (will commit selected paths only)")

    try:
        _run(f"git checkout -b {shlex.quote(branch)}", cwd=repo_root, dry_run=dry_run)

        add_cmd = "git add " + " ".join(shlex.quote(p) for p in paths)
        _run(add_cmd, cwd=repo_root, dry_run=dry_run)

        _run(f"git commit -m {shlex.quote(ns.message)}", cwd=repo_root, dry_run=dry_run)

        if ns.push:
            _run(f"git push -u {shlex.quote(ns.remote)} {shlex.quote(branch)}", cwd=repo_root, dry_run=dry_run)

        if ns.pr:
            if not ns.push:
                raise RuntimeError("--pr requires --push (or push the branch first)")
            if _has_command("gh", cwd=repo_root):
                _run(f"gh pr create --fill --base {shlex.quote(base_branch)}", cwd=repo_root, dry_run=dry_run)
            else:
                print("WARN: GitHub CLI (gh) not found; PR creation skipped. Install gh or create PR manually.")

        print("DONE.")
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=__import__('sys').stderr)
        print("Attempt rollback: checkout previous branch and delete failed branch.", file=__import__('sys').stderr)
        try:
            _run(f"git checkout {shlex.quote(cur_branch)}", cwd=repo_root, dry_run=dry_run)
            _run(f"git branch -D {shlex.quote(branch)}", cwd=repo_root, dry_run=dry_run)
        except Exception:
            pass
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_auto_pr())
