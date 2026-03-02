from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from .env import env_bool as _env_bool
from .env import env_int as _env_int


def main(argv: list[str] | None = None) -> int:
    args_in = list(sys.argv[1:] if argv is None else argv)
    repo_root = Path(__file__).resolve().parents[1]

    known_cmds = {
        "capture",
        "search",
        "fetch",
        "auth",
        "sources-audit",
        "dir-docs",
        "topics-capture",
        "improve",
        "postprocess",
        "validate",
        "build-site",
        "self-check",
        "runner",
        "auto-pr",
        "backfill-package-v2",
        "backfill-verification",
        "backfill-sources",
        "queue-init",
        "queue-enqueue",
        "queue-lease",
        "queue-ack",
        "queue-nack",
        "queue-requeue",
        "queue-stats",
        "queue-watch",
        "queue-gc",
        "queue-drain",
        "queue-seed",
        "queue-from-captures",
        "import-littlecrawler",
        "arxiv-pipeline",
        "journal-pipeline",
        # Repo understanding / synthesis
        "repo-index",
        "repo-runbook",
        "repo-query",
        "repo-export",
        "skill-from-repo",
        "skill-search",
        "build-bundle",
        "bundle-install",
        "bundle-rebuild",
        "reindex-skills",
    }
    if args_in and args_in[0].lower() not in known_cmds and not args_in[0].startswith("-"):
        args_in = ["capture", *args_in]

    parser = argparse.ArgumentParser(prog="langskills")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_capture = sub.add_parser("capture", help="Generate a new capture run under captures/")
    p_capture.add_argument("topic", help='Topic text, optionally with "@N" shorthand for --total N')
    p_capture.add_argument("--total", type=int, default=None, help="Total items per run (split across methods/domains)")
    p_capture.add_argument("--per-source", type=int, default=None, help="Items per method per domain")
    p_capture.add_argument("--domain", type=str, default=None, help="Force a single domain")
    p_capture.add_argument("--all", action="store_true", help="Run all domains")
    p_capture.add_argument("--publish", action="store_true", help="Publish run outputs into skills/")
    p_capture.add_argument("--publish-overwrite", action="store_true", help="Overwrite skills/ entries when publishing")
    p_capture.add_argument("--pretty", action="store_true", help="Pretty per-skill progress (implies --progress pretty)")
    p_capture.add_argument("--progress", choices=["plain", "pretty"], default=None, help="Progress UI mode")

    p_search = sub.add_parser("search", help="Search URLs (web/tavily/baidu/zhihu/xhs/github/forum/arxiv)")
    p_search.add_argument("engine", choices=["web", "tavily", "baidu", "zhihu", "xhs", "github", "forum", "arxiv"])
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.add_argument("--enqueue", action="store_true", help="Enqueue results into the persistent queue")
    p_search.add_argument("--queue", default="", help="Queue DB path (default: runs/queue.db)")
    p_search.add_argument("--stage", default="ingest")
    p_search.add_argument("--domain", default="")

    p_ss = sub.add_parser("skill-search", help="Search the local skill library (index.sqlite)")
    p_ss.add_argument("query", nargs="?", default="", help="Free-text search query")
    p_ss.add_argument("--top", type=int, default=10, help="Max results (default: 10)")
    p_ss.add_argument("--domain", default="", help="Filter by domain")
    p_ss.add_argument("--kind", default="", help="Filter by skill_kind")
    p_ss.add_argument("--source-type", default="", help="Filter by source_type")
    p_ss.add_argument("--min-score", type=float, default=0.0, help="Minimum overall_score")
    p_ss.add_argument("--domains", action="store_true", help="List available domains and exit")
    p_ss.add_argument("--kinds", action="store_true", help="List available skill kinds and exit")
    p_ss.add_argument("--show-path", action="store_true", help="Show local skill.md paths in results")
    p_ss.add_argument("--content", action="store_true", help="Include full skill.md content")
    p_ss.add_argument("--max-chars", type=int, default=4000, help="Truncate skill content (0=unlimited)")
    p_ss.add_argument("--format", choices=["brief", "markdown", "json"], default="brief", help="Output format")
    p_ss.add_argument("--brief", action="store_true", help="Shorthand for --format brief")

    p_bb = sub.add_parser("build-bundle", help="Build a self-contained SQLite skill bundle")
    p_bb.add_argument("--type", choices=["lite", "full", "both"], default="lite", help="Bundle type (default: lite)")
    p_bb.add_argument("--out", default="dist", help="Output directory (default: dist/)")
    p_bb.add_argument("--version", default="", help="Version string (default: auto from date)")
    p_bb.add_argument("--workers", type=int, default=16, help="Parallel reader threads (default: 16)")
    p_bb.add_argument("--split-by-domain", action="store_true", help="Build independent bundles for each domain/journal")
    p_bb.add_argument("--domain", default="", help="Comma-separated domain list (e.g. linux,web,research-arxiv)")
    p_bb.add_argument("--min-score", type=float, default=0.0, help="Exclude skills below this overall_score")

    p_bi = sub.add_parser("bundle-install", help="Download a skill bundle from GitHub Releases")
    p_bi.add_argument("--release", default="latest", help="Release tag or 'latest'")
    p_bi.add_argument("--bundle", choices=["lite", "full"], default="lite", help="Bundle type (default: lite)")
    p_bi.add_argument("--repo", default="", help="GitHub repo override")
    p_bi.add_argument("--check", action="store_true", help="Dry-run: show what would be downloaded")
    p_bi.add_argument("--domain", default="", help="Install domain-specific bundle (e.g. linux, web, research-arxiv)")
    p_bi.add_argument("--auto", action="store_true", help="Auto-detect project type and install matching bundles")
    p_bi.add_argument("--project-dir", default="", help="Project directory for --auto detection (default: cwd)")

    sub.add_parser("bundle-rebuild", help="Rebuild skills/index.sqlite from skills/index.json")

    p_fetch = sub.add_parser("fetch", help="Fetch a URL and extract text (debug)")
    p_fetch.add_argument("engine", choices=["auto", "webpage", "baidu", "github", "forum", "arxiv", "zhihu", "xhs"])
    p_fetch.add_argument("url")
    p_fetch.add_argument("--timeout-ms", type=int, default=25_000)
    p_fetch.add_argument("--out-dir", default="", help="Write raw.html/text.txt/meta.json under this directory (optional)")
    p_fetch.add_argument("--include-text", action="store_true", help="Include full extracted text in stdout JSON (default: excerpt only)")

    p_auth = sub.add_parser("auth", help="Playwright login helpers (zhihu/xhs)")
    p_auth.add_argument("platform", choices=["zhihu", "xhs"])
    p_auth.add_argument(
        "--storage-state",
        default="",
        help="Where to write Playwright storage_state JSON (default: runs/playwright_auth/<platform>_storage_state.json)",
    )
    p_auth.add_argument("--timeout-sec", type=int, default=300)

    p_sa = sub.add_parser("sources-audit", help="Audit source providers (speed, auth readiness, common failures)")
    p_sa.add_argument("--query", default="python")
    p_sa.add_argument("--limit", type=int, default=5)
    p_sa.add_argument("--timeout-ms", type=int, default=25_000)
    p_sa.add_argument("--webpage-concurrency", type=int, default=6)
    p_sa.add_argument("--out-dir", default="", help="Default: captures/source_audit/<timestamp>/")
    p_sa.add_argument("--report", default="docs/source_audit_report.md", help="Write a Markdown summary here (optional)")
    p_sa.add_argument("--no-report", action="store_true", help="Do not write docs report file")
    p_sa.add_argument("--json", action="store_true", help="Print raw JSON to stdout (default: print paths)")

    p_dd = sub.add_parser(
        "dir-docs",
        help="Generate per-directory DIR_DOCS.md for Python code (auto index of files/classes/functions)",
    )
    p_dd.add_argument("--roots", default="core,scripts", help="Comma-separated roots to scan (relative to repo root)")
    p_dd.add_argument("--filename", default="DIR_DOCS.md", help="Output filename in each directory")
    p_dd.add_argument("--dry-run", action="store_true", help="Do not write files; only print summary JSON")

    p_topics = sub.add_parser("topics-capture", help="Batch enqueue topics into the persistent queue")
    p_topics.add_argument("--topics-file", default="topics/topics.yaml")
    p_topics.add_argument("--limit", type=int, default=0, help="Limit number of topics (0 = all)")
    p_topics.add_argument("--queue", default="", help="Queue DB path (default: runs/queue.db)")

    p_improve = sub.add_parser("improve", help="Improve a run in place")
    p_improve.add_argument("run_target", help="run-id, path, or 'latest'")

    p_post = sub.add_parser("postprocess", help="Postprocess a run (dedupe/matrix/combos)")
    p_post.add_argument("run_target", help="run-id, path, or 'latest'")

    p_validate = sub.add_parser("validate", help="Validate skills/ (or a run skills root)")
    p_validate.add_argument("--strict", action="store_true")
    p_validate.add_argument("--package", action="store_true", dest="check_package")
    p_validate.add_argument("--pkg", "--v2", action="store_true", dest="check_package", help=argparse.SUPPRESS, default=argparse.SUPPRESS)
    p_validate.add_argument("--root", default="skills")
    p_validate.add_argument("--path", dest="root", help=argparse.SUPPRESS, default=argparse.SUPPRESS)
    p_validate.add_argument(
        "--max-skills",
        type=int,
        default=0,
        help="Validate at most N skill directories (0 = all). Also supports LANGSKILLS_VALIDATE_MAX_SKILLS.",
    )

    sub.add_parser("build-site", help="Generate dist/index.json + dist/index.html from skills/index.json")

    p_sc = sub.add_parser("self-check", help="Local environment sanity check")
    p_sc.add_argument("--skip-remote", action="store_true")

    p_runner = sub.add_parser("runner", help="Resumable background runner (discover -> queue -> generate -> publish)")
    p_runner.add_argument("--state", default="runs/queue.db", help="Legacy: queue db path (or old runner_state.json)")
    p_runner.add_argument("--queue", default="", help="Queue DB path (default: runs/queue.db)")
    p_runner.add_argument("--once", action="store_true")
    p_runner.add_argument("--interval-ms", type=int, default=60_000)
    p_runner.add_argument("--rate-ms", type=int, default=1_000)
    p_runner.add_argument("--task-timeout-ms", type=int, default=600_000)
    p_runner.add_argument("--max-tasks", type=int, default=50)
    p_runner.add_argument("--max-attempts", type=int, default=5)
    p_runner.add_argument("--domain", default="")
    p_runner.add_argument("--all", action="store_true")
    p_runner.add_argument("--topic", default="")
    p_runner.add_argument("--topics-file", default="")
    p_runner.add_argument("--topics-limit", type=int, default=0)
    p_runner.add_argument("--publish-overwrite", dest="publish_overwrite", action="store_true")
    p_runner.add_argument("--publish-force", dest="publish_overwrite", action="store_true", help=argparse.SUPPRESS, default=argparse.SUPPRESS)
    p_runner.add_argument("--strict", action="store_true")
    p_runner.add_argument("--no-discover", action="store_true", help="Skip discovery; only process existing queued items")
    p_runner.add_argument(
        "--discover-providers",
        default="web,github,forum",
        help="Comma-separated: web,github,forum (controls discovery only; does not affect existing queue items)",
    )
    p_runner.add_argument(
        "--ignore-license-policy",
        action="store_true",
        help="Do not skip/deny items based on license policy during discovery/ingest (still recorded in artifacts)",
    )
    p_runner.add_argument(
        "--enforce-license-policy",
        action="store_true",
        help="Enforce license policy during discovery/ingest (overrides --ignore-license-policy and the --no-llm default)",
    )
    p_runner.add_argument(
        "--max-stage",
        default="",
        help="Only process queue items up to this stage (inclusive): discover|ingest|preprocess|llm_generate|validate|improve|publish",
    )
    p_runner.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM-dependent stages (equivalent to --max-stage preprocess); useful when OPENAI/OLLAMA env is not set yet.",
    )
    p_runner.add_argument("--worker-id", default="")
    p_runner.add_argument("--verbose", action="store_true", help="Print per-item progress logs")
    p_runner.add_argument("--source-type", default="", help="Only process queue items with this source_type (comma-separated)")

    p_pr = sub.add_parser("auto-pr", help="Create a commit/branch and optionally push + open a PR")
    p_pr.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS, default=argparse.SUPPRESS)
    p_pr.add_argument("--push", action="store_true")
    p_pr.add_argument("--pr", action="store_true")
    p_pr.add_argument("--remote", default="origin")
    p_pr.add_argument("--base", default="")
    p_pr.add_argument("--branch", default="")
    p_pr.add_argument("--message", default="chore(skills): update generated skills")
    p_pr.add_argument("--paths", default="skills,docs,dist")

    p_bf = sub.add_parser("backfill-package-v2", help="Generate missing package v2 files for existing skills")
    p_bf.add_argument("--root", default="skills")
    p_bf.add_argument("--provider", dest="provider", default=None)
    p_bf.add_argument("--llm", dest="provider", help=argparse.SUPPRESS, default=argparse.SUPPRESS)
    p_bf.add_argument("--limit", type=int, default=0)
    p_bf.add_argument("--overwrite", action="store_true", dest="overwrite")
    p_bf.add_argument("--force", action="store_true", dest="overwrite", help=argparse.SUPPRESS, default=argparse.SUPPRESS)

    p_bv = sub.add_parser("backfill-verification", help="Ensure Verification sections include fenced code blocks")
    p_bv.add_argument("--root", default="skills/by-skill")
    p_bv.add_argument("--dry-run", action="store_true")

    p_bs = sub.add_parser("backfill-sources", help="Backfill sources/by-id from existing artifacts")
    p_bs.add_argument("--overwrite", action="store_true")
    p_bs.add_argument("--dry-run", action="store_true")

    p_reindex = sub.add_parser("reindex-skills", help="Rebuild skills/index.json from by-skill view")
    p_reindex.add_argument("--root", default="skills/by-skill")

    p_qinit = sub.add_parser("queue-init", help="Initialize the persistent queue storage")
    p_qinit.add_argument("--queue", default="", help="Queue DB path (default: runs/queue.db)")

    p_qe = sub.add_parser("queue-enqueue", help="Manually enqueue a source item")
    p_qe.add_argument("--source-url", required=True)
    p_qe.add_argument("--source-type", default="webpage")
    p_qe.add_argument("--stage", default="ingest")
    p_qe.add_argument("--domain", default="")
    p_qe.add_argument("--title", default="")
    p_qe.add_argument("--tags", default="")
    p_qe.add_argument("--priority", type=int, default=0)
    p_qe.add_argument("--max-attempts", type=int, default=0)
    p_qe.add_argument("--payload-path", default="")
    p_qe.add_argument("--config-json", default="")
    p_qe.add_argument("--extra-json", default="")
    p_qe.add_argument("--queue", default="")

    p_ql = sub.add_parser("queue-lease", help="Lease queue items for debugging")
    p_ql.add_argument("--limit", type=int, default=1)
    p_ql.add_argument("--stage", action="append", default=[])
    p_ql.add_argument("--source-type", default="")
    p_ql.add_argument("--lease-seconds", type=int, default=0)
    p_ql.add_argument("--worker-id", default="manual")
    p_ql.add_argument("--queue", default="")

    p_qa = sub.add_parser("queue-ack", help="Acknowledge a queue item as done")
    p_qa.add_argument("item_id", type=int)
    p_qa.add_argument("--queue", default="")

    p_qn = sub.add_parser("queue-nack", help="Fail a queue item with backoff")
    p_qn.add_argument("item_id", type=int)
    p_qn.add_argument("--reason", default="error")
    p_qn.add_argument("--backoff-seconds", type=int, default=0)
    p_qn.add_argument("--max-attempts", type=int, default=0)
    p_qn.add_argument("--queue", default="")

    p_qr = sub.add_parser("queue-requeue", help="Move a queue item to another stage")
    p_qr.add_argument("item_id", type=int)
    p_qr.add_argument("--stage", required=True)
    p_qr.add_argument("--queue", default="")

    p_qs = sub.add_parser("queue-stats", help="Show queue counts by stage/status/source")
    p_qs.add_argument("--queue", default="")

    p_qw = sub.add_parser("queue-watch", help="Live queue stats (rich)")
    p_qw.add_argument("--queue", default="")
    p_qw.add_argument("--interval-ms", type=int, default=1000)
    p_qw.add_argument("--once", action="store_true")
    p_qw.add_argument("--skills-root", default="captures")
    p_qw.add_argument("--skills-published-root", default="skills/by-skill")
    p_qw.add_argument("--skills-scan-ms", type=int, default=30000)

    p_qg = sub.add_parser("queue-gc", help="Reclaim expired leases")
    p_qg.add_argument("--no-reclaim", action="store_true")
    p_qg.add_argument("--queue", default="")

    p_qd = sub.add_parser("queue-drain", help="Enable/disable queue draining (no new enqueues)")
    p_qd.add_argument("--enable", action="store_true")
    p_qd.add_argument("--disable", action="store_true")
    p_qd.add_argument("--status", action="store_true")
    p_qd.add_argument("--queue", default="")

    p_qseed = sub.add_parser("queue-seed", help="Seed the persistent queue by searching topics")

    sub.add_parser("arxiv-pipeline", help="ArXiv paper pipeline: discover, download PDF, generate skills")
    sub.add_parser("journal-pipeline", help="Journal paper pipeline: crawl PMC/PLOS/Nature/eLife, extract fulltext, generate skills")

    p_ilc = sub.add_parser("import-littlecrawler", help="Import LittleCrawler search_contents JSON into the queue (offline)")
    p_ilc.add_argument("platform", choices=["zhihu", "xhs"])
    p_ilc.add_argument("--input", required=True, help="Path to LittleCrawler search_contents_*.json")
    p_ilc.add_argument("--queue", default="", help="Queue DB path (default: runs/queue_<platform>.db)")
    p_ilc.add_argument("--run-id", default="", help="captures/<run-id>/ will be created to store SourceArtifact JSON files")
    p_ilc.add_argument("--stage", default="preprocess")
    p_ilc.add_argument("--limit", type=int, default=0, help="Import at most N items (0 = all)")
    p_ilc.add_argument("--dry-run", action="store_true")
    p_qseed.add_argument("--topics-file", default="topics/topics.yaml")
    p_qseed.add_argument("--limit", type=int, default=0, help="Limit number of topics (0 = all)")
    p_qseed.add_argument("--target", type=int, default=50_000)
    p_qseed.add_argument("--per-topic", type=int, default=50)
    p_qseed.add_argument("--providers", default="web,github,forum,baidu,xhs")
    p_qseed.add_argument("--workers", type=int, default=4)
    p_qseed.add_argument(
        "--provider-qps",
        default="",
        help="Per-provider QPS, e.g. 'web=2,github=0.1,forum=1,baidu=0.2,xhs=0.05'",
    )
    p_qseed.add_argument(
        "--provider-concurrency",
        default="",
        help="Per-provider concurrency, e.g. 'web=2,github=1,forum=2,baidu=1,xhs=1'",
    )
    p_qseed.add_argument(
        "--github-query-mode",
        choices=["topic", "domain_topic"],
        default="topic",
        help="GitHub query construction: 'topic' uses topic keywords; 'domain_topic' prefixes config domain query.",
    )
    p_qseed.add_argument(
        "--github-min-stars",
        type=int,
        default=None,
        help="Override GitHub stars threshold (default: topic mode=10; domain_topic mode=domain config).",
    )
    p_qseed.add_argument("--github-topic-max-terms", type=int, default=6, help="Max keyword terms used in topic mode")
    p_qseed.add_argument("--github-traverse", action="store_true")
    p_qseed.add_argument("--github-pages-per-bucket", type=int, default=1)
    p_qseed.add_argument(
        "--forum-search-mode",
        choices=["auto", "stackexchange", "tavily", "html"],
        default="auto",
        help="Forum search: auto prefers StackExchange API search; falls back to StackOverflow HTML scraping when backoff is active.",
    )
    p_qseed.add_argument(
        "--forum-site-filter",
        default="site:stackoverflow.com/questions",
        help="Tavily-only: extra query filter (recommended to keep it on StackOverflow questions).",
    )
    p_qseed.add_argument(
        "--forum-tavily-depth",
        choices=["basic", "advanced"],
        default="basic",
        help="Tavily-only: search_depth (basic uses less quota).",
    )
    p_qseed.add_argument("--loop", action="store_true")
    p_qseed.add_argument("--loop-stall-limit", type=int, default=3)
    p_qseed.add_argument("--queue", default="")
    p_qseed.add_argument("--stage", default="ingest")
    p_qseed.add_argument(
        "--state-file",
        default="runs/queue_seed_state.jsonl",
        help="Persisted search state (provider/query/page/bucket). Empty to disable.",
    )
    p_qseed.add_argument(
        "--progress-every-sec",
        type=int,
        default=60,
        help="Emit progress JSON every N seconds (0 to disable)",
    )
    p_qseed.add_argument("--drain-after", action="store_true")
    p_qseed.add_argument("--no-drain", action="store_true")

    p_qfc = sub.add_parser("queue-from-captures", help="Enqueue existing SourceArtifact JSON files under captures/")
    p_qfc.add_argument("--captures", default="captures")
    p_qfc.add_argument("--queue", default="")
    p_qfc.add_argument("--stage", default="preprocess")
    p_qfc.add_argument("--source-type", default="")
    p_qfc.add_argument("--limit", type=int, default=0)
    p_qfc.add_argument("--dry-run", action="store_true")

    p_repo_index = sub.add_parser("repo-index", help="Traverse + statically index repo into captures/*")
    p_repo_index.add_argument("--out-dir", default="captures")
    p_repo_index.add_argument("--repo", default="")
    p_repo_index.add_argument("--ref", default="")
    p_repo_index.add_argument("--max-files", type=int, default=0)
    p_repo_index.add_argument("--incremental", action="store_true")
    p_repo_index.add_argument("--state", default="")
    p_repo_index.add_argument("--big-file-bytes", type=int, default=0)
    p_repo_index.add_argument("--contracts-out", default="")
    p_repo_index.add_argument("--include", action="append", default=[])
    p_repo_index.add_argument("--exclude", action="append", default=[])

    p_repo_runbook = sub.add_parser("repo-runbook", help="Run golden workflows and write captures/run_index.jsonl")
    p_repo_runbook.add_argument("--out", default="captures/run_index.jsonl")
    p_repo_runbook.add_argument("--mode", choices=["smoke", "full"], default="smoke")
    p_repo_runbook.add_argument("--provider", default="openai")

    p_repo_query = sub.add_parser("repo-query", help="Evidence-backed search over captures/symbol_index.jsonl")
    p_repo_query.add_argument("question")
    p_repo_query.add_argument("--index", default="captures/symbol_index.jsonl")
    p_repo_query.add_argument("--top", type=int, default=8)
    p_repo_query.add_argument("--json", action="store_true")

    p_sfr = sub.add_parser("skill-from-repo", help="Generate SkillSpec + package v2 from the repo index")
    p_sfr.add_argument("--target", choices=["cli", "workflow", "module", "troubleshooting"], default="cli")
    p_sfr.add_argument("--top", type=int, default=10)
    p_sfr.add_argument("--index", default="captures/symbol_index.jsonl")
    p_sfr.add_argument("--spec-out", default="captures/skillspec")
    p_sfr.add_argument("--pkg-out", default="captures/repo_skills")
    p_sfr.add_argument("--validate", action="store_true")
    p_sfr.add_argument("--llm", action="store_true", help="Use LLM to rewrite skills into tutorial style")
    p_sfr.add_argument("--llm-model", default=str(os.environ.get("OPENAI_MODEL") or ""), help="LLM model name (optional)")
    p_sfr.add_argument("--llm-candidates", action="store_true", help="Use LLM to pick skill candidates instead of rule-based scoring")
    p_sfr.add_argument("--llm-dir-candidates", action="store_true", help="Use LLM to pick files then derive candidates")
    p_sfr.add_argument("--llm-timeout-ms", type=int, default=300_000, help="LLM request timeout in ms (default: 300000)")
    p_sfr.add_argument("--language", default="en", help="Language for LLM-generated content")

    p_repo_export = sub.add_parser("repo-export", help="Export captures/docs as a shareable bundle (optional redaction)")
    p_repo_export.add_argument("--out", required=True)
    p_repo_export.add_argument("--captures", default="captures")
    p_repo_export.add_argument("--docs", default="docs")
    p_repo_export.add_argument("--redact", action="store_true")
    p_repo_export.add_argument("--redact-urls", action="store_true")
    p_repo_export.add_argument("--max-file-bytes", type=int, default=0)

    ns, _extra = parser.parse_known_args(args_in)

    if ns.cmd == "topics-capture":
        from .scripts.topics_capture import cli_topics_capture as topics_capture_main

        return topics_capture_main(args_in[1:] if args_in and args_in[0] == "topics-capture" else None)

    if ns.cmd == "reindex-skills":
        from .scripts.reindex_skills import cli_reindex_skills as reindex_main

        return reindex_main(args_in[1:] if args_in and args_in[0] == "reindex-skills" else None)

    if ns.cmd == "backfill-verification":
        from .scripts.backfill_verification import cli_backfill_verification as backfill_verification_main

        return backfill_verification_main(args_in[1:] if args_in and args_in[0] == "backfill-verification" else None)

    if ns.cmd == "backfill-sources":
        from .scripts.backfill_sources import cli_backfill_sources as backfill_sources_main

        return backfill_sources_main(args_in[1:] if args_in and args_in[0] == "backfill-sources" else None)

    if ns.cmd == "queue-init":
        from .scripts.queue_tools import cli_queue_init

        return cli_queue_init(args_in[1:] if args_in and args_in[0] == "queue-init" else None)

    if ns.cmd == "queue-from-captures":
        from .scripts.queue_from_captures import cli_queue_from_captures

        return cli_queue_from_captures(args_in[1:] if args_in and args_in[0] == "queue-from-captures" else None)

    if ns.cmd == "queue-enqueue":
        from .scripts.queue_tools import cli_queue_enqueue

        return cli_queue_enqueue(args_in[1:] if args_in and args_in[0] == "queue-enqueue" else None)

    if ns.cmd == "queue-lease":
        from .scripts.queue_tools import cli_queue_lease

        return cli_queue_lease(args_in[1:] if args_in and args_in[0] == "queue-lease" else None)

    if ns.cmd == "queue-ack":
        from .scripts.queue_tools import cli_queue_ack

        return cli_queue_ack(args_in[1:] if args_in and args_in[0] == "queue-ack" else None)

    if ns.cmd == "queue-nack":
        from .scripts.queue_tools import cli_queue_nack

        return cli_queue_nack(args_in[1:] if args_in and args_in[0] == "queue-nack" else None)

    if ns.cmd == "queue-requeue":
        from .scripts.queue_tools import cli_queue_requeue

        return cli_queue_requeue(args_in[1:] if args_in and args_in[0] == "queue-requeue" else None)

    if ns.cmd == "queue-stats":
        from .scripts.queue_tools import cli_queue_stats

        return cli_queue_stats(args_in[1:] if args_in and args_in[0] == "queue-stats" else None)

    if ns.cmd == "queue-watch":
        from .scripts.queue_tools import cli_queue_watch

        return cli_queue_watch(args_in[1:] if args_in and args_in[0] == "queue-watch" else None)

    if ns.cmd == "queue-gc":
        from .scripts.queue_tools import cli_queue_gc

        return cli_queue_gc(args_in[1:] if args_in and args_in[0] == "queue-gc" else None)

    if ns.cmd == "queue-drain":
        from .scripts.queue_tools import cli_queue_drain

        return cli_queue_drain(args_in[1:] if args_in and args_in[0] == "queue-drain" else None)

    if ns.cmd == "queue-seed":
        from .scripts.queue_seed import cli_queue_seed
        from .env import load_dotenv

        load_dotenv(repo_root)

        return cli_queue_seed(args_in[1:] if args_in and args_in[0] == "queue-seed" else None)

    if ns.cmd == "import-littlecrawler":
        from .scripts.import_littlecrawler import cli_import_littlecrawler

        return cli_import_littlecrawler(args_in[1:] if args_in and args_in[0] == "import-littlecrawler" else None)

    if ns.cmd == "capture":
        topic_raw = str(ns.topic or "").strip()
        if not topic_raw:
            parser.error("topic is required")

        total = ns.total
        m = re.match(r"^(.*)@(\d+)$", topic_raw)
        if m and total is None:
            topic_raw = m.group(1).strip()
            total = int(m.group(2))

        from .skills.generate import capture as capture_run

        publish = bool(ns.publish or ns.publish_overwrite) or str(os.environ.get("LANGSKILLS_PUBLISH") or "").strip() == "1"
        publish_overwrite = bool(ns.publish_overwrite) or str(os.environ.get("LANGSKILLS_PUBLISH_OVERWRITE") or "").strip() == "1"
        if publish_overwrite:
            publish = True

        offline = _env_bool("LANGSKILLS_OFFLINE", False)
        pipeline = _env_bool("LANGSKILLS_PIPELINE", True)
        auto_improve = _env_bool("LANGSKILLS_AUTO_IMPROVE", True)

        raw_progress = "pretty" if bool(getattr(ns, "pretty", False)) else (ns.progress or "")
        if not raw_progress:
            raw_progress = str(os.environ.get("LANGSKILLS_PROGRESS") or "").strip()
        if not raw_progress and str(os.environ.get("LANGSKILLS_PRETTY") or "").strip() == "1":
            raw_progress = "pretty"
        progress_mode = str(raw_progress or "").strip().lower()
        pretty = progress_mode in {"pretty", "tui"}

        run_dir = capture_run(
            repo_root=repo_root,
            topic=topic_raw,
            domain=ns.domain,
            all_domains=bool(ns.all),
            total=total,
            per_source=ns.per_source,
            provider=None,
            offline=offline,
            publish=publish,
            publish_overwrite=publish_overwrite,
            pretty=pretty,
        )

        # Node-compat behavior: optionally run improve/pipeline before publishing.
        from .env import load_dotenv
        from .llm.factory import create_llm_from_env

        load_dotenv(repo_root)
        llm = create_llm_from_env(provider_override=None)

        if pipeline:
            from .postprocess.run import postprocess_run
            from .utils.fs import list_skill_dirs

            print("\n=== Pipeline: postprocess ===")
            postprocess_run(repo_root=repo_root, run_target=str(run_dir), llm=llm)

            print("\n=== Pipeline: improve ===")
            if not auto_improve:
                print("SKIP: auto improve disabled (LANGSKILLS_AUTO_IMPROVE=0).")
            else:
                from .skills.improve import improve_run_in_place

                max_passes = max(1, min(5, _env_int("LANGSKILLS_IMPROVE_PASSES", 3)))
                out = improve_run_in_place(repo_root=repo_root, run_target=str(run_dir), llm=llm, max_passes=max_passes)
                if int(out.get("lintCount") or 0) > 0 or int(out.get("missingCount") or 0) > 0:
                    print("WARN: improve finished but still has lint/missing suggestions; consider re-running improve.")

            print("\n=== Pipeline: validate (run skills) ===")
            try:
                from .scripts.validate_skills import validate_skills
            except ImportError:
                validate_skills = None
            skills_root = Path(run_dir) / "skills"
            if validate_skills is None:
                print("SKIP: validate_skills module not available; skipping validation.")
            elif skills_root.exists():
                errors, warnings = validate_skills(repo_root=repo_root, root=skills_root, strict=True, check_package=True)
                for w in warnings:
                    print(f"WARN: {w}")
                for e in errors:
                    print(f"FAIL: {e}")
            else:
                print("WARN: No skills directory generated; skipping validation.")

            if validate_skills is not None:
                combos_root = Path(run_dir) / "analysis"
                if combos_root.exists() and list_skill_dirs(combos_root):
                    print("\n=== Pipeline: validate (combo skills, non-strict) ===")
                    combo_errors, combo_warnings = validate_skills(repo_root=repo_root, root=combos_root, strict=False, check_package=False)
                    for w in combo_warnings:
                        print(f"WARN: {w}")
                    for e in combo_errors:
                        print(f"FAIL: {e}")
        elif auto_improve:
            print("\n=== Auto: improve ===")
            from .skills.improve import improve_run_in_place

            max_passes = max(1, min(5, _env_int("LANGSKILLS_IMPROVE_PASSES", 3)))
            out = improve_run_in_place(repo_root=repo_root, run_target=str(run_dir), llm=llm, max_passes=max_passes)
            if int(out.get("lintCount") or 0) > 0 or int(out.get("missingCount") or 0) > 0:
                print("WARN: improve finished but still has lint/missing suggestions; consider re-running improve.")

        if publish:
            from .skills.publish import publish_run_to_skills_library

            p = publish_run_to_skills_library(repo_root=repo_root, run_dir=run_dir, overwrite=publish_overwrite)
            print(f"\nPublished to skills/: published={p['published']} skipped={p['skipped']} total_run_skills={p['total']}")

        print(run_dir.as_posix())
        return 0

    if ns.cmd == "search":
        import json

        from .env import load_dotenv

        load_dotenv(repo_root)

        engine = str(ns.engine or "").strip().lower()
        query = str(ns.query or "").strip()
        limit = max(1, min(200, int(ns.limit or 10)))

        urls: list[str] = []
        warnings: list[str] = []
        meta: dict[str, object] = {}
        emit = lambda msg: print(str(msg), file=sys.stderr, flush=True)
        if engine == "web":
            from .sources.web_search import search_web_urls

            info: dict[str, object] = {}
            urls = search_web_urls(query, limit=limit, info=info)  # type: ignore[arg-type]
            if info:
                meta["info"] = info
        elif engine == "tavily":
            from .sources.web_search import search_web_urls_with_tavily

            info = {}
            urls = search_web_urls_with_tavily(query, limit=limit, info=info)  # type: ignore[arg-type]
            if info:
                meta["info"] = info
            if not urls:
                status = str(info.get("status") or "").strip() if isinstance(info, dict) else ""
                if status == "error":
                    warnings.append("No results (Tavily error; check quota/API key).")
                else:
                    warnings.append("No results (requires Tavily API key + quota).")
        elif engine == "baidu":
            from .sources.baidu import search_baidu_urls

            urls = search_baidu_urls(query, limit=limit)
            if not urls:
                warnings.append("No results (requires Playwright + browsers, and network access).")
        elif engine == "github":
            from .sources.github import github_search_top_repos

            repos = github_search_top_repos(query=query, per_page=limit, min_stars=10)
            urls = [r.html_url for r in repos if str(getattr(r, "html_url", "") or "").strip()]
            if repos:
                top = repos[0]
                meta["top_repo"] = {
                    "full_name": top.full_name,
                    "url": top.html_url,
                    "stars": top.stargazers_count,
                    "language": top.language,
                    "default_branch": top.default_branch,
                    "license_spdx": top.license_spdx,
                }
            if not urls:
                warnings.append("No results (GitHub Search API rate-limited; add GITHUB_TOKEN and retry).")
        elif engine == "forum":
            from .sources.stackoverflow import stack_search_top_questions

            qs = stack_search_top_questions(q=query, tagged=None, pagesize=limit)
            urls = [q.link for q in qs if str(getattr(q, "link", "") or "").strip()]
            if qs:
                meta["sample"] = {"question_id": qs[0].question_id, "title": qs[0].title, "url": qs[0].link}
            if not urls:
                warnings.append("No results (StackExchange may throttle; add STACKEXCHANGE_KEY to reduce throttling).")
        elif engine == "arxiv":
            from .sources.arxiv import search_arxiv

            items = search_arxiv(query, max_results=limit)
            urls = [str(it.get("primary_url") or "").strip() for it in (items or []) if isinstance(it, dict)]
            urls = [u for u in urls if u]
            if items:
                top0 = items[0] if isinstance(items[0], dict) else {}
                meta["top_entry"] = {
                    "arxiv_id": str(top0.get("arxiv_id") or ""),
                    "title": str(top0.get("title") or ""),
                    "primary_url": str(top0.get("primary_url") or ""),
                    "pdf_url": str(top0.get("pdf_url") or ""),
                }
            if not urls:
                warnings.append("No results (arXiv API returned empty).")
        elif engine == "zhihu":
            from .sources.zhihu import search_zhihu_urls

            auth: dict[str, object] = {}
            urls = search_zhihu_urls(query, limit=limit, info=auth, emit=emit)  # type: ignore[arg-type]
            if auth:
                meta["auth"] = auth
            if not urls:
                warnings.append("No results (requires Playwright + browsers, and may require login).")
        elif engine == "xhs":
            from .sources.xhs import search_xhs_urls

            auth = {}
            urls = search_xhs_urls(query, limit=limit, info=auth, emit=emit)  # type: ignore[arg-type]
            if auth:
                meta["auth"] = auth
            if not urls:
                warnings.append("No results (requires Playwright + browsers, and may require login).")
        else:
            parser.error(f"Unknown search engine: {engine}")

        if bool(getattr(ns, "enqueue", False)) and urls:
            from .queue import QueueSettings, QueueStore

            settings = QueueSettings.from_env(repo_root_path=repo_root)
            if str(getattr(ns, "queue", "") or "").strip():
                settings.path = Path(str(getattr(ns, "queue") or ""))
            if not settings.path.is_absolute():
                settings.path = (repo_root / settings.path).resolve()
            queue = QueueStore(settings.path)
            queue.init_db()
            for u in urls:
                queue.enqueue(
                    source_id="",
                    source_type=engine,
                    source_url=u,
                    stage=str(getattr(ns, "stage") or "ingest"),
                    domain=str(getattr(ns, "domain") or ""),
                    max_attempts=settings.max_attempts,
                    config_snapshot={"engine": engine, "query": query},
                    extra={"query": query},
                )
            meta["enqueue"] = {"queue": str(queue.db_path), "enqueued": len(urls)}

        print(
            json.dumps(
                {
                    "engine": engine,
                    "query": query,
                    "count": len(urls),
                    "urls": urls,
                    "warnings": warnings,
                    **(meta if meta else {}),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if ns.cmd == "fetch":
        import json

        from .config import canonicalize_source_url
        from .env import load_dotenv
        from .sources.router import fetch_text
        from .utils.fs import ensure_dir, write_json_atomic, write_text_atomic
        from .utils.hashing import sha256_hex

        load_dotenv(repo_root)

        engine = str(ns.engine or "").strip().lower()
        url = str(ns.url or "").strip()
        timeout_ms = max(2_000, min(180_000, int(ns.timeout_ms or 25_000)))

        if not url:
            parser.error("fetch: url is required")

        emit = lambda msg: print(str(msg), file=sys.stderr, flush=True)

        auth: dict[str, object] = {}
        result = None
        fetch_error = ""
        try:
            result = fetch_text(url, engine=engine, timeout_ms=timeout_ms, info=auth, emit=emit)
        except ValueError:
            parser.error(f"Unknown fetch engine: {engine}")
        except Exception as e:
            fetch_error = f"{type(e).__name__}: {e}"

        out_root = str(getattr(ns, "out_dir", "") or "").strip()
        out_dir = ""
        if out_root:
            src_url = canonicalize_source_url(url) or url
            source_id = sha256_hex(src_url)
            dest = Path(out_root)
            if not dest.is_absolute():
                dest = (repo_root / dest).resolve()
            dest = dest / source_id
            ensure_dir(dest)
            if result is not None:
                write_text_atomic(dest / "raw.html", str(result.raw_html or ""))
                write_text_atomic(dest / "text.txt", str(result.extracted_text or ""))
            meta = {
                "ok": bool(result is not None and not fetch_error),
                "error": fetch_error,
                "url": url,
                "final_url": str(getattr(result, "final_url", "") or "") if result is not None else "",
                "title": str(getattr(result, "title", "") or "") if result is not None else "",
                "platform": str(getattr(result, "platform", "") or "") if result is not None else "",
                "used_playwright": bool(getattr(result, "used_playwright", False)) if result is not None else False,
                "raw_html_chars": len(str(result.raw_html or "")) if result is not None else 0,
                "extracted_text_chars": len(str(result.extracted_text or "")) if result is not None else 0,
                "auth": auth if auth else {},
            }
            write_json_atomic(dest / "meta.json", meta)
            out_dir = dest.as_posix()

        if result is None:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "engine": engine,
                        "url": url,
                        "error": fetch_error or "fetch_failed",
                        "out_dir": out_dir,
                        "auth": auth if auth else {},
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1

        extracted = str(result.extracted_text or "")
        excerpt = extracted.strip()[:8000]
        payload: dict[str, object] = {
            "ok": True,
            "engine": engine,
            "url": url,
            "final_url": str(getattr(result, "final_url", "") or ""),
            "title": str(getattr(result, "title", "") or ""),
            "platform": str(getattr(result, "platform", "") or ""),
            "used_playwright": bool(getattr(result, "used_playwright", False)),
            "raw_html_chars": len(str(result.raw_html or "")),
            "extracted_text_chars": len(extracted),
            "out_dir": out_dir,
            "auth": auth if auth else {},
        }
        if bool(getattr(ns, "include_text", False)):
            payload["extracted_text"] = extracted
        else:
            payload["extracted_excerpt"] = excerpt

        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if ns.cmd == "auth":
        import json

        from .env import load_dotenv
        from .sources.playwright_utils import playwright_page, resolve_auth_dir

        load_dotenv(repo_root)

        platform = str(ns.platform or "").strip().lower()
        timeout_sec = max(30, min(3600, int(ns.timeout_sec or 300)))
        timeout_ms = timeout_sec * 1000

        emit = lambda msg: print(str(msg), file=sys.stderr, flush=True)
        auth: dict[str, object] = {}

        if platform == "zhihu":
            from .sources.zhihu import ensure_zhihu_login, zhihu_requires_headful

            headless = False if zhihu_requires_headful() else None
            with playwright_page(platform="zhihu", timeout_ms=timeout_ms, headless=headless) as page:
                ok = ensure_zhihu_login(page, timeout_sec=timeout_sec, emit=emit, info=auth, headless=False)  # type: ignore[arg-type]
                if not ok:
                    return 1
                default_path = resolve_auth_dir() / "zhihu_storage_state.json"
                raw_path = str(getattr(ns, "storage_state", "") or "").strip()
                state_path = Path(raw_path) if raw_path else default_path
                if not state_path.is_absolute():
                    state_path = (repo_root / state_path).resolve()
                try:
                    state_path.parent.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
                page.context.storage_state(path=str(state_path))
                auth["storage_state_path"] = state_path.as_posix()

        elif platform == "xhs":
            from .sources.xhs import ensure_xhs_login, xhs_requires_headful

            headless = False if xhs_requires_headful() else None
            with playwright_page(platform="xhs", timeout_ms=timeout_ms, headless=headless) as page:
                ok = ensure_xhs_login(page, timeout_sec=timeout_sec, emit=emit, info=auth, headless=False)  # type: ignore[arg-type]
                if not ok:
                    return 1
                default_path = resolve_auth_dir() / "xhs_storage_state.json"
                raw_path = str(getattr(ns, "storage_state", "") or "").strip()
                state_path = Path(raw_path) if raw_path else default_path
                if not state_path.is_absolute():
                    state_path = (repo_root / state_path).resolve()
                try:
                    state_path.parent.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
                page.context.storage_state(path=str(state_path))
                auth["storage_state_path"] = state_path.as_posix()
        else:
            parser.error(f"Unknown auth platform: {platform}")

        print(json.dumps({"platform": platform, "auth": auth}, ensure_ascii=False, indent=2))
        return 0

    if ns.cmd == "sources-audit":
        import json
        import time

        from .env import load_dotenv
        from .scripts.source_audit import run_sources_audit
        from .utils.fs import write_text_atomic

        load_dotenv(repo_root)

        query = str(ns.query or "").strip() or "python"
        limit = int(ns.limit or 5)
        timeout_ms = int(ns.timeout_ms or 25_000)
        webpage_conc = int(getattr(ns, "webpage_concurrency", 6) or 6)

        out_dir = str(getattr(ns, "out_dir", "") or "").strip()
        if not out_dir:
            ts = time.strftime("%Y%m%d_%H%M%S", time.localtime())
            out_dir = f"captures/source_audit/{ts}"

        payload = run_sources_audit(
            repo_root=repo_root,
            query=query,
            out_dir=out_dir,
            timeout_ms=timeout_ms,
            limit=limit,
            webpage_concurrency=webpage_conc,
        )

        report_path = str(getattr(ns, "report", "") or "").strip()
        if report_path and not bool(getattr(ns, "no_report", False)):
            p = Path(report_path)
            if not p.is_absolute():
                p = (repo_root / p).resolve()
            # The script always writes sources_audit.md under out_dir; mirror it into docs for easy reading.
            out_root = Path(out_dir)
            if not out_root.is_absolute():
                out_root = (repo_root / out_root).resolve()
            src_md = out_root / "sources_audit.md"
            if src_md.exists():
                write_text_atomic(p, src_md.read_text(encoding="utf-8"))

        if bool(getattr(ns, "json", False)):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(
                json.dumps(
                    {
                        "run_id": payload.get("run_id"),
                        "out_dir": str(out_dir),
                        "json": str(Path(out_dir) / "sources_audit.json"),
                        "md": str(Path(out_dir) / "sources_audit.md"),
                        "docs_report": report_path if (report_path and not bool(getattr(ns, "no_report", False))) else "",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        return 0

    if ns.cmd == "dir-docs":
        import json

        from .scripts.dir_docs import run_dir_docs

        roots_raw = str(getattr(ns, "roots", "") or "").strip() or "core,scripts"
        roots = [s.strip() for s in roots_raw.split(",") if s.strip()]
        filename = str(getattr(ns, "filename", "") or "").strip() or "DIR_DOCS.md"
        dry_run = bool(getattr(ns, "dry_run", False))

        payload = run_dir_docs(repo_root=repo_root, roots=roots, filename=filename, dry_run=dry_run)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if ns.cmd == "improve":
        from .env import load_dotenv
        from .llm.factory import create_llm_from_env
        from .skills.improve import improve_run_in_place

        load_dotenv(repo_root)
        llm = create_llm_from_env(provider_override=None)
        max_passes = max(1, min(5, _env_int("LANGSKILLS_IMPROVE_PASSES", 3)))
        out = improve_run_in_place(repo_root=repo_root, run_target=ns.run_target, llm=llm, max_passes=max_passes)
        print(f"OK: improve {Path(out['run_dir']).name}")
        return 0

    if ns.cmd == "postprocess":
        from .env import load_dotenv
        from .llm.factory import create_llm_from_env
        from .postprocess.run import postprocess_run

        load_dotenv(repo_root)
        llm = create_llm_from_env(provider_override=None)
        out = postprocess_run(repo_root=repo_root, run_target=ns.run_target, llm=llm)
        # Print a short success path (useful for scripting).
        run_id = str(out.get("run_id") or ns.run_target)
        print(f"OK: postprocess {run_id}")
        return 0

    if ns.cmd == "validate":
        try:
            from .scripts.validate_skills import validate_skills
        except ImportError:
            print("ERROR: validate_skills module is not available.")
            return 1

        max_skills = int(getattr(ns, "max_skills", 0) or 0)
        errors, warnings = validate_skills(
            repo_root=repo_root,
            root=ns.root,
            strict=bool(ns.strict),
            check_package=bool(ns.check_package),
            max_skills=(max_skills if max_skills > 0 else None),
        )
        for w in warnings:
            print(f"WARN: {w}")
        for e in errors:
            print(f"FAIL: {e}")
        print(f"\nSummary: warnings={len(warnings)} errors={len(errors)} strict={bool(ns.strict)} package={bool(ns.check_package)}")
        return 1 if errors else 0

    if ns.cmd == "build-site":
        from .scripts.build_site import build_site

        out_json, out_html = build_site(repo_root=repo_root)
        print(f"Wrote: {out_json.relative_to(repo_root).as_posix()}")
        print(f"Wrote: {out_html.relative_to(repo_root).as_posix()}")
        return 0

    if ns.cmd == "self-check":
        from .scripts.self_check import run_self_check

        return run_self_check(repo_root=repo_root, skip_remote=bool(ns.skip_remote))

    if ns.cmd == "runner":
        from .scripts.runner import cli_runner as runner_main

        return runner_main(
            [
                "--state",
                ns.state,
                *([] if not ns.queue else ["--queue", ns.queue]),
                *([] if not ns.once else ["--once"]),
                "--interval-ms",
                str(ns.interval_ms),
                "--rate-ms",
                str(ns.rate_ms),
                "--task-timeout-ms",
                str(ns.task_timeout_ms),
                "--max-tasks",
                str(ns.max_tasks),
                "--max-attempts",
                str(ns.max_attempts),
                *([] if not ns.domain else ["--domain", ns.domain]),
                *([] if not ns.all else ["--all"]),
                *([] if not ns.topic else ["--topic", ns.topic]),
                *([] if not ns.topics_file else ["--topics-file", ns.topics_file]),
                *([] if not ns.topics_limit else ["--topics-limit", str(ns.topics_limit)]),
                *([] if not ns.publish_overwrite else ["--publish-overwrite"]),
                *([] if not ns.strict else ["--strict"]),
                *([] if not ns.no_discover else ["--no-discover"]),
                "--discover-providers",
                str(ns.discover_providers),
                *([] if not ns.ignore_license_policy else ["--ignore-license-policy"]),
                *([] if not ns.enforce_license_policy else ["--enforce-license-policy"]),
                *([] if not ns.max_stage else ["--max-stage", ns.max_stage]),
                *([] if not ns.no_llm else ["--no-llm"]),
                *([] if not ns.worker_id else ["--worker-id", ns.worker_id]),
                *([] if not getattr(ns, "verbose", False) else ["--verbose"]),
                *([] if not getattr(ns, "source_type", "") else ["--source-type", str(getattr(ns, "source_type") or "")]),
            ]
        )

    if ns.cmd == "auto-pr":
        from .scripts.auto_pr import cli_auto_pr as auto_pr_main

        return auto_pr_main(
            [
                *([] if not ns.push else ["--push"]),
                *([] if not ns.pr else ["--pr"]),
                "--remote",
                ns.remote,
                *([] if not ns.base else ["--base", ns.base]),
                *([] if not ns.branch else ["--branch", ns.branch]),
                "--message",
                ns.message,
                "--paths",
                ns.paths,
            ]
        )

    if ns.cmd == "backfill-package-v2":
        from .scripts.backfill_package_v2 import cli_backfill_package_v2 as backfill_main

        return backfill_main(
            [
                "--root",
                ns.root,
                *([] if not ns.provider else ["--provider", ns.provider]),
                *([] if not ns.limit else ["--limit", str(ns.limit)]),
                *([] if not ns.overwrite else ["--overwrite"]),
            ]
        )

    if ns.cmd == "arxiv-pipeline":
        from .scripts.arxiv_pipeline import cli_arxiv_pipeline
        from .env import load_dotenv

        load_dotenv(repo_root)
        return cli_arxiv_pipeline(args_in[1:] if args_in and args_in[0] == "arxiv-pipeline" else None)

    if ns.cmd == "journal-pipeline":
        import types as _types_mod
        from .skills import generate as _gen_mod
        if "core.skills.generate.core_impl" not in sys.modules:
            _alias = _types_mod.ModuleType("core.skills.generate.core_impl")
            _alias.__dict__.update({k: v for k, v in _gen_mod.__dict__.items()})
            sys.modules["core.skills.generate.core_impl"] = _alias

        from .scripts.journal_pipeline.cli import cli_journal_pipeline
        from .env import load_dotenv

        load_dotenv(repo_root)
        return cli_journal_pipeline(args_in[1:] if args_in and args_in[0] == "journal-pipeline" else None)

    if ns.cmd == "repo-index":
        from .scripts.repo_index import cli_repo_index as repo_index_main

        args = ["--out-dir", ns.out_dir]
        if str(ns.repo or "").strip():
            args += ["--repo", ns.repo]
        if str(ns.ref or "").strip():
            args += ["--ref", ns.ref]
        if int(ns.max_files or 0) > 0:
            args += ["--max-files", str(int(ns.max_files))]
        if ns.incremental:
            args.append("--incremental")
        if str(ns.state or "").strip():
            args += ["--state", ns.state]
        if int(ns.big_file_bytes or 0) > 0:
            args += ["--big-file-bytes", str(int(ns.big_file_bytes))]
        if str(ns.contracts_out or "").strip():
            args += ["--contracts-out", ns.contracts_out]
        for x in ns.include or []:
            args += ["--include", x]
        for x in ns.exclude or []:
            args += ["--exclude", x]
        return repo_index_main(args)

    if ns.cmd == "repo-runbook":
        from .scripts.repo_runbook import cli_repo_runbook as runbook_main

        return runbook_main(["--out", ns.out, "--mode", ns.mode, "--provider", ns.provider])

    if ns.cmd == "repo-query":
        from .scripts.repo_query import cli_repo_query as repo_query_main

        args = [ns.question, "--index", ns.index, "--top", str(ns.top)]
        if ns.json:
            args.append("--json")
        return repo_query_main(args)

    if ns.cmd == "skill-from-repo":
        from .scripts.skill_from_repo import cli_skill_from_repo as sfr_main

        args = [
            "--target",
            ns.target,
            "--top",
            str(ns.top),
            "--index",
            ns.index,
            "--spec-out",
            ns.spec_out,
            "--pkg-out",
            ns.pkg_out,
            "--llm-timeout-ms",
            str(int(getattr(ns, "llm_timeout_ms", 300_000) or 300_000)),
        ]
        if ns.validate:
            args.append("--validate")
        if getattr(ns, "llm", False):
            args.append("--llm")
        if getattr(ns, "llm_candidates", False):
            args.append("--llm-candidates")
        if getattr(ns, "llm_dir_candidates", False):
            args.append("--llm-dir-candidates")
        if getattr(ns, "language", None):
            args += ["--language", ns.language]
        if getattr(ns, "llm_model", None):
            args += ["--llm-model", ns.llm_model]
        return sfr_main(args)

    if ns.cmd == "repo-export":
        from .scripts.repo_export import cli_repo_export as export_main

        args = ["--out", ns.out, "--captures", ns.captures, "--docs", ns.docs]
        if ns.redact:
            args.append("--redact")
        if ns.redact_urls:
            args.append("--redact-urls")
        if int(ns.max_file_bytes or 0) > 0:
            args += ["--max-file-bytes", str(int(ns.max_file_bytes))]
        return export_main(args)

    if ns.cmd == "skill-search":
        from .search import cli_skill_search

        raw_args = [ns.query] if ns.query else []
        raw_args += ["--top", str(ns.top)]
        if ns.domains:
            raw_args.append("--domains")
        if ns.kinds:
            raw_args.append("--kinds")
        if ns.show_path:
            raw_args.append("--show-path")
        if ns.domain:
            raw_args += ["--domain", ns.domain]
        if ns.kind:
            raw_args += ["--kind", ns.kind]
        if ns.source_type:
            raw_args += ["--source-type", ns.source_type]
        if ns.min_score:
            raw_args += ["--min-score", str(ns.min_score)]
        if ns.content:
            raw_args.append("--content")
        if ns.max_chars:
            raw_args += ["--max-chars", str(ns.max_chars)]
        fmt = "brief" if ns.brief else ns.format
        raw_args += ["--format", fmt]
        return cli_skill_search(raw_args)

    if ns.cmd == "build-bundle":
        from .scripts.build_bundle import cli_build_bundle

        raw_args = ["--type", ns.type, "--out", ns.out, "--workers", str(ns.workers)]
        if ns.version:
            raw_args += ["--version", ns.version]
        if ns.split_by_domain:
            raw_args.append("--split-by-domain")
        if ns.domain:
            raw_args += ["--domain", ns.domain]
        if ns.min_score:
            raw_args += ["--min-score", str(ns.min_score)]
        return cli_build_bundle(raw_args)

    if ns.cmd == "bundle-install":
        from .scripts.bundle_install import cli_bundle_install

        raw_args = ["--release", ns.release, "--bundle", ns.bundle]
        if ns.repo:
            raw_args += ["--repo", ns.repo]
        if ns.check:
            raw_args.append("--check")
        if getattr(ns, "domain", ""):
            raw_args += ["--domain", ns.domain]
        if getattr(ns, "auto", False):
            raw_args.append("--auto")
        if getattr(ns, "project_dir", ""):
            raw_args += ["--project-dir", ns.project_dir]
        return cli_bundle_install(raw_args)

    if ns.cmd == "bundle-rebuild":
        from .skills.index_sqlite import cli_rebuild_index

        return cli_rebuild_index([])

    parser.error(f"Unknown cmd: {ns.cmd}")
    return 2
