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
  return sanitizeRunId(`${domain}-${stamp}-${rand}`);
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

function parseDomainConfigYaml(yamlText) {
  const text = stripBom(String(yamlText || "")).replace(/\r\n/g, "\n");
  const lines = text.split("\n");

  let domain = null;
  const topics = [];

  let inTopics = false;
  let current = null;

  for (const rawLine of lines) {
    const line = rawLine.replace(/\s+$/, "");
    if (!line.trim()) continue;
    if (/^\s*#/.test(line)) continue;

    const domainMatch = line.match(/^domain:\s*(.+?)\s*$/);
    if (domainMatch && !inTopics) {
      domain = unquoteScalar(domainMatch[1]);
      continue;
    }

    if (/^topics:\s*$/.test(line)) {
      inTopics = true;
      current = null;
      continue;
    }

    if (!inTopics) continue;

    const itemStart = line.match(/^\s*-\s*id:\s*(.+?)\s*$/);
    if (itemStart) {
      if (current) topics.push(current);
      current = { id: unquoteScalar(itemStart[1]) };
      continue;
    }

    const propMatch = line.match(/^\s+([A-Za-z0-9_]+):\s*(.+?)\s*$/);
    if (propMatch && current) {
      const key = propMatch[1];
      const value = unquoteScalar(propMatch[2]);
      current[key] = value;
    }
  }

  if (current) topics.push(current);

  if (!domain) throw new Error("Invalid config: missing 'domain:'");
  if (topics.length === 0) throw new Error("Invalid config: no topics found under 'topics:'");

  return { domain, topics };
}

function usage(exitCode = 0) {
  const msg = `
Usage:
  node agents/runner/run.js --domain <domain>
    [--out <skillsRoot>] [--overwrite]
    [--topic <topic/id>] [--capture] [--capture-strict] [--cache-dir <path>] [--timeout-ms <n>]
    [--llm-provider mock|ollama|openai] [--llm-model <model>] [--llm-base-url <url>] [--llm-api-key <key>] [--llm-fixture <path>] [--llm-timeout-ms <n>] [--llm-strict]
    [--runs-dir <dir>] [--run-id <id>] [--loop] [--sleep-ms <n>] [--cycle-sleep-ms <n>] [--max-topics <n>] [--max-cycles <n>]

Examples:
  # One pass (all topics)
  node agents/runner/run.js --domain linux --out skills --overwrite --capture --capture-strict

  # Loop forever
  node agents/runner/run.js --domain linux --out skills --overwrite --capture --loop --sleep-ms 30000

  # Resume (same run-id)
  node agents/runner/run.js --domain linux --run-id linux-weekly --out skills --overwrite --capture --loop
`.trim();

  if (exitCode === 0) console.log(msg);
  else console.error(msg);
  process.exit(exitCode);
}

function parseArgs(argv) {
  const args = {
    domain: null,
    out: "skills",
    overwrite: false,
    topic: null,
    capture: false,
    captureStrict: false,
    cacheDir: ".cache/web",
    timeoutMs: 20000,

    llmProvider: null,
    llmModel: null,
    llmBaseUrl: null,
    llmApiKey: null,
    llmFixture: null,
    llmTimeoutMs: 60000,
    llmStrict: false,

    runsDir: "runs",
    runId: null,
    loop: false,
    sleepMs: 0,
    cycleSleepMs: 0,
    maxTopics: 0,
    maxCycles: 0,
  };

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--domain") {
      args.domain = argv[i + 1] || null;
      i++;
    } else if (a === "--out") {
      args.out = argv[i + 1] || args.out;
      i++;
    } else if (a === "--overwrite") args.overwrite = true;
    else if (a === "--topic") {
      args.topic = argv[i + 1] || null;
      i++;
    } else if (a === "--capture") args.capture = true;
    else if (a === "--capture-strict") args.captureStrict = true;
    else if (a === "--cache-dir") {
      args.cacheDir = argv[i + 1] || args.cacheDir;
      i++;
    } else if (a === "--timeout-ms") {
      args.timeoutMs = Number(argv[i + 1] || "20000");
      i++;
    } else if (a === "--llm-provider") {
      args.llmProvider = argv[i + 1] || null;
      i++;
    } else if (a === "--llm-model") {
      args.llmModel = argv[i + 1] || null;
      i++;
    } else if (a === "--llm-base-url") {
      args.llmBaseUrl = argv[i + 1] || null;
      i++;
    } else if (a === "--llm-api-key") {
      args.llmApiKey = argv[i + 1] || null;
      i++;
    } else if (a === "--llm-fixture") {
      args.llmFixture = argv[i + 1] || null;
      i++;
    } else if (a === "--llm-timeout-ms") {
      args.llmTimeoutMs = Number(argv[i + 1] || "60000");
      i++;
    } else if (a === "--llm-strict") args.llmStrict = true;
    else if (a === "--runs-dir") {
      args.runsDir = argv[i + 1] || args.runsDir;
      i++;
    } else if (a === "--run-id") {
      args.runId = argv[i + 1] || null;
      i++;
    } else if (a === "--loop") args.loop = true;
    else if (a === "--sleep-ms") {
      args.sleepMs = Number(argv[i + 1] || "0");
      i++;
    } else if (a === "--cycle-sleep-ms") {
      args.cycleSleepMs = Number(argv[i + 1] || "0");
      i++;
    } else if (a === "--max-topics") {
      args.maxTopics = Number(argv[i + 1] || "0");
      i++;
    } else if (a === "--max-cycles") {
      args.maxCycles = Number(argv[i + 1] || "0");
      i++;
    } else if (a === "-h" || a === "--help") usage(0);
    else throw new Error(`Unknown arg: ${a}`);
  }

  if (!args.domain) usage(2);
  args.runId = args.runId ? sanitizeRunId(args.runId) : makeDefaultRunId(args.domain);
  if (!args.runId) throw new Error("Invalid --run-id");

  return args;
}

