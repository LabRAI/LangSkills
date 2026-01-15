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

function sanitizeRunId(raw) {
  const v = String(raw || "").trim();
  if (!v) return "";
  const safe = v.replace(/[^A-Za-z0-9._-]/g, "-");
  return safe.replace(/-+/g, "-").replace(/^-+/, "").replace(/-+$/, "");
}

function makeDefaultRunId(domain) {
  const stamp = utcNowIso().replace(/[:.]/g, "").replace("T", "-").replace("Z", "");
  const rand = crypto.randomBytes(3).toString("hex");
  return sanitizeRunId(`${domain}-crawl-${stamp}-${rand}`);
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

function parseDomainCrawlConfigYaml(yamlText) {
  const text = stripBom(String(yamlText || "")).replace(/\r\n/g, "\n");
  const lines = text.split("\n");

  let domain = null;
  const sourcePolicy = { allow_domains: [], deny_domains: [] };
  const seeds = [];

  let inSourcePolicy = false;
  let collectAllow = false;
  let collectDeny = false;
  let collectSeeds = false;

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
      collectAllow = false;
      collectDeny = false;
      continue;
    }

    const seedsMatch = line.match(/^seeds:\s*(.*?)\s*$/);
    if (seedsMatch) {
      const parsed = parseInlineYamlList(seedsMatch[1]);
      seeds.length = 0;
      if (parsed !== null) seeds.push(...parsed);
      collectSeeds = parsed === null;
      inSourcePolicy = false;
      collectAllow = false;
      collectDeny = false;
      continue;
    }

    if (collectSeeds) {
      const m = line.match(/^\s*-\s*(.+?)\s*$/);
      if (m) {
        seeds.push(unquoteScalar(m[1]));
        continue;
      }
      collectSeeds = false;
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

  if (!domain) throw new Error("Invalid config: missing 'domain:'");
  return { domain, seeds, source_policy: sourcePolicy };
}

function normalizeDomainPattern(pattern) {
  const p = String(pattern || "").trim().toLowerCase();
  if (!p) return "";
  return p.replace(/^\.+/, "").replace(/\.+$/, "");
}

function hostMatchesPattern(hostname, pattern) {
  const host = String(hostname || "").trim().toLowerCase();
  const raw = String(pattern || "").trim().toLowerCase();
  const p = normalizeDomainPattern(raw);
  if (!host || !p) return false;
  if (host === p) return true;
  return host.endsWith(`.${p}`);
}

function isUrlAllowed(url, { allow_domains: allowDomains = [], deny_domains: denyDomains = [] } = {}) {
  const u = new URL(String(url || ""));
  const host = u.hostname;

  for (const d of Array.isArray(denyDomains) ? denyDomains : []) {
    if (hostMatchesPattern(host, d)) return false;
  }

  const allow = Array.isArray(allowDomains) ? allowDomains.filter(Boolean) : [];
  if (allow.length === 0) return true;
  return allow.some((d) => hostMatchesPattern(host, d));
}

function sha256Hex(text) {
  return crypto.createHash("sha256").update(String(text || ""), "utf8").digest("hex");
}

function cachePathForUrl(cacheDir, url) {
  const hash = sha256Hex(url).slice(0, 16);
  return path.join(cacheDir, `${hash}.txt`);
}

function cacheFileForUrl(url) {
  return `${sha256Hex(url).slice(0, 16)}.txt`;
}

function cacheFreshEnough(cachePath, cacheTtlMs) {
  if (!exists(cachePath)) return false;
  const ttl = Number(cacheTtlMs || 0);
  if (!Number.isFinite(ttl) || ttl <= 0) return true;
  const stat = fs.statSync(cachePath);
  return Date.now() - Number(stat.mtimeMs || 0) <= ttl;
}

async function fetchText(url, timeoutMs) {
  if (typeof fetch !== "function") {
    throw new Error("Global fetch() not available. Use Node.js 18+.");
  }

  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const resp = await fetch(url, {
      method: "GET",
      headers: { "User-Agent": "skill-crawler" },
      redirect: "follow",
      signal: controller.signal,
    });
    const text = await resp.text();
    return {
      ok: resp.ok,
      status: resp.status,
      contentType: resp.headers.get("content-type") || "",
      text,
    };
  } finally {
    clearTimeout(t);
  }
}

