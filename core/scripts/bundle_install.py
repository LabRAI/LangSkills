"""Download and install LangSkills bundles from Hugging Face."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

_HF_REPO = "Tommysha/langskills-bundles"
_HF_ENDPOINTS = [
    "https://huggingface.co",
    "https://hf-mirror.com",
]
_INSTALL_DIR = Path.home() / ".langskills"
_CONFIG_PATH = _INSTALL_DIR / "search_config.json"
_SUPPORTED_HF_BUNDLE_TYPES = {"lite"}


# ── Hugging Face helpers ─────────────────────────────────────────

def _hf_list_files(hf_repo: str) -> list[str]:
    """List files in a Hugging Face dataset repo via the API.

    Tries the official endpoint first, then falls back to hf-mirror.com.
    """
    custom = os.environ.get("HF_ENDPOINT", "").strip().rstrip("/")
    endpoints = [custom] if custom else list(_HF_ENDPOINTS)

    for ep in endpoints:
        url = f"{ep}/api/datasets/{hf_repo}"
        req = urllib.request.Request(url, headers={"User-Agent": "langskills-rai"})
        token = os.environ.get("HF_TOKEN", "").strip()
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                info = json.loads(resp.read().decode())
            siblings = info.get("siblings", [])
            # Remember which endpoint worked for download URLs.
            os.environ["_HF_ACTIVE_ENDPOINT"] = ep
            return [s["rfilename"] for s in siblings]
        except Exception:
            continue
    raise RuntimeError("Could not reach Hugging Face (tried official + mirror)")


def _hf_pick_asset(
    files: list[str], bundle_type: str, domain: str = "",
) -> tuple[str, str] | None:
    """Find the .sqlite file and its .sha256 sidecar on Hugging Face.

    Returns (sqlite_url, sha256_url) or None.
    """
    if domain:
        pattern = f"langskills-bundle-{bundle_type}-{domain}-"
    else:
        pattern = f"langskills-bundle-{bundle_type}-"
    sqlite_file = None
    sha_file = None

    for name in files:
        if pattern not in name:
            continue
        if name.endswith(".sqlite"):
            sqlite_file = name
        elif name.endswith(".sqlite.sha256"):
            sha_file = name

    if sqlite_file is None:
        return None
    # Use whichever endpoint succeeded during _hf_list_files
    active = os.environ.get("_HF_ACTIVE_ENDPOINT", _HF_ENDPOINTS[0])
    base = f"{active}/datasets/{_HF_REPO}/resolve/main"
    sqlite_url = f"{base}/{sqlite_file}"
    sha_url = f"{base}/{sha_file}" if sha_file else ""
    return sqlite_url, sha_url


# ── download / verify ────────────────────────────────────────────

def _download_with_progress(url: str, dest: Path) -> None:
    """Download a URL to *dest* with a simple progress indicator."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "langskills-rai"})
    hf_token = os.environ.get("HF_TOKEN", "").strip()
    if hf_token and ("huggingface.co" in url or "hf-mirror.com" in url):
        req.add_header("Authorization", f"Bearer {hf_token}")

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

    req = urllib.request.Request(checksum_url, headers={"User-Agent": "langskills-rai"})
    token = os.environ.get("HF_TOKEN", "").strip()
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
    bundle_type: str = "lite",
    check_only: bool = False,
    domain: str = "",
) -> int:
    """Download and install a domain bundle from Hugging Face.

    Parameters
    ----------
    domain : str
        If given, download the domain-specific bundle (e.g. ``"linux"``).

    Returns 0 on success, 1 on failure.
    """
    if bundle_type not in _SUPPORTED_HF_BUNDLE_TYPES:
        supported = ", ".join(sorted(_SUPPORTED_HF_BUNDLE_TYPES))
        print(
            f"Error: Hugging Face only publishes {supported} domain bundles. "
            f"Requested bundle type '{bundle_type}' is local-build only.",
            file=sys.stderr,
        )
        return 1

    if not domain:
        print(
            "Error: Hugging Face bundles are published per domain. "
            "Use --domain <name> or --auto.",
            file=sys.stderr,
        )
        return 1

    print(f"Fetching file list from Hugging Face ({_HF_REPO}) ...", file=sys.stderr)
    try:
        hf_files = _hf_list_files(_HF_REPO)
    except Exception as exc:
        print(f"Hugging Face unavailable: {exc}", file=sys.stderr)
        return 1

    asset_info = _hf_pick_asset(hf_files, bundle_type, domain=domain)
    if asset_info is None:
        label = f"{bundle_type}-{domain}"
        print(
            f"Error: no {label} bundle found in Hugging Face dataset {_HF_REPO}",
            file=sys.stderr,
        )
        return 1

    print("Source: Hugging Face", file=sys.stderr)

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
        "Search with: langskills-rai skill-search \"your query\" --content --top 5",
        file=sys.stderr,
    )
    return 0


def install_auto(
    bundle_type: str = "lite",
    check_only: bool = False,
    project_dir: str = "",
) -> int:
    """Auto-detect project type and install matching domain bundles.

    Returns 0 on success, 1 if any domain fails.
    """
    from ..detect_project import detect_domains

    if bundle_type not in _SUPPORTED_HF_BUNDLE_TYPES:
        supported = ", ".join(sorted(_SUPPORTED_HF_BUNDLE_TYPES))
        print(
            f"Error: Hugging Face only publishes {supported} domain bundles. "
            f"Requested bundle type '{bundle_type}' is local-build only.",
            file=sys.stderr,
        )
        return 1

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
            bundle_type=bundle_type,
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
        prog="langskills-rai bundle-install",
        description="Download and install LangSkills domain bundles from Hugging Face",
    )
    parser.add_argument(
        "--bundle",
        choices=["lite", "full"],
        default="lite",
        help="Bundle type (lite is available from Hugging Face; full is local-build only)",
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
        help="Auto-detect project type and install matching bundles (default when --domain is omitted)",
    )
    parser.add_argument(
        "--project-dir",
        default="",
        help="Project directory for --auto detection (default: cwd)",
    )

    args = parser.parse_args(argv)

    if args.auto and args.domain:
        parser.error("--auto cannot be combined with --domain")

    if not args.auto and not args.domain:
        args.auto = True

    if args.auto:
        return install_auto(
            bundle_type=args.bundle,
            check_only=args.check,
            project_dir=args.project_dir,
        )

    return install_bundle(
        bundle_type=args.bundle,
        check_only=args.check,
        domain=args.domain,
    )


if __name__ == "__main__":
    raise SystemExit(cli_bundle_install())
