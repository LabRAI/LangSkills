#!/usr/bin/env node
/* eslint-disable no-console */

const crypto = require("crypto");
const childProcess = require("child_process");
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

function utcNowIso() {
  return new Date().toISOString();
}

function writeJsonAtomic(filePath, obj) {
  ensureDir(path.dirname(filePath));
  const tmp = `${filePath}.${crypto.randomBytes(4).toString("hex")}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 2) + "\n", "utf8");
  fs.renameSync(tmp, filePath);
}

function appendJsonl(filePath, obj) {
  ensureDir(path.dirname(filePath));
  fs.appendFileSync(filePath, JSON.stringify(obj) + "\n", "utf8");
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
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

function sanitizeRunId(raw) {
  const v = String(raw || "").trim();
  if (!v) return "";
  const safe = v.replace(/[^A-Za-z0-9._-]/g, "-");
  return safe.replace(/-+/g, "-").replace(/^-+/, "").replace(/-+$/, "");
}

function makeDefaultRunId(domain) {
  const stamp = utcNowIso().replace(/[:.]/g, "").replace("T", "-").replace("Z", "");
  const rand = crypto.randomBytes(3).toString("hex");
  return sanitizeRunId(`${domain}-orch-${stamp}-${rand}`);
}

function run(cmd, args, options = {}) {
  const p = childProcess.spawnSync(cmd, args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    ...options,
  });
  return {
    status: typeof p.status === "number" ? p.status : 1,
    stdout: p.stdout || "",
    stderr: p.stderr || "",
  };
}

function assertOk(condition, message) {
  if (!condition) throw new Error(message);
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

function usage(exitCode = 0) {
  const msg = `
Usage:
  node agents/orchestrator/run.js --domain <domain>
    [--run-id <id>] [--runs-dir runs] [--cache-dir .cache/web]
    [--crawl-max-pages <n>] [--crawl-max-depth <n>]
    [--extract-max-docs <n>]
    [--generate-max-topics <n>] [--out <skillsRoot>] [--overwrite] [--capture] [--capture-strict]
    [--loop] [--sleep-ms <n>] [--cycle-sleep-ms <n>]
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
    cacheDir: ".cache/web",
    crawlMaxPages: 50,
    crawlMaxDepth: 2,
    extractMaxDocs: 50,
    generateMaxTopics: 0,
    out: "skills",
    overwrite: false,
    capture: false,
    captureStrict: false,
    loop: false,
    sleepMs: 0,
    cycleSleepMs: 0,
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
    } else if (a === "--cache-dir") {
      args.cacheDir = argv[i + 1] || args.cacheDir;
      i++;
    } else if (a === "--crawl-max-pages") {
      args.crawlMaxPages = Number(argv[i + 1] || "50");
      i++;
    } else if (a === "--crawl-max-depth") {
      args.crawlMaxDepth = Number(argv[i + 1] || "2");
      i++;
    } else if (a === "--extract-max-docs") {
      args.extractMaxDocs = Number(argv[i + 1] || "50");
      i++;
    } else if (a === "--generate-max-topics") {
      args.generateMaxTopics = Number(argv[i + 1] || "0");
      i++;
    } else if (a === "--out") {
      args.out = argv[i + 1] || args.out;
      i++;
    } else if (a === "--overwrite") args.overwrite = true;
    else if (a === "--capture") args.capture = true;
    else if (a === "--capture-strict") args.captureStrict = true;
    else if (a === "--loop") args.loop = true;
    else if (a === "--sleep-ms") {
      args.sleepMs = Number(argv[i + 1] || "0");
      i++;
    } else if (a === "--cycle-sleep-ms") {
      args.cycleSleepMs = Number(argv[i + 1] || "0");
      i++;
    } else if (a === "-h" || a === "--help") usage(0);
    else throw new Error(`Unknown arg: ${a}`);
  }

  if (!args.domain) usage(2);
  args.runId = args.runId ? sanitizeRunId(args.runId) : makeDefaultRunId(args.domain);
  if (!args.runId) throw new Error("Invalid --run-id");

  if (!Number.isFinite(args.crawlMaxPages) || args.crawlMaxPages < 0) args.crawlMaxPages = 50;
  if (!Number.isFinite(args.crawlMaxDepth) || args.crawlMaxDepth < 0) args.crawlMaxDepth = 2;
  if (!Number.isFinite(args.extractMaxDocs) || args.extractMaxDocs < 0) args.extractMaxDocs = 50;
  if (!Number.isFinite(args.generateMaxTopics) || args.generateMaxTopics < 0) args.generateMaxTopics = 0;
  if (!Number.isFinite(args.sleepMs) || args.sleepMs < 0) args.sleepMs = 0;
  if (!Number.isFinite(args.cycleSleepMs) || args.cycleSleepMs < 0) args.cycleSleepMs = 0;
  return args;
}

function readJsonMaybe(filePath) {
  if (!exists(filePath)) return null;
  try {
    return JSON.parse(readText(filePath));
  } catch {
    return null;
  }
}