async function fetchWithCache({ url, cacheDir, timeoutMs, cacheTtlMs }) {
  ensureDir(cacheDir);
  const cachePath = cachePathForUrl(cacheDir, url);

  if (cacheFreshEnough(cachePath, cacheTtlMs)) {
    const text = readText(cachePath);
    return {
      ok: true,
      status: 200,
      contentType: "",
      text,
      cache: "hit",
      bytes: Buffer.byteLength(text, "utf8"),
      sha256: sha256Hex(text),
    };
  }

  const r = await fetchText(url, timeoutMs);
  if (!r.ok) {
    throw new Error(`HTTP ${r.status} for ${url}`);
  }

  fs.writeFileSync(cachePath, r.text, "utf8");
  return {
    ok: true,
    status: r.status,
    contentType: r.contentType || "",
    text: r.text,
    cache: "miss",
    bytes: Buffer.byteLength(r.text, "utf8"),
    sha256: sha256Hex(r.text),
  };
}

function removeTrackingParams(u) {
  const keys = [
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
  ];
  for (const k of keys) u.searchParams.delete(k);
}

function canonicalizeUrl(rawUrl) {
  const raw = String(rawUrl || "").trim();
  if (!raw) return null;
  let u;
  try {
    u = new URL(raw);
  } catch {
    return null;
  }
  if (u.protocol !== "http:" && u.protocol !== "https:") return null;
  u.hash = "";
  removeTrackingParams(u);
  u.searchParams.sort();
  return u.toString();
}

function shouldSkipByExtension(url) {
  const u = String(url || "").toLowerCase();
  return /\.(png|jpe?g|gif|webp|svg|ico|pdf|zip|tar|gz|xz|bz2|7z|dmg|pkg|exe|mp[34]|wav)(?:$|[?#])/.test(u);
}

function looksLikeHtml(text) {
  const t = String(text || "");
  return /<!doctype html|<html[\s>]|<a\s+href=|<head[\s>]/i.test(t.slice(0, 4096));
}

function extractLinks(html, baseUrl) {
  const base = String(baseUrl || "");
  const out = new Set();
  const re = /href\s*=\s*["']([^"']+)["']/gi;
  for (const m of html.matchAll(re)) {
    const href = String(m[1] || "").trim();
    if (!href) continue;
    if (href.startsWith("#")) continue;
    if (/^(javascript:|mailto:|tel:)/i.test(href)) continue;

    let abs;
    try {
      abs = new URL(href, base).toString();
    } catch {
      continue;
    }

    const canonical = canonicalizeUrl(abs);
    if (!canonical) continue;
    if (shouldSkipByExtension(canonical)) continue;
    out.add(canonical);
  }
  return [...out];
}

function usage(exitCode = 0) {
  const msg = `
Usage:
  node agents/crawler/run.js --domain <domain>
    [--runs-dir <dir>] [--run-id <id>]
    [--cache-dir <dir>] [--timeout-ms <n>] [--cache-ttl-ms <n>]
    [--max-depth <n>] [--max-pages <n>]
    [--sleep-ms <n>] [--loop] [--cycle-sleep-ms <n>]
    [--seeds <url[,url...]>] [--allow-domain <domain>] [--deny-domain <domain>]

Notes:
  - Seeds and source_policy are read from: agents/configs/<domain>.yaml (unless overridden via CLI).
  - Writes state: runs/<run-id>/crawl_state.json and logs: runs/<run-id>/crawl_log.jsonl
  - Writes fetch cache: .cache/web/<sha256(url)[:16]>.txt (default; override with --cache-dir)
`.trim();
  if (exitCode === 0) console.log(msg);
  else console.error(msg);
  process.exit(exitCode);
}

function parseArgs(argv) {
  const args = {
    domain: null,
    runsDir: "runs",
    runId: null,
    cacheDir: ".cache/web",
    timeoutMs: 20000,
    cacheTtlMs: 0,
    maxDepth: 2,
    maxPages: 200,
    sleepMs: 0,
    loop: false,
    cycleSleepMs: 0,
    seeds: [],
    allowDomains: [],
    denyDomains: [],
  };

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--domain") {
      args.domain = argv[i + 1] || null;
      i++;
    } else if (a === "--runs-dir") {
      args.runsDir = argv[i + 1] || args.runsDir;
      i++;
    } else if (a === "--run-id") {
      args.runId = argv[i + 1] || null;
      i++;
    } else if (a === "--cache-dir") {
      args.cacheDir = argv[i + 1] || args.cacheDir;
      i++;
    } else if (a === "--timeout-ms") {
      args.timeoutMs = Number(argv[i + 1] || "20000");
      i++;
    } else if (a === "--cache-ttl-ms") {
      args.cacheTtlMs = Number(argv[i + 1] || "0");
      i++;
    } else if (a === "--max-depth") {
      args.maxDepth = Number(argv[i + 1] || "2");
      i++;
    } else if (a === "--max-pages") {
      args.maxPages = Number(argv[i + 1] || "200");
      i++;
    } else if (a === "--sleep-ms") {
      args.sleepMs = Number(argv[i + 1] || "0");
      i++;
    } else if (a === "--loop") {
      args.loop = true;
    } else if (a === "--cycle-sleep-ms") {
      args.cycleSleepMs = Number(argv[i + 1] || "0");
      i++;
    } else if (a === "--seeds" || a === "--seed") {
      const v = argv[i + 1];
      if (!v) throw new Error(`${a} requires a value`);
      v.split(",")
        .map((x) => x.trim())
        .filter(Boolean)
        .forEach((x) => args.seeds.push(x));
      i++;
    } else if (a === "--allow-domain") {
      const v = argv[i + 1];
      if (!v) throw new Error("--allow-domain requires a value");
      args.allowDomains.push(String(v).trim());
      i++;
    } else if (a === "--deny-domain") {
      const v = argv[i + 1];
      if (!v) throw new Error("--deny-domain requires a value");
      args.denyDomains.push(String(v).trim());
      i++;
    } else if (a === "-h" || a === "--help") {
      usage(0);
    } else {
      throw new Error(`Unknown arg: ${a}`);
    }
  }

  if (!args.domain) usage(2);
  args.runId = args.runId ? sanitizeRunId(args.runId) : makeDefaultRunId(args.domain);
  if (!args.runId) throw new Error("Invalid --run-id");
  if (!Number.isFinite(args.timeoutMs) || args.timeoutMs <= 0) args.timeoutMs = 20000;
  if (!Number.isFinite(args.cacheTtlMs) || args.cacheTtlMs < 0) args.cacheTtlMs = 0;
  if (!Number.isFinite(args.maxDepth) || args.maxDepth < 0) args.maxDepth = 0;
  if (!Number.isFinite(args.maxPages) || args.maxPages < 0) args.maxPages = 0;
  if (!Number.isFinite(args.sleepMs) || args.sleepMs < 0) args.sleepMs = 0;
  if (!Number.isFinite(args.cycleSleepMs) || args.cycleSleepMs < 0) args.cycleSleepMs = 0;
  return args;
}

