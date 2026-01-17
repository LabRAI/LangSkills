#!/usr/bin/env node
/* eslint-disable no-console */

const childProcess = require("child_process");
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

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function writeJsonAtomic(filePath, obj) {
  ensureDir(path.dirname(filePath));
  const tmp = `${filePath}.${crypto.randomBytes(4).toString("hex")}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 2) + "\n", "utf8");
  fs.renameSync(tmp, filePath);
}

function utcNowIso() {
  return new Date().toISOString();
}

function sanitizeRunId(raw) {
  const v = String(raw || "").trim();
  if (!v) return "";
  const safe = v.replace(/[^A-Za-z0-9._-]/g, "-");
  return safe.replace(/-+/g, "-").replace(/^-+/, "").replace(/-+$/, "");
}

function makeDefaultRunId({ domain, topicId }) {
  const stamp = utcNowIso().replace(/[:.]/g, "").replace("T", "-").replace("Z", "");
  const rand = crypto.randomBytes(3).toString("hex");
  const base = sanitizeRunId(`${domain}-${topicId}-${stamp}-${rand}`);
  return base || sanitizeRunId(`${domain}-${stamp}-${rand}`);
}

function looksLikeNetworkError(text) {
  return /fetch failed|ENOTFOUND|ECONNRESET|ETIMEDOUT|EAI_AGAIN|ECONNREFUSED|certificate|AbortError/i.test(String(text || ""));
}

function rmrf(targetPath) {
  try {
    fs.rmSync(targetPath, { recursive: true, force: true });
  } catch {
    // ignore
  }
}

function listRunDirs(runsRoot) {
  const out = [];
  for (const ent of fs.readdirSync(runsRoot, { withFileTypes: true })) {
    if (!ent.isDirectory()) continue;
    out.push(ent.name);
  }
  return out;
}

function usage(exitCode = 0) {
  const msg = `
Usage:
  node scripts/run-topic.js --domain <domain> --topic <topic/slug> [--topic <topic/slug> ...]
  node scripts/run-topic.js --domain <domain> --topics <topic/slug,topic/slug,...>
  node scripts/run-topic.js --domain <domain> --topic <prefix>           # expands to prefix/*
  node scripts/run-topic.js --domain <domain> --topic <prefix>/*         # expands to all matching
  node scripts/run-topic.js --domain <domain> --topic all|*              # expands to all topics in config
    [--run-id <id>] [--runs-dir runs]
    [--clean-project] [--clean-cache] [--clean-all-runs] [--require-network]
    [--continue-on-error]
    [--llm-provider openai|ollama|mock|none] [--llm-capture]
    [--cache-dir <path>] [--out <path>]
    [--git-push] [--git-repo <path>] [--git-remote <name>] [--git-branch <name>] [--git-message <msg>] [--git-dry-run]

What it does:
  1) (optional) Cleans demo run artifacts under runs/ (keeps the sample runs listed in runs/README.md)
  2) Runs one-or-more topics end-to-end via agents/run_local.js --capture (plus optional LLM rewrite)
  3) Writes a JSON report with exact output paths for debugging
  4) (optional) Commits + pushes this run dir to a git repo (for artifact storage)

Notes:
  - Model is read from .env via OPENAI_MODEL when using --llm-provider openai and --llm-model is omitted.
  - If network fetch fails, it retries with docs/fixtures/web-cache unless --require-network is set.
`.trim();
  if (exitCode === 0) console.log(msg);
  else console.error(msg);
  process.exit(exitCode);
}

function parseArgs(argv) {
  const args = {
    domain: null,
    topics: [],
    runId: null,
    runsDir: "runs",

    cleanProject: true,
    cleanCache: true,
    cleanAllRuns: true,
    requireNetwork: false,
    continueOnError: false,

    llmProvider: "openai",
    llmCapture: true,

    cacheDir: null,
    out: null,

    gitPush: false,
    gitDryRun: false,
    gitRepo: null,
    gitRemote: "origin",
    gitBranch: null,
    gitMessage: null,
  };

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--domain") {
      args.domain = argv[i + 1] || null;
      i++;
    } else if (a === "--topic") {
      const v = argv[i + 1] || null;
      if (v) args.topics.push(v);
      i++;
    } else if (a === "--topics") {
      const raw = argv[i + 1] || "";
      const parts = String(raw)
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      for (const p of parts) args.topics.push(p);
      i++;
    } else if (a === "--run-id") {
      args.runId = argv[i + 1] || null;
      i++;
    } else if (a === "--runs-dir") {
      args.runsDir = argv[i + 1] || args.runsDir;
      i++;
    } else if (a === "--clean-project") args.cleanProject = true;
    else if (a === "--no-clean-project") args.cleanProject = false;
    else if (a === "--clean-cache") args.cleanCache = true;
    else if (a === "--no-clean-cache") args.cleanCache = false;
    else if (a === "--clean-all-runs") args.cleanAllRuns = true;
    else if (a === "--no-clean-all-runs") args.cleanAllRuns = false;
    else if (a === "--require-network") args.requireNetwork = true;
    else if (a === "--continue-on-error") args.continueOnError = true;
    else if (a === "--llm-provider") {
      args.llmProvider = argv[i + 1] || "";
      i++;
    } else if (a === "--llm-capture") args.llmCapture = true;
    else if (a === "--no-llm-capture") args.llmCapture = false;
    else if (a === "--cache-dir") {
      args.cacheDir = argv[i + 1] || null;
      i++;
    } else if (a === "--out") {
      args.out = argv[i + 1] || null;
      i++;
    } else if (a === "--git-push") args.gitPush = true;
    else if (a === "--git-dry-run") args.gitDryRun = true;
    else if (a === "--git-repo") {
      args.gitRepo = argv[i + 1] || null;
      i++;
    } else if (a === "--git-remote") {
      args.gitRemote = argv[i + 1] || args.gitRemote;
      i++;
    } else if (a === "--git-branch") {
      args.gitBranch = argv[i + 1] || null;
      i++;
    } else if (a === "--git-message") {
      args.gitMessage = argv[i + 1] || null;
      i++;
    } else if (a === "-h" || a === "--help") usage(0);
    else throw new Error(`Unknown arg: ${a}`);
  }

  if (!args.domain) usage(2);
  if (!Array.isArray(args.topics) || args.topics.length === 0) usage(2);
  if (args.gitDryRun) args.gitPush = true;

  args.runId = args.runId ? sanitizeRunId(args.runId) : null;
  if (args.runId === "") args.runId = null;
  return args;
}

function normalizeTopicId(topic) {
  const raw = String(topic || "").trim().replace(/\\/g, "/");
  if (!raw) return "";
  const parts = raw.split("/").filter(Boolean);
  if (parts.length === 3) return parts.slice(1).join("/");
  return raw;
}

function loadTopicIdsFromConfig(configPath) {
  const text = stripBom(fs.readFileSync(configPath, "utf8")).replace(/\r\n/g, "\n");
  const lines = text.split("\n");

  const ids = [];
  const topics = [];
  let inTopics = false;
  let current = null;

  for (const rawLine of lines) {
    const line = rawLine.replace(/\s+$/, "");
    if (!line.trim()) continue;
    if (/^\s*#/.test(line)) continue;

    if (!inTopics) {
      if (/^topics:\s*$/.test(line)) inTopics = true;
      continue;
    }

    // Stop if a new top-level key starts.
    if (/^[A-Za-z0-9_]+:\s*/.test(line) && !/^\s+/.test(line)) break;

    const m = line.match(/^\s*-\s*id:\s*(.+?)\s*$/);
    if (m) {
      if (current) {
        ids.push(current.id);
        topics.push(current);
      }
      const id = unquoteScalar(m[1]);
      if (!id) continue;
      current = { id, title: "", risk_level: "", level: "" };
      continue;
    }

    const propMatch = line.match(/^\s+([A-Za-z0-9_]+):\s*(.+?)\s*$/);
    if (propMatch && current) {
      const key = propMatch[1];
      const value = unquoteScalar(propMatch[2]);
      if (key === "title") current.title = value;
      else if (key === "risk_level") current.risk_level = value;
      else if (key === "level") current.level = value;
    }
  }

  if (current) {
    ids.push(current.id);
    topics.push(current);
  }

  if (ids.length === 0) throw new Error(`No topics found in config: ${configPath}`);
  return { ids, topics };
}

