"""Download and install LangSkills bundles from GitHub Releases."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

_GITHUB_REPO = "LabRAI/LangSkills"
_INSTALL_DIR = Path.home() / ".langskills"
_CONFIG_PATH = _INSTALL_DIR / "search_config.json"


# ── GitHub Release helpers ───────────────────────────────────────

def _find_latest_release(repo: str) -> dict:
    """Fetch the latest GitHub release metadata via the public API."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _find_release_by_tag(repo: str, tag: str) -> dict:
    """Fetch a specific release by tag name."""
    url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _pick_asset(
    release: dict, bundle_type: str, domain: str = "",
) -> tuple[str, str] | None:
    """Find the .sqlite asset and its .sha256 sidecar in a release.

    When *domain* is given, match ``langskills-bundle-{bundle_type}-{domain}-``
    instead of the generic pattern.

    Returns (sqlite_url, sha256_url) or None.
    """
    assets = release.get("assets", [])
    if domain:
        pattern = f"langskills-bundle-{bundle_type}-{domain}-"
    else:
        pattern = f"langskills-bundle-{bundle_type}-"
    sqlite_asset = None
    sha_asset = None

    for a in assets:
        name = a.get("name", "")
        dl = a.get("browser_download_url", "")
        if not name.startswith(pattern.split("-v")[0]):
            # For domain bundles we need stricter matching to avoid
            # "linux" matching "linux-v..." but not "llm-v..."
            if pattern not in name:
                continue
        if pattern in name and name.endswith(".sqlite"):
            sqlite_asset = (name, dl)
        elif pattern in name and name.endswith(".sqlite.sha256"):
            sha_asset = (name, dl)

    if sqlite_asset is None:
        return None
    return sqlite_asset[1], sha_asset[1] if sha_asset else ""


# ── download / verify ────────────────────────────────────────────