function extendPolicy(configPolicy, args) {
  const policy = {
    allow_domains: Array.isArray(configPolicy.allow_domains) ? [...configPolicy.allow_domains] : [],
    deny_domains: Array.isArray(configPolicy.deny_domains) ? [...configPolicy.deny_domains] : [],
  };

  for (const d of Array.isArray(args.allowDomains) ? args.allowDomains : []) {
    if (!d) continue;
    policy.allow_domains.push(d);
  }
  for (const d of Array.isArray(args.denyDomains) ? args.denyDomains : []) {
    if (!d) continue;
    policy.deny_domains.push(d);
  }

  return policy;
}

function ensureDocEntry(state, { url, depth, from, nowIso }) {
  state.docs = state.docs && typeof state.docs === "object" ? state.docs : {};
  const key = String(url || "").trim();
  if (!key) return null;

  const existing = state.docs[key];
  const base = existing && typeof existing === "object" ? existing : null;
  const d = base || {
    url: key,
    state: "DISCOVERED",
    discovered_at: nowIso,
    last_seen_at: nowIso,
    depth: Number.isFinite(depth) ? depth : 0,
    from: from || null,
    attempts: 0,
  };

  d.last_seen_at = nowIso;
  const newDepth = Number.isFinite(depth) ? depth : 0;
  const prevDepth = Number.isFinite(d.depth) ? d.depth : null;
  if (prevDepth == null || newDepth < prevDepth) d.depth = newDepth;
  if (!d.from && from) d.from = from;

  state.docs[key] = d;
  return d;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const repoRoot = path.resolve(__dirname, "..", "..");

  const configPath = path.join(repoRoot, "agents", "configs", `${args.domain}.yaml`);
  if (!exists(configPath)) throw new Error(`Missing config: ${configPath}`);

  const cfg = parseDomainCrawlConfigYaml(readText(configPath));
  if (cfg.domain !== args.domain) throw new Error(`Config domain mismatch: expected ${args.domain} but got ${cfg.domain}`);

  const seeds = (args.seeds.length > 0 ? args.seeds : cfg.seeds).map((s) => canonicalizeUrl(s)).filter(Boolean);
  if (seeds.length === 0) throw new Error(`No seeds provided (config has none and no --seeds).`);

  const policy = extendPolicy(cfg.source_policy || { allow_domains: [], deny_domains: [] }, args);

  for (const url of seeds) {
    if (!isUrlAllowed(url, policy)) {
      throw new Error(`[source_policy] blocked seed URL: ${url}`);
    }
  }

  const runsRoot = path.isAbsolute(args.runsDir) ? args.runsDir : path.resolve(repoRoot, args.runsDir);
  const runDir = path.join(runsRoot, args.runId);
  ensureDir(runDir);

  const statePath = path.join(runDir, "crawl_state.json");
  const logPath = path.join(runDir, "crawl_log.jsonl");

  const cacheDirAbs = path.isAbsolute(args.cacheDir) ? args.cacheDir : path.resolve(repoRoot, args.cacheDir);

  let state = null;
  if (exists(statePath)) {
    state = JSON.parse(readText(statePath));
    if (state.domain !== args.domain) throw new Error(`state.domain mismatch: ${state.domain} != ${args.domain}`);
  } else {
    const nowIso = utcNowIso();
    state = {
      run_id: args.runId,
      created_at: utcNowIso(),
      updated_at: utcNowIso(),
      domain: args.domain,
      seeds,
      source_policy: policy,
      options: {
        cache_dir: args.cacheDir,
        timeout_ms: args.timeoutMs,
        cache_ttl_ms: args.cacheTtlMs,
        max_depth: args.maxDepth,
        max_pages: args.maxPages,
        sleep_ms: args.sleepMs,
        loop: args.loop,
        cycle_sleep_ms: args.cycleSleepMs,
      },
      cycle: 1,
      cursor: 0,
      queue: seeds.map((url) => ({ url, depth: 0, from: null })),
      docs: Object.fromEntries(
        seeds.map((url) => [
          url,
          {
            url,
            state: "DISCOVERED",
            discovered_at: nowIso,
            last_seen_at: nowIso,
            depth: 0,
            from: null,
            attempts: 0,
          },
        ]),
      ),
      stats: {
        fetched: 0,
        enqueued: seeds.length,
        errors: 0,
        blocked: 0,
        skipped: 0,
        cache_hit: 0,
        cache_miss: 0,
      },
    };
    writeJsonAtomic(statePath, state);
  }

  const queueSet = new Set((Array.isArray(state.queue) ? state.queue : []).map((q) => q.url));
  state.queue = Array.isArray(state.queue) ? state.queue : [];
  state.cursor = Number.isFinite(state.cursor) ? state.cursor : 0;
  state.cycle = Number.isFinite(state.cycle) ? state.cycle : 1;
  state.stats = state.stats || {};
  state.docs = state.docs && typeof state.docs === "object" ? state.docs : {};

  for (const q of state.queue) {
    const url = String(q && q.url ? q.url : "").trim();
    if (!url) continue;
    ensureDocEntry(state, {
      url,
      depth: Number(q && q.depth != null ? q.depth : 0),
      from: q && q.from ? String(q.from) : null,
      nowIso: utcNowIso(),
    });
  }

  const maxDepth = Number.isFinite(args.maxDepth) ? args.maxDepth : 2;
  const maxPages = Number.isFinite(args.maxPages) ? args.maxPages : 200;

  let processedThisRun = 0;

  while (true) {
    if (state.cursor >= state.queue.length) {
      if (!args.loop) break;
      if (args.cycleSleepMs > 0) {
        console.log(`[crawler] cycle=${state.cycle} complete; sleeping ${args.cycleSleepMs}ms`);
        await sleep(args.cycleSleepMs);
      }
      state.cycle += 1;
      state.cursor = 0;
      state.updated_at = utcNowIso();
      writeJsonAtomic(statePath, state);
      continue;
    }

    if (maxPages > 0 && processedThisRun >= maxPages) break;

    const item = state.queue[state.cursor];
    state.cursor += 1;
    processedThisRun += 1;

    const url = String(item && item.url ? item.url : "").trim();
    const depth = Number(item && item.depth != null ? item.depth : 0);
    if (!url) {
      state.stats.skipped = Number(state.stats.skipped || 0) + 1;
      continue;
    }

    const nowIso = utcNowIso();
    const doc = ensureDocEntry(state, { url, depth, from: item && item.from ? String(item.from) : null, nowIso });

    if (!isUrlAllowed(url, policy)) {
      state.stats.blocked = Number(state.stats.blocked || 0) + 1;
      if (doc) {
        doc.state = "BLOCKED";
        doc.blocked_at = nowIso;
        doc.last_error = "blocked by source_policy";
      }
      appendJsonl(logPath, { ts: nowIso, url, depth, ok: false, doc_state: "BLOCKED", error: "blocked by source_policy" });
      continue;
    }

    let fetched = null;
    try {
      fetched = await fetchWithCache({
        url,
        cacheDir: cacheDirAbs,
        timeoutMs: args.timeoutMs,
        cacheTtlMs: args.cacheTtlMs,
      });
    } catch (e) {
      state.stats.errors = Number(state.stats.errors || 0) + 1;
      const errMsg = String(e && e.message ? e.message : e);
      if (doc) {
        doc.state = "ERROR";
        doc.last_error = errMsg;
        doc.last_error_at = nowIso;
        doc.attempts = Number(doc.attempts || 0) + 1;
      }
      appendJsonl(logPath, { ts: nowIso, url, depth, ok: false, doc_state: "ERROR", error: errMsg });
      state.updated_at = utcNowIso();
      writeJsonAtomic(statePath, state);
      if (args.sleepMs > 0) await sleep(args.sleepMs);
      continue;
    }

    state.stats.fetched = Number(state.stats.fetched || 0) + 1;
    if (fetched.cache === "hit") state.stats.cache_hit = Number(state.stats.cache_hit || 0) + 1;
    else state.stats.cache_miss = Number(state.stats.cache_miss || 0) + 1;

    if (doc) {
      doc.state = "FETCHED";
      doc.fetched_at = nowIso;
      doc.attempts = Number(doc.attempts || 0) + 1;
      doc.last_error = null;
      doc.last_error_at = null;
      doc.fetch = {
        cache: fetched.cache,
        status: fetched.status,
        content_type: fetched.contentType || "",
        bytes: fetched.bytes,
        sha256: fetched.sha256,
        cache_file: cacheFileForUrl(url),
      };
    }

    const html = fetched.text || "";
    const isHtml = looksLikeHtml(html);
    const links = isHtml && depth < maxDepth ? extractLinks(html, url) : [];

    let enqueued = 0;
    let blocked = 0;
    let skipped = 0;

    for (const link of links) {
      if (!link) continue;
      if (!isUrlAllowed(link, policy)) {
        blocked++;
        continue;
      }
      if (queueSet.has(link)) {
        skipped++;
        continue;
      }
      queueSet.add(link);
      state.queue.push({ url: link, depth: depth + 1, from: url });
      ensureDocEntry(state, { url: link, depth: depth + 1, from: url, nowIso });
      enqueued++;
    }

    state.stats.enqueued = Number(state.stats.enqueued || 0) + enqueued;
    state.stats.blocked = Number(state.stats.blocked || 0) + blocked;
    state.stats.skipped = Number(state.stats.skipped || 0) + skipped;

    appendJsonl(logPath, {
      ts: nowIso,
      url,
      depth,
      ok: true,
      doc_state: "FETCHED",
      cache: fetched.cache,
      status: fetched.status,
      content_type: fetched.contentType || "",
      bytes: fetched.bytes,
      sha256: fetched.sha256,
      cache_file: cacheFileForUrl(url),
      is_html: isHtml,
      discovered: links.length,
      enqueued,
      blocked,
      skipped,
    });

    state.updated_at = utcNowIso();
    writeJsonAtomic(statePath, state);

    if (args.sleepMs > 0) await sleep(args.sleepMs);
  }

  state.updated_at = utcNowIso();
  writeJsonAtomic(statePath, state);
  console.log(
    `[crawler] done. run_id=${state.run_id} domain=${state.domain} cycle=${state.cycle} cursor=${state.cursor}/${state.queue.length} processed=${processedThisRun}`,
  );
  console.log(`[crawler] state: ${statePath}`);
  console.log(`[crawler] log: ${logPath}`);
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
