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
  return sanitizeRunId(`${domain}-extract-${stamp}-${rand}`);
}

function sha256Hex(text) {
  return crypto.createHash("sha256").update(String(text || ""), "utf8").digest("hex");
}

function looksLikeHtml(text) {
  const t = String(text || "");
  return /<!doctype html|<html[\s>]|<a\s+href=|<head[\s>]/i.test(t.slice(0, 4096));
}

function stripTags(html) {
  const raw = String(html || "");
  const noScripts = raw
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ");
  return noScripts.replace(/<[^>]+>/g, " ");
}

function decodeEntities(text) {
  const t = String(text || "");
  return t
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'");
}

function normalizeText(text) {
  const t = decodeEntities(String(text || ""));
  return t.replace(/\s+/g, " ").trim();
}

function extractHtmlTitle(html) {
  const raw = String(html || "");
  const m = raw.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  if (!m) return "";
  return normalizeText(stripTags(m[1]));
}

function extractHtmlHeadings(html) {
  const raw = String(html || "");
  const headings = [];
  const re = /<(h[1-6])\b[^>]*>([\s\S]*?)<\/\1>/gi;
  for (const m of raw.matchAll(re)) {
    const tag = String(m[1] || "").toLowerCase();
    const level = Number(tag.replace("h", "")) || 0;
    const text = normalizeText(stripTags(m[2] || ""));
    if (!text) continue;
    headings.push({ level, text });
  }
  return { title: extractHtmlTitle(raw), headings };
}

