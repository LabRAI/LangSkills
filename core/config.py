from __future__ import annotations

import json
import os
import re
from typing import Any
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .domain_config import DOMAIN_CONFIG
from .env import load_master_config
from .utils.paths import repo_root


def extract_url_hostname(raw_url: str) -> str:
    u = str(raw_url or "").strip()
    if not u:
        return ""
    try:
        return (urlsplit(u).hostname or "").strip().lower()
    except Exception:
        return ""


def _canonicalization_config() -> dict[str, Any]:
    default = {
        "drop_exact_params": [
            "gclid",
            "fbclid",
            "igshid",
            "mc_cid",
            "mc_eid",
            "mkt_tok",
            "yclid",
        ],
        "drop_prefix_params": ["utm_"],
        "host_specific": {
            "github.com": {"strip_dot_git": True},
            "stackoverflow.com": {"collapse_question_slug": True},
        },
        "trailing_slash": {"remove": True},
    }
    master = load_master_config(repo_root()) or {}
    canon = master.get("canonicalization") if isinstance(master, dict) else None
    if not isinstance(canon, dict):
        return default
    out = dict(default)
    for key in ("drop_exact_params", "drop_prefix_params"):
        if isinstance(canon.get(key), list):
            out[key] = canon.get(key)
    if isinstance(canon.get("host_specific"), dict):
        out["host_specific"] = canon.get("host_specific")
    if isinstance(canon.get("trailing_slash"), dict):
        out["trailing_slash"] = canon.get("trailing_slash")
    return out


def canonicalize_source_url(raw_url: str) -> str:
    input_url = str(raw_url or "").strip()
    if not input_url:
        return ""

    try:
        parts = urlsplit(input_url)
    except Exception:
        return input_url

    scheme = (parts.scheme or "").lower()
    hostname = (parts.hostname or "").lower()
    port = parts.port

    # Drop default ports.
    netloc = hostname
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{hostname}:{port}"

    path = parts.path or ""
    query_pairs = parse_qsl(parts.query or "", keep_blank_values=True)

    canon_cfg = _canonicalization_config()
    drop_exact = set([str(x) for x in (canon_cfg.get("drop_exact_params") or []) if str(x)])
    drop_prefix = tuple(str(x) for x in (canon_cfg.get("drop_prefix_params") or []) if str(x))

    kept: list[tuple[str, str]] = []
    for k, v in query_pairs:
        key = str(k or "").strip()
        lk = key.lower()
        if not key:
            continue
        if lk in drop_exact:
            continue
        if any(lk.startswith(p) for p in drop_prefix):
            continue
        kept.append((key, str(v or "")))
    kept.sort(key=lambda kv: (kv[0], kv[1]))
    query = urlencode(kept, doseq=True)

    # Remove trailing slash (except root).
    trailing = canon_cfg.get("trailing_slash") if isinstance(canon_cfg.get("trailing_slash"), dict) else {}
    if len(path) > 1 and bool(trailing.get("remove", True)):
        path = re.sub(r"/+$", "", path)

    # Host-specific canonicalization.
    host_specific = canon_cfg.get("host_specific") if isinstance(canon_cfg.get("host_specific"), dict) else {}
    gh_cfg = host_specific.get("github.com") if isinstance(host_specific.get("github.com"), dict) else {}
    so_cfg = host_specific.get("stackoverflow.com") if isinstance(host_specific.get("stackoverflow.com"), dict) else {}
    if hostname == "github.com" and bool(gh_cfg.get("strip_dot_git", True)):
        path_parts = [p for p in path.split("/") if p]
        if len(path_parts) == 2:
            owner, repo = path_parts
            if repo.lower().endswith(".git"):
                repo = repo[:-4]
            path = f"/{owner}/{repo}"
            query = ""
    if (hostname == "stackoverflow.com" or hostname.endswith(".stackoverflow.com")) and bool(so_cfg.get("collapse_question_slug", True)):
        m = re.match(r"^/questions/(\d+)(?:/|$)", path, flags=re.IGNORECASE)
        if m:
            path = f"/questions/{m.group(1)}"
            query = ""

    return urlunsplit((scheme, netloc, path, query, ""))  # drop fragment


def normalize_host_list(values: list[str] | None) -> list[str]:
    arr = [str(x or "").strip().lower() for x in (values or [])]
    out: list[str] = []
    seen: set[str] = set()
    for x in arr:
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def get_crawl_policy_from_config(config: dict, source_type: str) -> dict[str, list[str]]:
    cfg = dict(config or {})
    crawl = cfg.get("crawl") if isinstance(cfg.get("crawl"), dict) else {}
    key = str(source_type or "").strip().lower()
    block = crawl.get(key) if isinstance(crawl.get(key), dict) else {}
    return {
        "allow_hosts": normalize_host_list(block.get("allow_hosts")),
        "deny_hosts": normalize_host_list(block.get("deny_hosts")),
    }


def is_url_allowed_by_host_policy(url: str, policy: dict) -> bool:
    allow_hosts = normalize_host_list(policy.get("allow_hosts"))
    deny_hosts = normalize_host_list(policy.get("deny_hosts"))
    host = extract_url_hostname(url)
    if not host:
        return False
    if host in deny_hosts:
        return False
    if allow_hosts and host not in allow_hosts:
        return False
    return True