function computeMetrics({ repoRoot, runDir, domain, runId, startedAtIso }) {
  const out = {
    ts: utcNowIso(),
    domain,
    run_id: runId,
    started_at: startedAtIso,
    crawler: null,
    extractor: null,
    runner: null,
  };

  const crawlState = readJsonMaybe(path.join(runDir, "crawl_state.json"));
  if (crawlState) {
    const q = Array.isArray(crawlState.queue) ? crawlState.queue : [];
    const docs = crawlState.docs && typeof crawlState.docs === "object" ? crawlState.docs : null;
    const docsTotal = docs ? Object.keys(docs).length : q.length;
    const docStates = {
      DISCOVERED: 0,
      FETCHED: 0,
      PARSED: 0,
      CANDIDATES_EXTRACTED: 0,
      BLOCKED: 0,
      ERROR: 0,
      OTHER: 0,
    };
    if (docs) {
      for (const d of Object.values(docs)) {
        const s = String(d && d.state ? d.state : "OTHER");
        if (Object.prototype.hasOwnProperty.call(docStates, s)) docStates[s] += 1;
        else docStates.OTHER += 1;
      }
    }

    const fetched = Number(crawlState.stats && crawlState.stats.fetched ? crawlState.stats.fetched : 0);
    const blocked = Number(crawlState.stats && crawlState.stats.blocked ? crawlState.stats.blocked : 0);
    const errors = Number(crawlState.stats && crawlState.stats.errors ? crawlState.stats.errors : 0);
    const cursor = Number.isFinite(crawlState.cursor) ? crawlState.cursor : 0;
    out.crawler = {
      queue_total: q.length,
      cursor,
      fetched,
      blocked,
      errors,
      docs_total: docsTotal,
      doc_states: docs ? docStates : null,
      coverage_fetched_ratio: docsTotal > 0 ? (docs ? docStates.FETCHED : fetched) / docsTotal : 0,
    };
  }

  const extractorState = readJsonMaybe(path.join(runDir, "extractor_state.json"));
  if (extractorState) {
    const processed = extractorState.stats && extractorState.stats.docs_processed ? Number(extractorState.stats.docs_processed) : 0;
    const candidates = extractorState.stats && extractorState.stats.candidates_emitted ? Number(extractorState.stats.candidates_emitted) : 0;
    const errors = extractorState.stats && extractorState.stats.errors ? Number(extractorState.stats.errors) : 0;
    out.extractor = {
      docs_processed: processed,
      candidates_emitted: candidates,
      errors,
    };
  }

  const runnerState = readJsonMaybe(path.join(runDir, "state.json"));
  if (runnerState) {
    const topics = Array.isArray(runnerState.topics) ? runnerState.topics : [];
    const processed = Number(runnerState.stats && runnerState.stats.processed ? runnerState.stats.processed : 0);
    const success = Number(runnerState.stats && runnerState.stats.success ? runnerState.stats.success : 0);
    const errors = Number(runnerState.stats && runnerState.stats.errors ? runnerState.stats.errors : 0);
    const done = topics.filter((t) => t && t.status === "done").length;
    out.runner = {
      topics_total: topics.length,
      topics_done: done,
      processed,
      success,
      errors,
      coverage_done_ratio: topics.length > 0 ? done / topics.length : 0,
    };
  }

  // Optional: surface where metrics live for dashboards
  out.paths = {
    run_dir: path.relative(repoRoot, runDir),
    crawl_state: exists(path.join(runDir, "crawl_state.json")) ? path.relative(repoRoot, path.join(runDir, "crawl_state.json")) : null,
    extractor_state: exists(path.join(runDir, "extractor_state.json"))
      ? path.relative(repoRoot, path.join(runDir, "extractor_state.json"))
      : null,
    candidates: exists(path.join(runDir, "candidates.jsonl")) ? path.relative(repoRoot, path.join(runDir, "candidates.jsonl")) : null,
    runner_state: exists(path.join(runDir, "state.json")) ? path.relative(repoRoot, path.join(runDir, "state.json")) : null,
  };
  return out;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const repoRoot = path.resolve(__dirname, "..", "..");

  const runId = args.runId;
  const runsRoot = path.isAbsolute(args.runsDir) ? args.runsDir : path.resolve(repoRoot, args.runsDir);
  const runDir = path.join(runsRoot, runId);
  ensureDir(runDir);

  const startedAtIso = utcNowIso();

  const domainConfigPath = path.join(repoRoot, "agents", "configs", `${args.domain}.yaml`);
  if (!exists(domainConfigPath)) throw new Error(`Missing domain config: ${domainConfigPath}`);
  const domainCfg = parseDomainPolicyAndSources(readText(domainConfigPath));
  if (domainCfg.domain !== args.domain) throw new Error(`domain mismatch: ${domainCfg.domain} != ${args.domain}`);

  const sourcesPath = path.join(repoRoot, "agents", "configs", "sources.yaml");
  const sources = exists(sourcesPath) ? parseSourcesRegistry(readText(sourcesPath)) : [];
  const primaryIds = (domainCfg.sources && Array.isArray(domainCfg.sources.primary) ? domainCfg.sources.primary : []).filter(Boolean);
  const primarySources = primaryIds.length > 0 ? sources.filter((s) => primaryIds.includes(s.id)) : [];

  if (primaryIds.length > 0 && primarySources.length === 0) {
    console.error(`[warn] domain has sources.primary but none found in sources.yaml: ${primaryIds.join(", ")}`);
  }

  let cycle = 0;
  while (true) {
    cycle += 1;
    console.log(`[orchestrator] cycle=${cycle} domain=${args.domain} run_id=${runId}`);

    // 1) Crawl (bounded per cycle)
    {
      const crawler = path.join(repoRoot, "agents", "crawler", "run.js");
      const maxPages = Number.isFinite(args.crawlMaxPages) ? args.crawlMaxPages : 50;
      const maxDepth = Number.isFinite(args.crawlMaxDepth) ? args.crawlMaxDepth : 2;

      const seedSources = primarySources.filter((s) => String(s.type || "") === "http_seed_crawl" && Array.isArray(s.seeds) && s.seeds.length > 0);
      const seeds = [];
      for (const s of seedSources) {
        for (const u of Array.isArray(s.seeds) ? s.seeds : []) {
          const url = String(u || "").trim();
          if (!url) continue;
          if (!seeds.includes(url)) seeds.push(url);
        }
      }
      const seedArg = seeds.length > 0 ? seeds.join(",") : null;

      let cacheTtlMs = null;
      for (const s of seedSources) {
        const mode = String(s && s.refresh && s.refresh.mode ? s.refresh.mode : "");
        if (mode !== "ttl") continue;
        const interval = s && s.refresh && s.refresh.interval ? s.refresh.interval : null;
        const ms = parseDurationToMs(interval);
        if (!ms) continue;
        cacheTtlMs = cacheTtlMs == null ? ms : Math.min(cacheTtlMs, ms);
      }

      const crawlArgs = [
        crawler,
        "--domain",
        args.domain,
        "--runs-dir",
        runsRoot,
        "--run-id",
        runId,
        "--cache-dir",
        args.cacheDir,
        "--max-pages",
        String(maxPages),
        "--max-depth",
        String(maxDepth),
      ];
      if (seedArg) {
        crawlArgs.push("--seeds", seedArg);
      }
      if (cacheTtlMs != null) {
        crawlArgs.push("--cache-ttl-ms", String(cacheTtlMs));
      }

      const r = run(process.execPath, crawlArgs, { cwd: repoRoot });
      assertOk(r.status === 0, r.stderr || r.stdout || "crawler failed");
    }

    // 2) Extract candidates (bounded per cycle)
    if (Number(args.extractMaxDocs || 0) > 0) {
      const extractor = path.join(repoRoot, "agents", "extractor", "run.js");
      const maxDocs = String(args.extractMaxDocs);
      const exArgs = [
        extractor,
        "--domain",
        args.domain,
        "--runs-dir",
        runsRoot,
        "--run-id",
        runId,
        "--cache-dir",
        args.cacheDir,
        "--max-docs",
        maxDocs,
      ];
      const r = run(process.execPath, exArgs, { cwd: repoRoot });
      assertOk(r.status === 0, r.stderr || r.stdout || "extractor failed");
    }

    // 2) Generate topics (bounded per cycle)
    if (Number(args.generateMaxTopics || 0) > 0) {
      const runner = path.join(repoRoot, "agents", "runner", "run.js");
      const maxTopics = String(args.generateMaxTopics);
      const runArgs = [
        runner,
        "--domain",
        args.domain,
        "--runs-dir",
        runsRoot,
        "--run-id",
        runId,
        "--out",
        args.out,
        "--max-topics",
        maxTopics,
      ];
      if (args.overwrite) runArgs.push("--overwrite");
      if (args.capture) runArgs.push("--capture");
      if (args.captureStrict) runArgs.push("--capture-strict");
      runArgs.push("--cache-dir", args.cacheDir);

      const r = run(process.execPath, runArgs, { cwd: repoRoot });
      assertOk(r.status === 0, r.stderr || r.stdout || "runner failed");
    }

    // 3) Metrics
    {
      const metrics = computeMetrics({ repoRoot, runDir, domain: args.domain, runId, startedAtIso });
      const metricsPath = path.join(runDir, "metrics.json");
      const metricsLogPath = path.join(runDir, "metrics_log.jsonl");
      writeJsonAtomic(metricsPath, metrics);
      appendJsonl(metricsLogPath, metrics);
      console.log(`[orchestrator] metrics: ${metricsPath}`);
    }

    if (!args.loop) break;
    if (args.sleepMs > 0) await sleep(args.sleepMs);
    if (args.cycleSleepMs > 0) await sleep(args.cycleSleepMs);
  }
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