def _download_with_progress(url: str, dest: Path) -> None:
    """Download a URL to *dest* with a simple progress indicator."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url)
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    with urllib.request.urlopen(req, timeout=300) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(1 << 20)  # 1 MB
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = 100 * downloaded // total
                    mb = downloaded / (1 << 20)
                    total_mb = total / (1 << 20)
                    print(
                        f"\r  {mb:.1f}/{total_mb:.1f} MB ({pct}%)",
                        end="",
                        flush=True,
                        file=sys.stderr,
                    )
        print(file=sys.stderr)  # newline after progress


def _verify_sha256(bundle_path: Path, checksum_url: str) -> bool:
    """Download the .sha256 sidecar and verify the bundle."""
    if not checksum_url:
        print("Warning: no checksum file available, skipping verification.", file=sys.stderr)
        return True

    req = urllib.request.Request(checksum_url)
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        expected = resp.read().decode().strip().split()[0].lower()

    h = hashlib.sha256()
    with open(bundle_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    actual = h.hexdigest().lower()

    if actual != expected:
        print(
            f"ERROR: SHA-256 mismatch!\n  expected: {expected}\n  actual:   {actual}",
            file=sys.stderr,
        )
        return False
    print(f"  SHA-256 verified: {actual[:16]}...", file=sys.stderr)
    return True


# ── config ───────────────────────────────────────────────────────

def _write_config(bundle_path: Path, domain: str = "") -> None:
    """Write search_config.json pointing to the installed bundle.

    When *domain* is given, update the ``bundles`` dict instead of
    overwriting ``bundle_path``.
    """
    _INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    cfg: dict = {}
    if _CONFIG_PATH.exists():
        try:
            cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    if domain:
        bundles = cfg.get("bundles", {})
        if not isinstance(bundles, dict):
            bundles = {}
        bundles[domain] = str(bundle_path)
        cfg["bundles"] = bundles
    else:
        cfg["bundle_path"] = str(bundle_path)

    _CONFIG_PATH.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print(f"  Config written: {_CONFIG_PATH}", file=sys.stderr)


# ── public API ───────────────────────────────────────────────────

def install_bundle(
    release: str = "latest",
    bundle_type: str = "lite",
    repo: str = _GITHUB_REPO,
    check_only: bool = False,
    domain: str = "",
) -> int:
    """Download and install a bundle from GitHub Releases.

    Parameters
    ----------
    domain : str
        If given, download the domain-specific bundle (e.g. ``"linux"``).

    Returns 0 on success, 1 on failure.
    """
    print(f"Fetching release info from {repo} ...", file=sys.stderr)
    try:
        if release == "latest":
            rel = _find_latest_release(repo)
        else:
            rel = _find_release_by_tag(repo, release)
    except Exception as exc:
        print(f"Error: could not fetch release — {exc}", file=sys.stderr)
        return 1

    tag = rel.get("tag_name", "unknown")
    print(f"Release: {tag}", file=sys.stderr)

    asset_info = _pick_asset(rel, bundle_type, domain=domain)
    if asset_info is None:
        label = f"{bundle_type}-{domain}" if domain else bundle_type
        print(f"Error: no {label} bundle found in release {tag}", file=sys.stderr)
        return 1

    sqlite_url, sha_url = asset_info

    if check_only:
        print(f"Would download: {sqlite_url}", file=sys.stderr)
        print(f"Destination:    {_INSTALL_DIR}", file=sys.stderr)
        return 0

    # Download
    filename = sqlite_url.rsplit("/", 1)[-1]
    dest = _INSTALL_DIR / filename
    print(f"Downloading {filename} ...", file=sys.stderr)
    _download_with_progress(sqlite_url, dest)

    # Verify
    if not _verify_sha256(dest, sha_url):
        dest.unlink(missing_ok=True)
        return 1

    # Write config
    _write_config(dest, domain=domain)

    print(f"\nInstalled: {dest}", file=sys.stderr)
    print(
        "Search with: python3 -m langskills.search \"your query\" --content --top 5",
        file=sys.stderr,
    )
    return 0


def install_auto(
    release: str = "latest",
    bundle_type: str = "lite",
    repo: str = _GITHUB_REPO,
    check_only: bool = False,
    project_dir: str = "",
) -> int:
    """Auto-detect project type and install matching domain bundles.

    Returns 0 on success, 1 if any domain fails.
    """
    from ..detect_project import detect_domains

    target = Path(project_dir) if project_dir else Path.cwd()
    domains = detect_domains(target)
    if not domains:
        print(f"No recognizable project type detected in {target}", file=sys.stderr)
        print("Use --domain to specify manually.", file=sys.stderr)
        return 1

    print(f"Detected domains: {', '.join(domains)}", file=sys.stderr)
    failures = 0
    for d in domains:
        print(f"\n--- Installing domain: {d} ---", file=sys.stderr)
        ret = install_bundle(
            release=release,
            bundle_type=bundle_type,
            repo=repo,
            check_only=check_only,
            domain=d,
        )
        if ret != 0:
            print(f"Warning: failed to install domain '{d}'", file=sys.stderr)
            failures += 1

    if failures == len(domains):
        return 1
    return 0


# ── CLI ──────────────────────────────────────────────────────────

def cli_bundle_install(argv: list[str] | None = None) -> int:
    """CLI entry point for ``langskills bundle-install``."""
    parser = argparse.ArgumentParser(
        prog="langskills bundle-install",
        description="Download and install a LangSkills skill bundle from GitHub Releases",
    )
    parser.add_argument(
        "--release",
        default="latest",
        help="Release tag or 'latest' (default: latest)",
    )
    parser.add_argument(
        "--bundle",
        choices=["lite", "full"],
        default="lite",
        help="Bundle type (default: lite)",
    )
    parser.add_argument(
        "--repo",
        default=_GITHUB_REPO,
        help=f"GitHub repo (default: {_GITHUB_REPO})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Dry-run: show what would be downloaded",
    )
    parser.add_argument(
        "--domain",
        default="",
        help="Install domain-specific bundle (e.g. linux, web, research-arxiv)",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Auto-detect project type and install matching bundles",
    )
    parser.add_argument(
        "--project-dir",
        default="",
        help="Project directory for --auto detection (default: cwd)",
    )

    args = parser.parse_args(argv)

    if args.auto:
        return install_auto(
            release=args.release,
            bundle_type=args.bundle,
            repo=args.repo,
            check_only=args.check,
            project_dir=args.project_dir,
        )

    return install_bundle(
        release=args.release,
        bundle_type=args.bundle,
        repo=args.repo,
        check_only=args.check,
        domain=args.domain,
    )


if __name__ == "__main__":
    raise SystemExit(cli_bundle_install())
