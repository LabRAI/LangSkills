#!/usr/bin/env node
/* eslint-disable no-console */

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

process.stdout.on("error", (err) => {
  if (err && err.code === "EPIPE") process.exit(0);
});

function exists(filePath) {
  try {
    fs.accessSync(filePath, fs.constants.F_OK);
    return true;
  } catch {
    return false;
  }
}

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function readText(filePath) {
  return fs.readFileSync(filePath, "utf8");
}

function writeJsonAtomic(filePath, obj) {
  ensureDir(path.dirname(filePath));
  const tmp = `${filePath}.${crypto.randomBytes(4).toString("hex")}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 2) + "\n", "utf8");
  fs.renameSync(tmp, filePath);
}

function stripBom(text) {
  if (!text) return text;
  return text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
}

function unquoteScalar(value) {
  let v = String(value || "").trim();
  if (!v) return "";
  if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
    v = v.slice(1, -1);
  }
  return v;
}

function parseInlineYamlList(value) {
  const v = String(value || "").trim();
  if (!v) return null;
  if (v === "[]") return [];
  if (v.startsWith("[") && v.endsWith("]")) {
    const inner = v.slice(1, -1).trim();
    if (!inner) return [];
    return inner
      .split(",")
      .map((x) => unquoteScalar(x))
      .map((x) => x.trim())
      .filter(Boolean);
  }
  return [unquoteScalar(v)];
}

function parseDurationToMs(raw) {
  const v = String(raw || "").trim();
  if (!v) return null;
  const m = v.match(/^(\d+(?:\.\d+)?)\s*([smhd])$/i);
  if (!m) return null;
  const n = Number(m[1]);
  const unit = String(m[2] || "").toLowerCase();
  if (!Number.isFinite(n) || n <= 0) return null;
  const mult = unit === "s" ? 1000 : unit === "m" ? 60_000 : unit === "h" ? 3_600_000 : unit === "d" ? 86_400_000 : null;
  if (!mult) return null;
  return Math.floor(n * mult);
}

function parseDomainPolicyAndSources(yamlText) {
  const text = stripBom(String(yamlText || "")).replace(/\r\n/g, "\n");
  const lines = text.split("\n");

  let domain = null;
  const sourcePolicy = { allow_domains: [], deny_domains: [] };
  const sources = { primary: [] };

  let inSourcePolicy = false;
  let inSources = false;
  let inSourcesPrimary = false;
  let collectAllow = false;
  let collectDeny = false;

  for (const rawLine of lines) {
    const line = rawLine.replace(/\s+$/, "");
    if (!line.trim()) continue;
    if (/^\s*#/.test(line)) continue;

    const domainMatch = line.match(/^domain:\s*(.+?)\s*$/);
    if (domainMatch && !domain) {
      domain = unquoteScalar(domainMatch[1]);
      continue;
    }

    if (/^source_policy:\s*$/.test(line)) {
      inSourcePolicy = true;
      inSources = false;
      inSourcesPrimary = false;
      collectAllow = false;
      collectDeny = false;
      continue;
    }

    if (/^sources:\s*$/.test(line)) {
      inSources = true;
      inSourcePolicy = false;
      inSourcesPrimary = false;
      continue;
    }

    if (inSources) {
      const primaryMatch = line.match(/^\s*primary:\s*(.*?)\s*$/);
      if (primaryMatch) {
        const parsed = parseInlineYamlList(primaryMatch[1]);
        if (parsed !== null) {
          sources.primary = parsed;
          inSourcesPrimary = false;
        } else {
          sources.primary = [];
          inSourcesPrimary = true;
        }
        continue;
      }
      if (inSourcesPrimary) {
        const m = line.match(/^\s*-\s*(.+?)\s*$/);
        if (m) {
          sources.primary.push(unquoteScalar(m[1]));
          continue;
        }
        inSourcesPrimary = false;
      }
    }

    if (inSourcePolicy) {
      if (collectAllow) {
        const m = line.match(/^\s*-\s*(.+?)\s*$/);
        if (m) {
          sourcePolicy.allow_domains.push(unquoteScalar(m[1]));
          continue;
        }
        collectAllow = false;
      }
      if (collectDeny) {
        const m = line.match(/^\s*-\s*(.+?)\s*$/);
        if (m) {
          sourcePolicy.deny_domains.push(unquoteScalar(m[1]));
          continue;
        }
        collectDeny = false;
      }

      const allowMatch = line.match(/^\s*allow_domains:\s*(.*?)\s*$/);
      if (allowMatch) {
        const parsed = parseInlineYamlList(allowMatch[1]);
        sourcePolicy.allow_domains = parsed === null ? [] : parsed;
        collectAllow = parsed === null;
        continue;
      }
      const denyMatch = line.match(/^\s*deny_domains:\s*(.*?)\s*$/);
      if (denyMatch) {
        const parsed = parseInlineYamlList(denyMatch[1]);
        sourcePolicy.deny_domains = parsed === null ? [] : parsed;
        collectDeny = parsed === null;
        continue;
      }
    }
  }

  if (!domain) throw new Error("Invalid domain config: missing 'domain:'");
  return { domain, source_policy: sourcePolicy, sources };
}

function parseSourcesRegistry(yamlText) {
  const text = stripBom(String(yamlText || "")).replace(/\r\n/g, "\n");
  const lines = text.split("\n");

  const sources = [];
  let inSources = false;
  let current = null;
  let inSeeds = false;
  let inInclude = false;
  let inRefresh = false;

  for (const rawLine of lines) {
    const line = rawLine.replace(/\s+$/, "");
    if (!line.trim()) continue;
    if (/^\s*#/.test(line)) continue;

    if (/^sources:\s*$/.test(line)) {
      inSources = true;
      continue;
    }
    if (!inSources) continue;

    const itemStart = line.match(/^\s*-\s*id:\s*(.+?)\s*$/);
    if (itemStart) {
      if (current) sources.push(current);
      current = { id: unquoteScalar(itemStart[1]), seeds: [], include_globs: [], refresh: {} };
      inSeeds = false;
      inInclude = false;
      inRefresh = false;
      continue;
    }
    if (!current) continue;

    if (/^\s*seeds:\s*$/.test(line)) {
      current.seeds = [];
      inSeeds = true;
      inInclude = false;
      inRefresh = false;
      continue;
    }
    if (/^\s*include_globs:\s*$/.test(line)) {
      current.include_globs = [];
      inInclude = true;
      inSeeds = false;
      inRefresh = false;
      continue;
    }
    if (/^\s*refresh:\s*$/.test(line)) {
      current.refresh = current.refresh || {};
      inRefresh = true;
      inSeeds = false;
      inInclude = false;
      continue;
    }

    if (inSeeds) {
      const m = line.match(/^\s*-\s*(.+?)\s*$/);
      if (m) {
        current.seeds.push(unquoteScalar(m[1]));
        continue;
      }
      inSeeds = false;
    }
    if (inInclude) {
      const m = line.match(/^\s*-\s*(.+?)\s*$/);
      if (m) {
        current.include_globs.push(unquoteScalar(m[1]));
        continue;
      }
      inInclude = false;
    }

    const propMatch = line.match(/^\s*([A-Za-z0-9_]+):\s*(.+?)\s*$/);
    if (propMatch) {
      const key = propMatch[1];
      const value = unquoteScalar(propMatch[2]);
      if (inRefresh) current.refresh[key] = value;
      else current[key] = value;
    }
  }
  if (current) sources.push(current);
  return sources;
}

function readJsonMaybe(filePath) {
  if (!exists(filePath)) return null;
  try {
    return JSON.parse(readText(filePath));
  } catch {
    return null;
  }
}

function usage(exitCode = 0) {
  const msg = `
Usage:
  node scripts/verify-longrun.js --domain <domain> --run-id <run-id>
    [--runs-dir runs] [--days 90] [--pages-per-day 500]
    [--out <path>] [--strict]

What it verifies (deterministic, file-based):
  - Tier0 repos ingested completely: runs/<run-id>/repo_state.json
  - Tier1 crawl backlog >= days * pages_per_day (or crawler loop enabled)
  - Extractor produced candidates and state/log files exist
  - Metrics files exist for long-running visibility
`.trim();
  if (exitCode === 0) console.log(msg);
  else console.error(msg);
  process.exit(exitCode);
}

function parseArgs(argv) {
  const args = {
    domain: null,
    runId: null,
    runsDir: "runs",
    days: 90,
    pagesPerDay: 500,
    out: null,
    strict: false,
  };

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--domain") {
      args.domain = argv[i + 1] || null;
      i++;
    } else if (a === "--run-id") {
      args.runId = argv[i + 1] || null;
      i++;
    } else if (a === "--runs-dir") {
      args.runsDir = argv[i + 1] || args.runsDir;
      i++;
    } else if (a === "--days") {
      args.days = Number(argv[i + 1] || "90");
      i++;
    } else if (a === "--pages-per-day") {
      args.pagesPerDay = Number(argv[i + 1] || "500");
      i++;
    } else if (a === "--out") {
      args.out = argv[i + 1] || null;
      i++;
    } else if (a === "--strict") {
      args.strict = true;
    } else if (a === "-h" || a === "--help") usage(0);
    else throw new Error(`Unknown arg: ${a}`);
  }

  if (!args.domain) usage(2);
  if (!args.runId) usage(2);
  if (!Number.isFinite(args.days) || args.days <= 0) throw new Error("Invalid --days");
  if (!Number.isFinite(args.pagesPerDay) || args.pagesPerDay <= 0) throw new Error("Invalid --pages-per-day");
  return args;
}

function pct(n) {
  if (!Number.isFinite(n)) return "0%";
  return `${(n * 100).toFixed(2)}%`;
}

function makeCheck(name, ok, details, meta = null) {
  return { name, ok: !!ok, details: String(details || ""), meta: meta && typeof meta === "object" ? meta : null };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const repoRoot = path.resolve(__dirname, "..");
  const runsRoot = path.isAbsolute(args.runsDir) ? args.runsDir : path.resolve(repoRoot, args.runsDir);
  const runDir = path.join(runsRoot, args.runId);

  const reportPath = args.out
    ? path.isAbsolute(args.out)
      ? args.out
      : path.resolve(repoRoot, args.out)
    : path.join(runDir, "acceptance_longrun.json");

  const requiredUnique = Math.floor(args.days * args.pagesPerDay);

  const sourcesPath = path.join(repoRoot, "agents", "configs", "sources.yaml");
  const domainPath = path.join(repoRoot, "agents", "configs", `${args.domain}.yaml`);
  const checks = [];

  const out = {
    version: 1,
    generated_at: new Date().toISOString(),
    inputs: {
      domain: args.domain,
      run_id: args.runId,
      runs_dir: path.relative(repoRoot, runsRoot),
      run_dir: path.relative(repoRoot, runDir),
      days: args.days,
      pages_per_day: args.pagesPerDay,
      required_unique_pages: requiredUnique,
    },
    files: {
      sources_yaml: path.relative(repoRoot, sourcesPath),
      domain_yaml: path.relative(repoRoot, domainPath),
      crawl_state_json: path.relative(repoRoot, path.join(runDir, "crawl_state.json")),
      extractor_state_json: path.relative(repoRoot, path.join(runDir, "extractor_state.json")),
      repo_state_json: path.relative(repoRoot, path.join(runDir, "repo_state.json")),
      metrics_json: path.relative(repoRoot, path.join(runDir, "metrics.json")),
      metrics_log_jsonl: path.relative(repoRoot, path.join(runDir, "metrics_log.jsonl")),
      candidates_jsonl: path.relative(repoRoot, path.join(runDir, "candidates.jsonl")),
    },
    checks,
    summary: {
      ok: false,
      failed: 0,
      warnings: 0,
    },
    recommended_run: {
      orchestrator_cmd: `node agents/orchestrator/run.js --domain ${args.domain} --run-id ${args.runId} --loop --crawl-max-pages ${args.pagesPerDay} --extract-max-docs ${args.pagesPerDay} --generate-max-topics 0 --cycle-sleep-ms 86400000`,
      verify_cmd: `node scripts/verify-longrun.js --domain ${args.domain} --run-id ${args.runId} --days ${args.days} --pages-per-day ${args.pagesPerDay} --strict`,
    },
  };

  if (!exists(sourcesPath)) {
    checks.push(makeCheck("config:sources.yaml exists", false, `Missing: ${sourcesPath}`));
  }
  if (!exists(domainPath)) {
    checks.push(makeCheck("config:domain.yaml exists", false, `Missing: ${domainPath}`));
  }

  let sources = null;
  let domainCfg = null;

  if (exists(sourcesPath)) {
    try {
      sources = parseSourcesRegistry(readText(sourcesPath));
      checks.push(makeCheck("config:sources.yaml parse", true, `sources=${sources.length}`));
    } catch (e) {
      checks.push(makeCheck("config:sources.yaml parse", false, String(e && e.message ? e.message : e)));
    }
  }

  if (exists(domainPath)) {
    try {
      domainCfg = parseDomainPolicyAndSources(readText(domainPath));
      const primary = domainCfg.sources && Array.isArray(domainCfg.sources.primary) ? domainCfg.sources.primary : [];
      checks.push(makeCheck("config:domain.yaml parse", true, `domain=${domainCfg.domain} primary_sources=${primary.length}`));
    } catch (e) {
      checks.push(makeCheck("config:domain.yaml parse", false, String(e && e.message ? e.message : e)));
    }
  }

  if (sources && domainCfg) {
    const byId = new Map(sources.map((s) => [String(s && s.id ? s.id : ""), s]));
    const primary = (domainCfg.sources && Array.isArray(domainCfg.sources.primary) ? domainCfg.sources.primary : []).filter(Boolean);
    const missing = primary.filter((id) => !byId.has(String(id)));
    checks.push(makeCheck("config:primary sources exist", missing.length === 0, missing.length ? `missing=${missing.join(", ")}` : "ok"));

    const primaryHttp = primary.map((id) => byId.get(String(id))).filter((s) => s && String(s.type || "") === "http_seed_crawl");
    const ttl = [];
    for (const s of primaryHttp) {
      const mode = String(s && s.refresh && s.refresh.mode ? s.refresh.mode : "");
      const interval = String(s && s.refresh && s.refresh.interval ? s.refresh.interval : "");
      const ms = parseDurationToMs(interval);
      ttl.push({ id: s.id, mode, interval, ms });
    }

    const badTtl = ttl.filter((t) => t.mode !== "ttl" || !t.ms);
    checks.push(
      makeCheck(
        "config:Tier1 ttl refresh configured",
        badTtl.length === 0,
        badTtl.length ? `bad=${badTtl.map((t) => t.id).join(", ")}` : "ok",
        { ttl },
      ),
    );

    const github = sources.filter((s) => String(s && s.type ? s.type : "") === "github_repo" && String(s && s.allowlist ? s.allowlist : "") === "true");
    checks.push(makeCheck("config:Tier0 github_repo sources", github.length > 0, `count=${github.length}`));
  }

  // Run artifacts checks (deterministic: file presence + key fields).
  const crawlStatePath = path.join(runDir, "crawl_state.json");
  const extractorStatePath = path.join(runDir, "extractor_state.json");
  const repoStatePath = path.join(runDir, "repo_state.json");
  const metricsPath = path.join(runDir, "metrics.json");
  const metricsLogPath = path.join(runDir, "metrics_log.jsonl");
  const candidatesPath = path.join(runDir, "candidates.jsonl");

  checks.push(makeCheck("run:run_dir exists", exists(runDir), exists(runDir) ? "ok" : `Missing: ${runDir}`));
  checks.push(makeCheck("run:crawl_state.json exists", exists(crawlStatePath), exists(crawlStatePath) ? "ok" : `Missing: ${crawlStatePath}`));
  checks.push(
    makeCheck("run:extractor_state.json exists", exists(extractorStatePath), exists(extractorStatePath) ? "ok" : `Missing: ${extractorStatePath}`),
  );
  checks.push(makeCheck("run:repo_state.json exists", exists(repoStatePath), exists(repoStatePath) ? "ok" : `Missing: ${repoStatePath}`));
  checks.push(makeCheck("run:metrics.json exists", exists(metricsPath), exists(metricsPath) ? "ok" : `Missing: ${metricsPath}`));
  checks.push(makeCheck("run:metrics_log.jsonl exists", exists(metricsLogPath), exists(metricsLogPath) ? "ok" : `Missing: ${metricsLogPath}`));
  checks.push(makeCheck("run:candidates.jsonl exists", exists(candidatesPath), exists(candidatesPath) ? "ok" : `Missing: ${candidatesPath}`));

  const crawlState = readJsonMaybe(crawlStatePath);
  if (crawlState) {
    const queueLen = Array.isArray(crawlState.queue) ? crawlState.queue.length : 0;
    const cursor = Number.isFinite(crawlState.cursor) ? crawlState.cursor : 0;
    const stats = crawlState.stats && typeof crawlState.stats === "object" ? crawlState.stats : {};
    const fetched = Number(stats.fetched || 0);
    const errors = Number(stats.errors || 0);
    const blocked = Number(stats.blocked || 0);
    const enqueued = Number(stats.enqueued || 0);

    const remaining = Math.max(0, queueLen - cursor);
    const remainingDays = remaining / args.pagesPerDay;

    const blockedRatio = blocked + enqueued > 0 ? blocked / (blocked + enqueued) : 0;
    const errorRatio = fetched + errors > 0 ? errors / (fetched + errors) : 0;

    const backlogOk = queueLen >= requiredUnique;
    const loopEnabled = !!(crawlState.options && crawlState.options.loop);
    const cacheTtlMs = crawlState.options && Number.isFinite(crawlState.options.cache_ttl_ms) ? Number(crawlState.options.cache_ttl_ms) : 0;
    const ttlOk = cacheTtlMs > 0;

    checks.push(
      makeCheck(
        "crawl:queue backlog for 90d",
        backlogOk || loopEnabled,
        backlogOk
          ? `queue=${queueLen} >= required=${requiredUnique}`
          : loopEnabled
            ? `queue=${queueLen} < required=${requiredUnique} but crawler loop=true (will not stop at end-of-queue)`
            : `queue=${queueLen} < required=${requiredUnique} and crawler loop=false (will stop early)`,
        { queue: queueLen, cursor, remaining, remaining_days: Number(remainingDays.toFixed(2)), required: requiredUnique, loop: loopEnabled },
      ),
    );

    checks.push(
      makeCheck(
        "crawl:cache ttl configured",
        ttlOk,
        ttlOk ? `cache_ttl_ms=${cacheTtlMs}` : "cache_ttl_ms is 0 (no refresh; may stop producing new info once cached)",
        { cache_ttl_ms: cacheTtlMs },
      ),
    );

    checks.push(
      makeCheck(
        "crawl:blocked ratio",
        blockedRatio < 0.85,
        `blocked_ratio=${pct(blockedRatio)} (blocked=${blocked} enqueued=${enqueued})`,
        { blocked_ratio: blockedRatio, blocked, enqueued },
      ),
    );

    checks.push(
      makeCheck(
        "crawl:error ratio",
        errorRatio < 0.25,
        `error_ratio=${pct(errorRatio)} (errors=${errors} fetched=${fetched})`,
        { error_ratio: errorRatio, errors, fetched },
      ),
    );
  }

  const extractorState = readJsonMaybe(extractorStatePath);
  if (extractorState) {
    const stats = extractorState.stats && typeof extractorState.stats === "object" ? extractorState.stats : {};
    const docsProcessed = Number(stats.docs_processed || 0);
    const candidatesEmitted = Number(stats.candidates_emitted || 0);
    const errors = Number(stats.errors || 0);
    const ok = docsProcessed > 0 && candidatesEmitted > 0;
    checks.push(
      makeCheck(
        "extractor:produces candidates",
        ok,
        ok ? `docs_processed=${docsProcessed} candidates_emitted=${candidatesEmitted}` : `docs_processed=${docsProcessed} candidates_emitted=${candidatesEmitted}`,
        { docs_processed: docsProcessed, candidates_emitted: candidatesEmitted, errors },
      ),
    );
  }

  const repoState = readJsonMaybe(repoStatePath);
  if (repoState && sources) {
    const repoSources = sources.filter((s) => String(s && s.type ? s.type : "") === "github_repo" && String(s && s.allowlist ? s.allowlist : "") === "true");
    const missing = [];
    const incomplete = [];
    for (const s of repoSources) {
      const id = String(s && s.id ? s.id : "").trim();
      const entry = repoState.sources && repoState.sources[id] ? repoState.sources[id] : null;
      if (!entry) {
        missing.push(id);
        continue;
      }
      const completed = !!entry.completed;
      const filesTotal = Number(entry.files_total || 0);
      const processedFiles = Number(entry.processed_files || 0);
      if (!completed || (filesTotal > 0 && processedFiles !== filesTotal)) incomplete.push(id);
    }
    const ok = missing.length === 0 && incomplete.length === 0;
    checks.push(
      makeCheck(
        "tier0:github repos ingested completely",
        ok,
        ok ? `repos=${repoSources.length}` : `missing=${missing.join(", ")} incomplete=${incomplete.join(", ")}`,
        { repos_total: repoSources.length, missing, incomplete },
      ),
    );
  }

  const failed = checks.filter((c) => !c.ok).length;
  out.summary.failed = failed;
  out.summary.ok = failed === 0;

  writeJsonAtomic(reportPath, out);
  console.log(`[verify-longrun] report: ${path.relative(repoRoot, reportPath)}`);
  if (!out.summary.ok) {
    console.error(`[verify-longrun] FAILED checks=${failed}`);
    if (args.strict) process.exit(1);
  } else {
    console.log("[verify-longrun] OK");
  }
}

main();