function extractMarkdownHeadings(text) {
  const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
  const headings = [];
  for (const raw of lines) {
    const line = String(raw || "");
    const m = line.match(/^(#{1,6})\s+(.+?)\s*$/);
    if (!m) continue;
    const level = m[1].length;
    const text2 = normalizeText(m[2]);
    if (!text2) continue;
    headings.push({ level, text: text2 });
  }
  return headings;
}

function shouldSkipHeading(text) {
  const t = String(text || "").trim();
  if (t.length < 4) return true;
  if (t.length > 140) return true;
  if (/^(table of contents|contents|overview|introduction|getting started)$/i.test(t)) return true;
  return false;
}

function makeCandidateId({ url, kind, title }) {
  const h = sha256Hex([url, kind, title].join("\n")).slice(0, 12);
  return `cand_${h}`;
}

function usage(exitCode = 0) {
  const msg = `
Usage:
  node agents/extractor/run.js --domain <domain>
    [--runs-dir <dir>] [--run-id <id>] [--cache-dir <dir>]
    [--max-docs <n>] [--loop] [--sleep-ms <n>] [--cycle-sleep-ms <n>]

Notes:
  - Reads crawl state: runs/<run-id>/crawl_state.json
  - Reads raw snapshots from cache dir (default .cache/web)
  - Writes candidates: runs/<run-id>/candidates.jsonl
  - Writes state: runs/<run-id>/extractor_state.json
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
    maxDocs: 50,
    loop: false,
    sleepMs: 0,
    cycleSleepMs: 0,
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
    } else if (a === "--max-docs") {
      args.maxDocs = Number(argv[i + 1] || "50");
      i++;
    } else if (a === "--loop") args.loop = true;
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

  if (!Number.isFinite(args.maxDocs) || args.maxDocs < 0) args.maxDocs = 50;
  if (!Number.isFinite(args.sleepMs) || args.sleepMs < 0) args.sleepMs = 0;
  if (!Number.isFinite(args.cycleSleepMs) || args.cycleSleepMs < 0) args.cycleSleepMs = 0;
  return args;
}

function readJson(filePath) {
  return JSON.parse(readText(filePath));
}

function getCrawlDocs(crawlState) {
  const docs = crawlState && crawlState.docs && typeof crawlState.docs === "object" ? crawlState.docs : null;
  if (docs) return docs;
  const out = {};
  const q = crawlState && Array.isArray(crawlState.queue) ? crawlState.queue : [];
  for (const item of q) {
    const url = String(item && item.url ? item.url : "").trim();
    if (!url) continue;
    out[url] = { url, state: "DISCOVERED", depth: Number(item && item.depth != null ? item.depth : 0), from: item && item.from ? item.from : null };
  }
  return out;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const repoRoot = path.resolve(__dirname, "..", "..");

  const runsRoot = path.isAbsolute(args.runsDir) ? args.runsDir : path.resolve(repoRoot, args.runsDir);
  const runDir = path.join(runsRoot, args.runId);
  ensureDir(runDir);

  const cacheDirAbs = path.isAbsolute(args.cacheDir) ? args.cacheDir : path.resolve(repoRoot, args.cacheDir);

  const crawlStatePath = path.join(runDir, "crawl_state.json");
  if (!exists(crawlStatePath)) throw new Error(`Missing crawl state: ${crawlStatePath}`);
  const crawlState = readJson(crawlStatePath);
  if (crawlState.domain !== args.domain) throw new Error(`domain mismatch: crawl_state.domain=${crawlState.domain} != ${args.domain}`);

  const docs = getCrawlDocs(crawlState);
  const urls = Object.keys(docs)
    .filter((u) => {
      const d = docs[u];
      return d && d.state === "FETCHED" && d.fetch && d.fetch.cache_file;
    })
    .sort();

  const statePath = path.join(runDir, "extractor_state.json");
  const candidatesPath = path.join(runDir, "candidates.jsonl");
  const logPath = path.join(runDir, "extractor_log.jsonl");

  let state = null;
  if (exists(statePath)) {
    state = readJson(statePath);
    if (state.domain !== args.domain) throw new Error(`state.domain mismatch: ${state.domain} != ${args.domain}`);
    if (state.run_id !== args.runId) throw new Error(`state.run_id mismatch: ${state.run_id} != ${args.runId}`);
  } else {
    state = {
      run_id: args.runId,
      created_at: utcNowIso(),
      updated_at: utcNowIso(),
      domain: args.domain,
      cycle: 1,
      cursor: 0,
      processed: {},
      stats: {
        docs_processed: 0,
        candidates_emitted: 0,
        errors: 0,
      },
    };
    writeJsonAtomic(statePath, state);
  }

  state.cursor = Number.isFinite(state.cursor) ? state.cursor : 0;
  state.cycle = Number.isFinite(state.cycle) ? state.cycle : 1;
  state.processed = state.processed && typeof state.processed === "object" ? state.processed : {};
  state.stats = state.stats && typeof state.stats === "object" ? state.stats : {};

  const maxDocs = Number.isFinite(args.maxDocs) ? args.maxDocs : 50;
  let processedThisRun = 0;

  while (true) {
    if (state.cursor >= urls.length) {
      if (!args.loop) break;
      if (args.cycleSleepMs > 0) {
        console.log(`[extractor] cycle=${state.cycle} complete; sleeping ${args.cycleSleepMs}ms`);
        await sleep(args.cycleSleepMs);
      }
      state.cycle += 1;
      state.cursor = 0;
      state.updated_at = utcNowIso();
      writeJsonAtomic(statePath, state);
      continue;
    }

    if (maxDocs > 0 && processedThisRun >= maxDocs) break;

    const url = urls[state.cursor];
    state.cursor += 1;
    processedThisRun += 1;

    const doc = docs[url];
    const fetchedSha = doc && doc.fetch && doc.fetch.sha256 ? String(doc.fetch.sha256) : "";
    if (fetchedSha && state.processed[url] === fetchedSha) continue;

    const cacheFile = doc && doc.fetch && doc.fetch.cache_file ? String(doc.fetch.cache_file) : "";
    const cachePath = cacheFile ? path.join(cacheDirAbs, cacheFile) : "";
    if (!cachePath || !exists(cachePath)) {
      state.stats.errors = Number(state.stats.errors || 0) + 1;
      appendJsonl(logPath, { ts: utcNowIso(), url, ok: false, error: "missing cache file", cache_path: cachePath || null });
      state.updated_at = utcNowIso();
      writeJsonAtomic(statePath, state);
      if (args.sleepMs > 0) await sleep(args.sleepMs);
      continue;
    }

    let raw = "";
    try {
      raw = readText(cachePath);
    } catch (e) {
      state.stats.errors = Number(state.stats.errors || 0) + 1;
      appendJsonl(logPath, { ts: utcNowIso(), url, ok: false, error: String(e && e.message ? e.message : e), cache_path: cachePath });
      state.updated_at = utcNowIso();
      writeJsonAtomic(statePath, state);
      if (args.sleepMs > 0) await sleep(args.sleepMs);
      continue;
    }

    const nowIso = utcNowIso();
    const extracted = looksLikeHtml(raw)
      ? extractHtmlHeadings(raw)
      : {
          title: "",
          headings: extractMarkdownHeadings(raw),
        };

    const uniq = new Set();
    let emitted = 0;

    const pushHeading = (h) => {
      const text = normalizeText(String(h && h.text ? h.text : ""));
      if (!text) return;
      if (shouldSkipHeading(text)) return;
      const key = text.toLowerCase();
      if (uniq.has(key)) return;
      uniq.add(key);

      const kind = "doc_heading";
      const id = makeCandidateId({ url, kind, title: text });
      appendJsonl(candidatesPath, {
        ts: nowIso,
        id,
        domain: args.domain,
        kind,
        title: text,
        level: Number(h && h.level != null ? h.level : 0) || 0,
        source: {
          url,
          fetched_at: doc && doc.fetched_at ? doc.fetched_at : null,
          fetched_sha256: fetchedSha || null,
          cache_file: cacheFile || null,
        },
      });
      emitted += 1;
    };

    if (extracted.title && !shouldSkipHeading(extracted.title)) {
      pushHeading({ level: 0, text: extracted.title });
    }

    const headings = Array.isArray(extracted.headings) ? extracted.headings : [];
    for (const h of headings.slice(0, 30)) pushHeading(h);

    state.stats.docs_processed = Number(state.stats.docs_processed || 0) + 1;
    state.stats.candidates_emitted = Number(state.stats.candidates_emitted || 0) + emitted;
    state.processed[url] = fetchedSha || `unknown:${nowIso}`;
    state.updated_at = utcNowIso();
    writeJsonAtomic(statePath, state);

    appendJsonl(logPath, { ts: nowIso, url, ok: true, headings: headings.length, emitted });

    if (args.sleepMs > 0) await sleep(args.sleepMs);
  }

  state.updated_at = utcNowIso();
  writeJsonAtomic(statePath, state);
  console.log(`[extractor] done. run_id=${state.run_id} domain=${state.domain} cycle=${state.cycle} cursor=${state.cursor}/${urls.length} processed=${processedThisRun}`);
  console.log(`[extractor] state: ${statePath}`);
  console.log(`[extractor] candidates: ${candidatesPath}`);
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});