function resolveTopicSelectors(requestedTopics, availableTopicIds) {
  const requested = Array.isArray(requestedTopics) ? requestedTopics : [];
  const available = Array.isArray(availableTopicIds) ? availableTopicIds : [];
  const out = [];
  const seen = new Set();

  const add = (id) => {
    if (!id || seen.has(id)) return;
    out.push(id);
    seen.add(id);
  };

  for (const raw0 of requested) {
    const raw = String(raw0 || "").trim();
    if (!raw) continue;
    const lower = raw.toLowerCase();
    if (raw === "*" || lower === "all") {
      for (const id of available) add(id);
      continue;
    }

    const normalized = normalizeTopicId(raw);
    if (available.includes(normalized)) {
      add(normalized);
      continue;
    }

    let prefix = normalized;
    if (prefix.endsWith("/*")) prefix = prefix.slice(0, -1); // keep trailing '/'
    if (!prefix.endsWith("/")) prefix = `${prefix}/`;

    const matches = available.filter((id) => String(id).startsWith(prefix));
    if (matches.length === 0) throw new Error(`Topic not found (id or prefix): ${raw}`);
    for (const id of matches) add(id);
  }

  if (out.length === 0) throw new Error("No topics resolved from selectors");
  return out;
}

function escapeMarkdownTableCell(raw) {
  return String(raw || "")
    .replace(/\r?\n/g, " ")
    .replace(/\|/g, "\\|")
    .trim();
}