function loadTopicsFromConfig(configPath, topicFilter) {
  const cfg = parseDomainConfigYaml(readText(configPath));
  const list = cfg.topics.map((t) => String(t.id || "").trim()).filter(Boolean);
  const filtered = topicFilter ? list.filter((id) => id === topicFilter) : list;
  if (topicFilter && filtered.length === 0) throw new Error(`Topic not found in config: ${topicFilter}`);
  return { domain: cfg.domain, topics: filtered };
}

function ensureTopicsInState(state, topicsFromConfig) {
  const known = new Set((state.topics || []).map((t) => t.id));
  for (const id of topicsFromConfig) {
    if (known.has(id)) continue;
    state.topics.push({
      id,
      status: "pending",
      attempts_total: 0,
      attempts_cycle: 0,
      last_started_at: null,
      last_finished_at: null,
      last_success_at: null,
      last_error_at: null,
      last_error: null,
      last_exit_code: null,
    });
  }
}

function resetCycle(state) {
  state.cycle += 1;
  state.cursor = 0;
  for (const t of state.topics) {
    t.status = "pending";
    t.attempts_cycle = 0;
  }
}

function initState({ runId, domain, out, options, topics }) {
  return {
    run_id: runId,
    created_at: utcNowIso(),
    updated_at: utcNowIso(),
    domain,
    out,
    options,
    cycle: 0,
    cursor: 0,
    stats: { success: 0, errors: 0, processed: 0 },
    topics: topics.map((id) => ({
      id,
      status: "pending",
      attempts_total: 0,
      attempts_cycle: 0,
      last_started_at: null,
      last_finished_at: null,
      last_success_at: null,
      last_error_at: null,
      last_error: null,
      last_exit_code: null,
    })),
  };
}