def is_url_allowed_by_config(*, config: dict, source_type: str, url: str) -> bool:
    policy = get_crawl_policy_from_config(config, source_type)
    if not policy["allow_hosts"] and not policy["deny_hosts"]:
        return True
    return is_url_allowed_by_host_policy(url, policy)


def clamp_int(value: object, *, min_value: int, max_value: int, default_value: int) -> int:
    try:
        n = int(str(value).strip())
    except Exception:
        return int(default_value)
    return max(min_value, min(max_value, n))


def rank_urls_by_topic(urls: list[str], topic: str) -> list[str]:
    arr = [str(x or "").strip() for x in (urls or [])]
    arr = [x for x in arr if x]
    t = str(topic or "").lower().strip()
    if not t:
        return arr

    tokens = [x.strip() for x in re.split(r"[^a-z0-9]+", t) if len(x.strip()) >= 3]

    def score(u: str) -> int:
        s = u.lower()
        sc = 0
        if t and t in s:
            sc += 10
        for tok in tokens:
            if tok in s:
                sc += 3
        return sc

    ranked = [{"u": u, "i": i, "sc": score(u)} for i, u in enumerate(arr)]
    ranked.sort(key=lambda x: (-x["sc"], x["i"]))
    return [x["u"] for x in ranked]


def compute_method_counts(*, config: dict, total: int | None, per_source: int | None) -> dict[str, int]:
    max_web = len(config.get("web_urls") or []) if isinstance(config.get("web_urls"), list) else 0
    default_per_source = 10
    max_per_source = 50
    max_total = 150

    env_total = str(os.environ.get("LANGSKILLS_TOTAL", "")).strip()
    env_per_source = str(os.environ.get("LANGSKILLS_PER_SOURCE", "")).strip()

    total_raw = total if total is not None else (env_total or None)
    if total_raw is not None and str(total_raw).strip() != "":
        t = clamp_int(total_raw, min_value=1, max_value=max_total, default_value=default_per_source * 3)
        base = t // 3
        rem = t % 3
        web = base + (1 if rem >= 1 else 0)
        github = base + (1 if rem >= 2 else 0)
        forum = base

        if max_web > 0 and web > max_web:
            overflow = web - max_web
            web = max_web
            github += overflow
        if max_web == 0:
            web = 0

        return {"web": web, "github": github, "forum": forum}

    per_source_raw = per_source if per_source is not None else (env_per_source or default_per_source)
    n = clamp_int(per_source_raw, min_value=1, max_value=max_per_source, default_value=default_per_source)
    web = min(n, max_web) if max_web > 0 else 0
    return {"web": web, "github": n, "forum": n}


def default_domain_for_topic(topic: str) -> str:
    t = str(topic or "").lower()
    if re.search(r"(k8s|kubernetes|helm|eks|gke|aks)", t):
        return "cloud"
    if re.search(
        r"(pytorch|torch|transformers|hugging ?face|hf|lora|fine-?tune|finetune|mlflow|scikit|sklearn|embedding|embeddings|rag|faiss|vector)",
        t,
    ):
        return "ml"
    if re.search(r"(owasp|jwt|oauth|oidc|sso|tls|https|xss|csrf|cve|vuln|vulnerability|hardening|ssh|sshd|authn|authz)", t):
        return "security"
    if re.search(r"(observability|prometheus|grafana|opentelemetry|otel|jaeger|tempo|tracing|metrics|logging|logs|alerting|promql)", t):
        return "observability"
    if re.search(r"(sql|postgres|duckdb|pandas|parquet|csv)", t):
        return "data"
    if re.search(r"(git|docker|npm|node|python|venv|ci|github actions)", t):
        return "devtools"
    if re.search(r"(react|next\.js|nextjs|javascript|typescript|css|html|frontend|web api|dom|browser)", t):
        return "web"
    return "linux"


def read_quality_gates(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    master = load_master_config(root)
    if isinstance(master, dict) and isinstance(master.get("quality_gates"), dict):
        return master.get("quality_gates") or {}
    path = root / "config" / "quality_gates.yaml"
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def read_license_policy(repo_root: str | Path) -> dict | None:
    root = Path(repo_root).resolve()
    master = load_master_config(root)
    if isinstance(master, dict) and isinstance(master.get("license_policy"), dict):
        return master.get("license_policy")
    policy_path = root / "config" / "license_policy.json"
    if not policy_path.exists():
        return None
    try:
        return json.loads(policy_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def license_decision(policy: dict | None, *, source_type: str, license_spdx: str) -> str:
    p = dict(policy or {})
    defaults = p.get("defaults") if isinstance(p.get("defaults"), dict) else {}
    by_type = p.get("by_source_type") if isinstance(p.get("by_source_type"), dict) else {}
    t = str(source_type or "").strip()
    spdx = str(license_spdx or "").strip()
    cfg = by_type.get(t) if isinstance(by_type.get(t), dict) else {}

    lic_map = cfg.get("license_spdx") if isinstance(cfg.get("license_spdx"), dict) else {}
    if spdx and spdx in lic_map:
        return str(lic_map[spdx])
    deny = cfg.get("deny_spdx") if isinstance(cfg.get("deny_spdx"), list) else []
    if spdx and spdx in deny:
        return "deny"
    allow = cfg.get("allow_spdx") if isinstance(cfg.get("allow_spdx"), list) else []
    if spdx and spdx in allow:
        return "allow"

    unk = cfg.get("unknown") if cfg.get("unknown") is not None else defaults.get("unknown", "needs_review")
    return str(unk)