function readFirstMarkdownTitleIfExists(filePath) {
  if (!filePath || !exists(filePath)) return "";
  const lines = String(fs.readFileSync(filePath, "utf8") || "")
    .replace(/\r\n/g, "\n")
    .split("\n");
  for (const raw of lines) {
    const line = String(raw || "").trim();
    if (!line) continue;
    const m = line.match(/^#\s+(.+?)\s*$/);
    if (m) return String(m[1]).trim();
  }
  return "";
}

function readFirstGoalBulletIfExists(filePath) {
  if (!filePath || !exists(filePath)) return "";
  const lines = String(fs.readFileSync(filePath, "utf8") || "")
    .replace(/\r\n/g, "\n")
    .split("\n");

  let inGoal = false;
  for (const raw of lines) {
    const line = String(raw || "").trim();
    if (!inGoal) {
      if (/^##\s+Goal\s*$/.test(line)) inGoal = true;
      continue;
    }
    if (/^##\s+/.test(line)) break;
    const m = line.match(/^-+\s+(.+?)\s*$/);
    if (m) return String(m[1]).trim();
  }
  return "";
}

function renderDomainReadme({ domain, topics, manifest, repoRoot }) {
  const topicList = Array.isArray(topics) ? topics : [];
  const results = Array.isArray(manifest && manifest.results) ? manifest.results : [];
  const skillsRoot = manifest && manifest.skills_root ? String(manifest.skills_root) : `skills/${domain ? domain : ""}`;

  const byId = new Map();
  for (const r of results) {
    if (r && r.topic) byId.set(String(r.topic), r);
  }

  const lines = [];
  lines.push(`# ${domain} Skills`);
  lines.push("");
  lines.push(`本目录包含 ${domain} domain 的 skills。`);
  lines.push("");
  lines.push("## 目录约定");
  lines.push("");
  lines.push(`- 路径：\`${escapeMarkdownTableCell(skillsRoot)}/${escapeMarkdownTableCell(domain)}/<topic>/<slug>/\``);
  lines.push("- 每个 skill：`skill.md` + `library.md` + `metadata.yaml` + `reference/`");
  lines.push("");
  lines.push("## Run Context");
  lines.push("");
  lines.push(`- run_id: \`${escapeMarkdownTableCell(manifest && manifest.run_id ? manifest.run_id : "")}\``);
  lines.push(`- generated_at: \`${escapeMarkdownTableCell(manifest && manifest.generated_at ? manifest.generated_at : "")}\``);
  if (manifest && manifest.topics_selectors) {
    const selectors = Array.isArray(manifest.topics_selectors) ? manifest.topics_selectors : [];
    lines.push(`- topics_selectors: \`${escapeMarkdownTableCell(selectors.join(", "))}\``);
  }
  if (manifest && manifest.llm && manifest.llm.provider) {
    lines.push(`- llm_provider: \`${escapeMarkdownTableCell(manifest.llm.provider)}\``);
  }
  if (manifest && manifest.skills_root) lines.push(`- skills_root: \`${escapeMarkdownTableCell(manifest.skills_root)}\``);
  lines.push("");

  lines.push("## Topics (Index)");
  lines.push("");
  lines.push("| # | ID | Risk | Level |");
  lines.push("|---:|---|---:|---:|");
  for (let i = 0; i < topicList.length; i++) {
    const t = topicList[i] || {};
    const id = String(t.id || "");
    const risk = t.risk_level ? `**${escapeMarkdownTableCell(t.risk_level)}**` : "";
    const level = escapeMarkdownTableCell(t.level || "");
    lines.push(`| ${i + 1} | \`${escapeMarkdownTableCell(domain + "/" + id)}\` | ${risk} | ${level} |`);
  }
  lines.push("");

  lines.push("## Topics (Artifacts)");
  lines.push("");
  lines.push("> 每个 topic 下方都有一个表格：标题/简述 + 本次运行产物的路径（skill、sources、LLM prompt capture、日志等）。");
  lines.push("");

  for (const t of topicList) {
    const id = String(t && t.id ? t.id : "");
    if (!id) continue;
    const r = byId.get(id) || null;

    const titleFromConfig = String(t && t.title ? t.title : "").trim();
    const skillMdPath = r && r.skill_md ? path.resolve(repoRoot, r.skill_md) : null;
    const titleFromSkill = skillMdPath ? readFirstMarkdownTitleIfExists(skillMdPath) : "";
    const title = titleFromSkill || titleFromConfig || `${domain}/${id}`;
    const brief = skillMdPath ? readFirstGoalBulletIfExists(skillMdPath) : "";

    const safeTitle = escapeMarkdownTableCell(title);
    lines.push(`### ${escapeMarkdownTableCell(id)} — ${safeTitle}`);
    lines.push("");
    lines.push("| Field | Value |");
    lines.push("|---|---|");
    lines.push(`| Title | ${escapeMarkdownTableCell(title)} |`);
    lines.push(`| Brief | ${escapeMarkdownTableCell(brief) || "—"} |`);
    lines.push(`| Risk | ${escapeMarkdownTableCell(t && t.risk_level ? t.risk_level : "") || "—"} |`);
    lines.push(`| Level | ${escapeMarkdownTableCell(t && t.level ? t.level : "") || "—"} |`);

    if (!r) {
      lines.push(`| Status | not generated |`);
      lines.push(`| skill_dir | — |`);
      lines.push(`| skill.md | — |`);
      lines.push(`| sources.md | — |`);
      lines.push(`| llm_capture (skill) | — |`);
      lines.push(`| llm_capture (library) | — |`);
      lines.push(`| logs (primary) | — |`);
      lines.push(`| report.json | — |`);
      lines.push("");
      continue;
    }

    const status = r.status || "";
    lines.push(`| Status | \`${escapeMarkdownTableCell(status)}\` |`);
    lines.push(`| skill_dir | ${r.skill_dir ? `\`${escapeMarkdownTableCell(r.skill_dir)}\`` : "—"} |`);
    lines.push(`| skill.md | ${r.skill_md ? `\`${escapeMarkdownTableCell(r.skill_md)}\`` : "—"} |`);
    lines.push(`| sources.md | ${r.sources_md ? `\`${escapeMarkdownTableCell(r.sources_md)}\`` : "—"} |`);
    lines.push(
      `| llm_capture (skill) | ${
        r.llm_capture && r.llm_capture.rewrite_skill ? `\`${escapeMarkdownTableCell(r.llm_capture.rewrite_skill)}\`` : "—"
      } |`,
    );
    lines.push(
      `| llm_capture (library) | ${
        r.llm_capture && r.llm_capture.rewrite_library ? `\`${escapeMarkdownTableCell(r.llm_capture.rewrite_library)}\`` : "—"
      } |`,
    );
    lines.push(`| logs (primary) | ${r.logs && r.logs.primary ? `\`${escapeMarkdownTableCell(r.logs.primary)}\`` : "—"} |`);
    lines.push(`| report.json | ${r.report_json ? `\`${escapeMarkdownTableCell(r.report_json)}\`` : "—"} |`);
    lines.push("");
  }

  return lines.join("\n") + "\n";
}

function makeTopicKey(topicId) {
  return String(topicId || "").trim().replace(/[^A-Za-z0-9._-]+/g, "-").replace(/-+/g, "-").replace(/^-+/, "").replace(/-+$/, "");
}

function isPreservedSampleRun(name) {
  return name === "linux-crawl-demo" || name === "linux-orch-weekly" || name === "integrations-weekly";
}

function cleanProjectArtifacts({ repoRoot, runsRoot, keepRunId, cleanCache, cleanAllRuns }) {
  const deleted = { runs: [], cache: [] };

  // 1) runs/<run-id> (fresh run)
  if (keepRunId) {
    const target = path.join(runsRoot, keepRunId);
    if (exists(target)) {
      rmrf(target);
      deleted.runs.push(keepRunId);
    }
  }

  // 2) demo run dirs (keep sample runs)
  for (const name of listRunDirs(runsRoot)) {
    if (name === keepRunId) continue;
    if (isPreservedSampleRun(name)) continue;
    if (!cleanAllRuns) {
      // Keep non-demo dirs unless they look like demo outputs.
      const looksDemo = /demo|^llm-|^skill-gen-|^curator-|^topic-run-/i.test(name);
      if (!looksDemo) continue;
    }
    rmrf(path.join(runsRoot, name));
    deleted.runs.push(name);
  }

  // 3) .cache (optional; delete the whole dir)
  if (cleanCache) {
    const cacheDir = path.join(repoRoot, ".cache");
    if (exists(cacheDir)) {
      rmrf(cacheDir);
      deleted.cache.push(path.relative(repoRoot, cacheDir));
    }
  }

  return deleted;
}

function run(cmd, args, { cwd, env, logPath }) {
  const proc = childProcess.spawnSync(cmd, args, {
    cwd,
    env,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    maxBuffer: 1024 * 1024 * 64,
  });

  const stdout = proc.stdout || "";
  const stderr = proc.stderr || "";
  if (logPath) {
    ensureDir(path.dirname(logPath));
    const header = [
      `# ts=${utcNowIso()}`,
      `# cmd=${[cmd, ...args].map((x) => JSON.stringify(x)).join(" ")}`,
      "",
    ].join("\n");
    fs.writeFileSync(logPath, `${header}\n[stdout]\n${stdout}\n[stderr]\n${stderr}\n`, "utf8");
  }

  return { status: typeof proc.status === "number" ? proc.status : 1, stdout, stderr };
}

function redactRemoteUrl(url) {
  const u = String(url || "").trim();
  const m = u.match(/^(https?:\/\/)([^@]+)@(.+)$/);
  if (m) return `${m[1]}<redacted>@${m[3]}`;
  return u;
}

function gitCmd(cwd, args) {
  const env = { ...process.env, GIT_TERMINAL_PROMPT: "0" };
  const proc = childProcess.spawnSync("git", args, {
    cwd,
    env,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    maxBuffer: 1024 * 1024 * 16,
  });
  return { status: typeof proc.status === "number" ? proc.status : 1, stdout: proc.stdout || "", stderr: proc.stderr || "" };
}

function getGitRepoRoot(cwd) {
  const r = gitCmd(cwd, ["rev-parse", "--show-toplevel"]);
  if (r.status !== 0) return null;
  const root = String(r.stdout || "").trim();
  return root || null;
}

function getGitCurrentBranch(repoRoot) {
  const r = gitCmd(repoRoot, ["branch", "--show-current"]);
  if (r.status !== 0) return null;
  const name = String(r.stdout || "").trim();
  return name || null;
}

function runGitAutomation({ scriptRepoRoot, gitRepoRoot, remote, branch, message, paths, execute }) {
  const scriptPath = path.join(scriptRepoRoot, "scripts", "git-automation.js");
  if (!exists(scriptPath)) throw new Error(`Missing: ${scriptPath}`);

  const args = [
    scriptPath,
    "--repo",
    gitRepoRoot,
    "--remote",
    remote,
    "--branch",
    branch,
    "--message",
    message,
    "--paths",
    paths.join(","),
  ];

  if (execute) args.push("--execute");
  const env = { ...process.env, GIT_TERMINAL_PROMPT: "0" };
  const proc = childProcess.spawnSync(process.execPath, args, {
    cwd: scriptRepoRoot,
    env,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    maxBuffer: 1024 * 1024 * 16,
  });
  return { status: typeof proc.status === "number" ? proc.status : 1, stdout: proc.stdout || "", stderr: proc.stderr || "" };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const repoRoot = path.resolve(__dirname, "..");
  const runsRoot = path.isAbsolute(args.runsDir) ? args.runsDir : path.resolve(repoRoot, args.runsDir);
  ensureDir(runsRoot);

  const topicsSelectors = args.topics.map(normalizeTopicId).filter(Boolean);
  if (topicsSelectors.length === 0) throw new Error("Invalid --topic/--topics");

  const configPath = path.join(repoRoot, "agents", "configs", `${args.domain}.yaml`);
  if (!exists(configPath)) throw new Error(`Missing config: ${configPath}`);
  const cfg = loadTopicIdsFromConfig(configPath);
  const topics = resolveTopicSelectors(topicsSelectors, cfg.ids);

  const runId = args.runId || makeDefaultRunId({ domain: args.domain, topicId: topics[0] });
  if (!runId) throw new Error("Invalid --run-id");

  const runDir = path.join(runsRoot, runId);
  const outRoot = args.out ? (path.isAbsolute(args.out) ? args.out : path.resolve(repoRoot, args.out)) : path.join(runDir, "skills");
  const reportPath = path.join(runDir, "report.json");
  const manifestPath = path.join(runDir, "manifest.json");
  const logsDir = path.join(runDir, "logs");
  const reportsDir = path.join(runDir, "reports");

  const fixtureCache = path.join(repoRoot, "docs", "fixtures", "web-cache");
  const cacheDirPrimary = args.cacheDir
    ? path.isAbsolute(args.cacheDir)
      ? args.cacheDir
      : path.resolve(repoRoot, args.cacheDir)
    : path.join(repoRoot, ".cache", "web");

  // Cleaning (keeps sample runs; never touches .env)
  if (args.cleanProject) {
    const deleted = cleanProjectArtifacts({
      repoRoot,
      runsRoot,
      keepRunId: runId,
      cleanCache: args.cleanCache,
      cleanAllRuns: args.cleanAllRuns,
    });
    console.log(`[clean] deleted runs: ${deleted.runs.length ? deleted.runs.join(", ") : "(none)"}`);
    console.log(`[clean] deleted cache: ${deleted.cache.length ? deleted.cache.join(", ") : "(none)"}`);
  } else {
    // Always ensure the current run dir is fresh to avoid confusing mixed outputs.
    rmrf(runDir);
  }

  ensureDir(runDir);
  ensureDir(logsDir);
  ensureDir(reportsDir);

  const runLocal = path.join(repoRoot, "agents", "run_local.js");
  if (!exists(runLocal)) throw new Error(`Missing: ${runLocal}`);

  const cachePrimaryRel = path.relative(repoRoot, cacheDirPrimary);
  const fixtureCacheRel = path.relative(repoRoot, fixtureCache);

  const env = { ...process.env, GIT_TERMINAL_PROMPT: "0" };
  const manifest = {
    version: 1,
    generated_at: utcNowIso(),
    run_id: runId,
    domain: args.domain,
    topics_selectors: topicsSelectors,
    topics_requested: topics,
    runs_dir: path.relative(repoRoot, runsRoot),
    run_dir: path.relative(repoRoot, runDir),
    skills_root: path.relative(repoRoot, outRoot),
    cache: {
      primary: cachePrimaryRel,
      fallback_fixture: fixtureCacheRel,
    },
    llm: { provider: args.llmProvider || "none", capture: !!args.llmCapture },
    results: [],
  };

  const domainRoot = path.join(outRoot, args.domain);
  const domainReadmePath = path.join(domainRoot, "README.md");

  let anyFailed = false;

  for (const topicId of topics) {
    const topicKey = makeTopicKey(topicId) || "topic";
    const perReportPath = path.join(reportsDir, `${topicKey}.json`);

    const baseArgs = [
      runLocal,
      "--domain",
      args.domain,
      "--topic",
      topicId,
      "--out",
      outRoot,
      "--overwrite",
      "--capture",
      "--capture-strict",
      "--report-json",
      perReportPath,
    ];

    if (args.llmProvider && args.llmProvider !== "none") {
      baseArgs.push("--llm-provider", args.llmProvider);
      if (args.llmCapture) baseArgs.push("--llm-capture");
    }

    // 1st attempt: primary cache
    let cacheMode = "primary";
    let cacheDirUsed = cacheDirPrimary;
    let r = run(process.execPath, [...baseArgs, "--cache-dir", cacheDirPrimary], {
      cwd: repoRoot,
      env,
      logPath: path.join(logsDir, `${topicKey}.primary.log`),
    });

    if (r.status !== 0) {
      const msg = (r.stderr || r.stdout || "").trim();
      const canFallback = !args.requireNetwork && exists(fixtureCache);
      if (canFallback && looksLikeNetworkError(msg)) {
        cacheMode = "fixture_fallback";
        cacheDirUsed = fixtureCache;
        r = run(process.execPath, [...baseArgs, "--cache-dir", fixtureCache], {
          cwd: repoRoot,
          env,
          logPath: path.join(logsDir, `${topicKey}.fixture.log`),
        });
      }
    }

    const result = {
      topic: topicId,
      topic_key: topicKey,
      status: r.status === 0 ? "ok" : "failed",
      exit_code: r.status,
      cache_mode: cacheMode,
      cache_dir_used: path.relative(repoRoot, cacheDirUsed),
      logs: {
        primary: path.relative(repoRoot, path.join(logsDir, `${topicKey}.primary.log`)),
        fixture: cacheMode === "fixture_fallback" ? path.relative(repoRoot, path.join(logsDir, `${topicKey}.fixture.log`)) : null,
      },
      report_json: path.relative(repoRoot, perReportPath),
      skill_dir: null,
      skill_md: null,
      sources_md: null,
      llm_capture: null,
      llm: null,
    };

    if (r.status === 0 && exists(perReportPath)) {
      try {
        const json = JSON.parse(fs.readFileSync(perReportPath, "utf8"));
        const topic0 = json && Array.isArray(json.topics) ? json.topics[0] : null;
        if (topic0 && topic0.skill_dir) result.skill_dir = topic0.skill_dir;
        if (topic0 && topic0.files) {
          result.skill_md = topic0.files.skill_md || null;
          result.sources_md = topic0.files.sources_md || null;
        }
        if (topic0 && topic0.llm_captures) result.llm_capture = topic0.llm_captures;
        if (json && json.llm) result.llm = json.llm;
      } catch {
        // ignore
      }
    }

    manifest.results.push(result);
    writeJsonAtomic(manifestPath, manifest);

    // Update domain README (human-friendly locator for artifacts).
    try {
      ensureDir(domainRoot);
      const readme = renderDomainReadme({ domain: args.domain, topics: cfg.topics, manifest, repoRoot });
      fs.writeFileSync(domainReadmePath, readme, "utf8");
    } catch (e) {
      console.error(`[readme] failed to update: ${String(e && e.message ? e.message : e)}`);
    }

    if (r.status !== 0) {
      anyFailed = true;
      console.error(`[run] FAILED topic=${topicId} exit=${r.status} log=${result.logs.primary}`);
      if (!args.continueOnError) break;
    } else {
      console.log(`[run] OK topic=${topicId} cache_mode=${cacheMode}`);
      if (result.skill_dir) console.log(`[run] skill_dir: ${result.skill_dir}`);
      if (result.llm_capture && result.llm_capture.rewrite_skill) console.log(`[run] llm_capture: ${result.llm_capture.rewrite_skill}`);
    }
  }

  // Back-compat: write report.json as the last successful per-topic report, if any.
  const lastOk = [...manifest.results].reverse().find((x) => x && x.status === "ok" && x.report_json);
  if (lastOk) {
    try {
      const abs = path.resolve(repoRoot, lastOk.report_json);
      fs.copyFileSync(abs, reportPath);
    } catch {
      // ignore
    }
  }

  console.log(`[run] run_id=${runId}`);
  console.log(`[run] run_dir: ${path.relative(repoRoot, runDir)}`);
  console.log(`[run] manifest_json: ${path.relative(repoRoot, manifestPath)}`);
  console.log(`[run] skills_root: ${path.relative(repoRoot, outRoot)}`);
  if (exists(domainReadmePath)) console.log(`[run] domain_readme: ${path.relative(repoRoot, domainReadmePath)}`);
  console.log(`[run] cache_dir_primary: ${cachePrimaryRel}`);
  if (exists(fixtureCache)) console.log(`[run] cache_dir_fallback: ${fixtureCacheRel}`);

  if (args.gitPush) {
    const gitRepoRoot = args.gitRepo ? path.resolve(args.gitRepo) : getGitRepoRoot(runDir);
    if (!gitRepoRoot) {
      console.error("[git] FAILED: --git-push enabled but no git repo detected (use --git-repo <path>)");
      process.exit(1);
    }

    const relRunDir = path.relative(gitRepoRoot, runDir);
    if (!relRunDir || relRunDir.startsWith("..") || path.isAbsolute(relRunDir)) {
      console.error(`[git] FAILED: run_dir is not inside git repo: run_dir=${runDir} git_repo=${gitRepoRoot}`);
      process.exit(1);
    }

    const remote = String(args.gitRemote || "origin").trim() || "origin";
    const branch = String(args.gitBranch || getGitCurrentBranch(gitRepoRoot) || "main").trim() || "main";
    const message = String(args.gitMessage || `chore(run): ${runId} (${topicsSelectors.join(", ")})`).trim() || `chore(run): ${runId}`;

    const remoteUrl = gitCmd(gitRepoRoot, ["remote", "get-url", remote]);
    if (remoteUrl.status === 0) {
      console.log(`[git] remote: ${remote} (${redactRemoteUrl(String(remoteUrl.stdout || "").trim())})`);
    } else {
      console.log(`[git] remote: ${remote} (git remote get-url failed)`);
    }
    console.log(`[git] repo: ${gitRepoRoot}`);
    console.log(`[git] branch: ${branch}`);
    console.log(`[git] paths: ${relRunDir}`);
    console.log(`[git] mode: ${args.gitDryRun ? "dry-run" : "execute"}`);

    const r = runGitAutomation({
      scriptRepoRoot: repoRoot,
      gitRepoRoot,
      remote,
      branch,
      message,
      paths: [relRunDir],
      execute: !args.gitDryRun,
    });

    if (r.stdout) process.stdout.write(r.stdout);
    if (r.stderr) process.stderr.write(r.stderr);
    if (r.status !== 0) process.exit(r.status);
  }

  if (anyFailed) process.exit(1);
}

main();