function runLocalOnce({ repoRoot, domain, topicId, out, overwrite, options }) {
  const args = [
    path.join(repoRoot, "agents", "run_local.js"),
    "--domain",
    domain,
    "--topic",
    topicId,
    "--out",
    out,
  ];

  if (overwrite) args.push("--overwrite");
  if (options.capture) args.push("--capture");
  if (options.captureStrict) args.push("--capture-strict");
  if (options.cacheDir) args.push("--cache-dir", options.cacheDir);
  if (Number.isFinite(options.timeoutMs)) args.push("--timeout-ms", String(options.timeoutMs));

  if (options.llmProvider) args.push("--llm-provider", options.llmProvider);
  if (options.llmModel) args.push("--llm-model", options.llmModel);
  if (options.llmBaseUrl) args.push("--llm-base-url", options.llmBaseUrl);
  if (options.llmApiKey) args.push("--llm-api-key", options.llmApiKey);
  if (options.llmFixture) args.push("--llm-fixture", options.llmFixture);
  if (Number.isFinite(options.llmTimeoutMs)) args.push("--llm-timeout-ms", String(options.llmTimeoutMs));
  if (options.llmStrict) args.push("--llm-strict");

  const proc = childProcess.spawnSync(process.execPath, args, {
    cwd: repoRoot,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });

  return {
    status: typeof proc.status === "number" ? proc.status : 1,
    stdout: proc.stdout || "",
    stderr: proc.stderr || "",
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const repoRoot = path.resolve(__dirname, "..", "..");

  const runsRoot = path.isAbsolute(args.runsDir) ? args.runsDir : path.resolve(repoRoot, args.runsDir);
  const runDir = path.join(runsRoot, args.runId);
  const statePath = path.join(runDir, "state.json");
  ensureDir(runDir);

  const configPath = path.join(repoRoot, "agents", "configs", `${args.domain}.yaml`);
  if (!exists(configPath)) throw new Error(`Missing config: ${configPath}`);

  let state = null;
  if (exists(statePath)) {
    state = JSON.parse(readText(statePath));
    if (state.domain !== args.domain) throw new Error(`state.domain mismatch: ${state.domain} != ${args.domain}`);
    if (state.out !== args.out) {
      console.error(`[warn] state.out=${state.out} differs from --out=${args.out}; using state.out`);
    }

    let repaired = false;
    for (const t of Array.isArray(state.topics) ? state.topics : []) {
      if (t && t.status === "running") {
        t.status = "pending";
        repaired = true;
      }
    }
    if (repaired) {
      state.updated_at = utcNowIso();
      writeJsonAtomic(statePath, state);
    }
  } else {
    const loaded = loadTopicsFromConfig(configPath, args.topic);
    if (loaded.domain !== args.domain) throw new Error(`Config domain mismatch: expected ${args.domain} but got ${loaded.domain}`);

    state = initState({
      runId: args.runId,
      domain: args.domain,
      out: args.out,
      options: {
        overwrite: args.overwrite,
        capture: args.capture,
        captureStrict: args.captureStrict,
        cacheDir: args.cacheDir,
        timeoutMs: args.timeoutMs,
        llmProvider: args.llmProvider,
        llmModel: args.llmModel,
        llmBaseUrl: args.llmBaseUrl,
        llmApiKey: args.llmApiKey,
        llmFixture: args.llmFixture,
        llmTimeoutMs: args.llmTimeoutMs,
        llmStrict: args.llmStrict,
      },
      topics: loaded.topics,
    });
    resetCycle(state);
    writeJsonAtomic(statePath, state);
  }

  if (args.overwrite && !(state.options && state.options.overwrite)) {
    state.options = state.options || {};
    state.options.overwrite = true;
    state.updated_at = utcNowIso();
    writeJsonAtomic(statePath, state);
  }

  const outRoot = path.isAbsolute(state.out) ? state.out : path.resolve(repoRoot, state.out);
  const runOnceOptions = {
    overwrite: !!(state.options && state.options.overwrite),
    capture: !!state.options.capture,
    captureStrict: !!state.options.captureStrict,
    cacheDir: state.options.cacheDir || ".cache/web",
    timeoutMs: Number.isFinite(state.options.timeoutMs) ? state.options.timeoutMs : 20000,
    llmProvider: state.options.llmProvider || null,
    llmModel: state.options.llmModel || null,
    llmBaseUrl: state.options.llmBaseUrl || null,
    llmApiKey: state.options.llmApiKey || null,
    llmFixture: state.options.llmFixture || null,
    llmTimeoutMs: Number.isFinite(state.options.llmTimeoutMs) ? state.options.llmTimeoutMs : 60000,
    llmStrict: !!state.options.llmStrict,
  };

  const maxTopics = Number.isFinite(args.maxTopics) ? args.maxTopics : 0;
  const maxCycles = Number.isFinite(args.maxCycles) ? args.maxCycles : 0;
  let processedThisRun = 0;

  while (true) {
    // Sync new topics from config (best-effort)
    try {
      const loaded = loadTopicsFromConfig(configPath, args.topic);
      ensureTopicsInState(state, loaded.topics);
    } catch (e) {
      console.error(`[warn] failed to sync topics from config: ${String(e && e.message ? e.message : e)}`);
    }

    // Skip already-done items (in case of partial state)
    while (state.cursor < state.topics.length && state.topics[state.cursor].status === "done") {
      state.cursor += 1;
    }

    if (state.cursor >= state.topics.length) {
      const reachedMaxCycles = maxCycles > 0 && state.cycle >= maxCycles;
      if (!args.loop || reachedMaxCycles) break;

      if (Number.isFinite(args.cycleSleepMs) && args.cycleSleepMs > 0) {
        console.log(`[runner] cycle=${state.cycle} complete; sleeping ${args.cycleSleepMs}ms`);
        await sleep(args.cycleSleepMs);
      }

      resetCycle(state);
      state.updated_at = utcNowIso();
      writeJsonAtomic(statePath, state);
      continue;
    }

    if (maxTopics > 0 && processedThisRun >= maxTopics) break;

    const item = state.topics[state.cursor];
    item.status = "running";
    item.attempts_total += 1;
    item.attempts_cycle += 1;
    item.last_started_at = utcNowIso();
    item.last_error = null;
    item.last_exit_code = null;
    state.updated_at = utcNowIso();
    writeJsonAtomic(statePath, state);

    console.log(`[runner] cycle=${state.cycle} cursor=${state.cursor + 1}/${state.topics.length} topic=${item.id}`);

    const r = runLocalOnce({
      repoRoot,
      domain: state.domain,
      topicId: item.id,
      out: outRoot,
      overwrite: runOnceOptions.overwrite,
      options: runOnceOptions,
    });

    item.last_finished_at = utcNowIso();
    item.last_exit_code = r.status;
    state.stats.processed += 1;
    processedThisRun += 1;

    if (r.status === 0) {
      item.status = "done";
      item.last_success_at = item.last_finished_at;
      item.last_error_at = null;
      item.last_error = null;
      state.stats.success += 1;
    } else {
      item.status = "error";
      item.last_error_at = item.last_finished_at;
      const msg = (r.stderr || r.stdout || "").trim();
      item.last_error = msg ? msg.slice(0, 2000) : `exit_code=${r.status}`;
      state.stats.errors += 1;
      console.error(`[runner] topic failed: ${item.id} (exit=${r.status})`);
    }

    state.updated_at = utcNowIso();
    writeJsonAtomic(statePath, state);

    state.cursor += 1;

    if (Number.isFinite(args.sleepMs) && args.sleepMs > 0) {
      await sleep(args.sleepMs);
    }
  }

  state.updated_at = utcNowIso();
  writeJsonAtomic(statePath, state);
  console.log(`[runner] done. run_id=${state.run_id} cycle=${state.cycle} cursor=${state.cursor}/${state.topics.length} processed=${processedThisRun}`);
  console.log(`[runner] state: ${statePath}`);
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
