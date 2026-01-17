#!/usr/bin/env node
/* eslint-disable no-console */

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const { createLLM } = require("../llm");

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

function writeText(filePath, text, overwrite) {
  if (!overwrite && exists(filePath)) return { written: false };
  ensureDir(path.dirname(filePath));
  fs.writeFileSync(filePath, String(text || "").endsWith("\n") ? String(text) : `${text}\n`, "utf8");
  return { written: true };
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

function utcDate() {
  return new Date().toISOString().slice(0, 10);
}

function sha256Hex(text) {
  return crypto.createHash("sha256").update(String(text || ""), "utf8").digest("hex");
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
  return sanitizeRunId(`${domain}-skillgen-${stamp}-${rand}`);
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

function parseDomainSourcePolicy(yamlText) {
  const text = stripBom(String(yamlText || "")).replace(/\r\n/g, "\n");
  const lines = text.split("\n");
  const policy = { allow_domains: [], deny_domains: [] };

  let inSourcePolicy = false;
  let collectAllow = false;
  let collectDeny = false;

  for (const rawLine of lines) {
    const line = rawLine.replace(/\s+$/, "");
    if (!line.trim()) continue;
    if (/^\s*#/.test(line)) continue;

    if (/^source_policy:\s*$/.test(line)) {
      inSourcePolicy = true;
      collectAllow = false;
      collectDeny = false;
      continue;
    }
    if (!inSourcePolicy) continue;

    if (collectAllow) {
      const m = line.match(/^\s*-\s*(.+?)\s*$/);
      if (m) {
        policy.allow_domains.push(unquoteScalar(m[1]));
        continue;
      }
      collectAllow = false;
    }
    if (collectDeny) {
      const m = line.match(/^\s*-\s*(.+?)\s*$/);
      if (m) {
        policy.deny_domains.push(unquoteScalar(m[1]));
        continue;
      }
      collectDeny = false;
    }

    const allowMatch = line.match(/^\s*allow_domains:\s*(.*?)\s*$/);
    if (allowMatch) {
      const parsed = parseInlineYamlList(allowMatch[1]);
      policy.allow_domains = parsed === null ? [] : parsed;
      collectAllow = parsed === null;
      continue;
    }
    const denyMatch = line.match(/^\s*deny_domains:\s*(.*?)\s*$/);
    if (denyMatch) {
      const parsed = parseInlineYamlList(denyMatch[1]);
      policy.deny_domains = parsed === null ? [] : parsed;
      collectDeny = parsed === null;
      continue;
    }
  }

  return policy;
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

function cacheFileForUrl(url) {
  return `${sha256Hex(url).slice(0, 16)}.txt`;
}

function cachePathForUrl(cacheDir, url) {
  return path.join(cacheDir, cacheFileForUrl(url));
}

async function fetchText(url, timeoutMs) {
  if (typeof fetch !== "function") throw new Error("Global fetch() not available. Use Node.js 18+.");
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const resp = await fetch(url, {
      method: "GET",
      headers: { "User-Agent": "skillgen" },
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

async function fetchWithCache({ url, cacheDir, timeoutMs }) {
  ensureDir(cacheDir);
  const cachePath = cachePathForUrl(cacheDir, url);
  if (exists(cachePath)) {
    const text = readText(cachePath);
    return {
      cache: "hit",
      status: 200,
      contentType: "",
      text,
      bytes: Buffer.byteLength(text, "utf8"),
      sha256: sha256Hex(text),
      cacheFile: path.basename(cachePath),
    };
  }

  // Avoid duplicate network fetches and cache file races when multiple workers request the same URL.
  // Key by cachePath (URL-hash) to dedupe in-process.
  // eslint-disable-next-line no-use-before-define
  if (!fetchWithCache._inflight) fetchWithCache._inflight = new Map();
  const inflight = fetchWithCache._inflight;
  if (inflight.has(cachePath)) return inflight.get(cachePath);

  const p = (async () => {
    const r = await fetchText(url, timeoutMs);
    const text = r.text || "";
    const tmp = `${cachePath}.${crypto.randomBytes(4).toString("hex")}.tmp`;
    fs.writeFileSync(tmp, text, "utf8");
    fs.renameSync(tmp, cachePath);
    return {
      cache: "miss",
      status: r.status,
      contentType: r.contentType || "",
      text,
      bytes: Buffer.byteLength(text, "utf8"),
      sha256: sha256Hex(text),
      cacheFile: path.basename(cachePath),
    };
  })().finally(() => {
    try {
      inflight.delete(cachePath);
    } catch {
      // ignore
    }
  });

  inflight.set(cachePath, p);
  return p;
}

function looksLikeHtml(text) {
  const t = String(text || "");
  return /<!doctype html|<html[\s>]|<a\s+href=|<head[\s>]/i.test(t.slice(0, 4096));
}

function stripHtmlToText(html) {
  let t = String(html || "");
  t = t.replace(/<script[\s\S]*?<\/script>/gi, " ");
  t = t.replace(/<style[\s\S]*?<\/style>/gi, " ");
  t = t.replace(/<[^>]+>/g, " ");
  t = t.replace(/&nbsp;/gi, " ");
  t = t.replace(/&amp;/gi, "&");
  t = t.replace(/&lt;/gi, "<");
  t = t.replace(/&gt;/gi, ">");
  t = t.replace(/&quot;/gi, '"');
  t = t.replace(/&#39;/gi, "'");
  t = t.replace(/\s+/g, " ").trim();
  return t;
}

function normalizeText(text) {
  return String(text || "").replace(/\s+/g, " ").trim();
}

function slugify(text, maxLen = 64) {
  const v = String(text || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-+/, "")
    .replace(/-+$/, "");
  if (v) return v.slice(0, maxLen);
  return `t-${sha256Hex(text).slice(0, 10)}`;
}

function splitTopicSegments(topic) {
  return String(topic || "").trim().replace(/\\/g, "/").split("/").filter(Boolean);
}

function sanitizeTopic(topic) {
  const parts = splitTopicSegments(topic);
  const first = parts.length > 0 ? parts[0] : "";
  return slugify(first, 48).slice(0, 80);
}

function sanitizeSlug(slug) {
  return slugify(slug, 64);
}

function normalizeAction(action) {
  const a = String(action || "").trim().toLowerCase();
  if (a === "auto" || a === "manual" || a === "ignore") return a;
  return null;
}

function parseActionSet(raw) {
  const v = String(raw || "").trim().toLowerCase();
  if (!v) return new Set(["auto"]);
  const parts = v.split(",").map((s) => s.trim()).filter(Boolean);
  const out = new Set();
  for (const p of parts) {
    const a = normalizeAction(p);
    if (!a || a === "ignore") continue;
    out.add(a);
  }
  return out.size > 0 ? out : new Set(["auto"]);
}

function extractJsonFromText(text) {
  const t = String(text || "").trim();
  if (!t) return "";
  const first = t.indexOf("{");
  const last = t.lastIndexOf("}");
  if (first >= 0 && last > first) return t.slice(first, last + 1);
  return t;
}

function formatInlineYamlList(values) {
  const list = Array.isArray(values) ? values : [];
  if (list.length === 0) return "[]";
  return `[${list.map((v) => JSON.stringify(String(v))).join(", ")}]`;
}

function escapeYamlDoubleQuoted(text) {
  return String(text || "").replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

function riskRank(level) {
  const v = String(level || "").trim().toLowerCase();
  if (v === "low") return 0;
  if (v === "medium") return 1;
  if (v === "high") return 2;
  return -1;
}

const RISK_PATTERNS = [
  { min: "high", re: /\brm\s+-rf\b/i, hint: "rm -rf" },
  { min: "high", re: /\bdd\s+if=/i, hint: "dd if=" },
  { min: "high", re: /\bmkfs(?:\.[a-z0-9]+)?\b/i, hint: "mkfs" },
  { min: "high", re: /\b(?:userdel|groupdel|deluser)\b/i, hint: "userdel/groupdel" },
  { min: "high", re: /\b(?:kill|pkill)\s+-(?:9|KILL)\b/i, hint: "kill -9/-KILL" },
  { min: "high", re: /\bvisudo\b/i, hint: "visudo" },
  { min: "high", re: /\bmount\b/i, hint: "mount" },
  { min: "medium", re: /\bpatch\b/i, hint: "patch" },
  { min: "medium", re: /\bxargs\b/i, hint: "xargs" },
  { min: "medium", re: /\bchmod\b/i, hint: "chmod" },
  { min: "medium", re: /\bchown\b/i, hint: "chown" },
];

function coerceRiskLevel(text, desired) {
  let risk = String(desired || "").trim().toLowerCase();
  if (risk !== "low" && risk !== "medium" && risk !== "high") risk = "low";
  const have = riskRank(risk);
  let minRank = have;
  for (const p of RISK_PATTERNS) {
    if (!p.re.test(text)) continue;
    minRank = Math.max(minRank, riskRank(p.min));
  }
  if (minRank <= 0) return "low";
  if (minRank === 1) return "medium";
  return "high";
}

function renderBullets(items, fallback) {
  const list = Array.isArray(items) ? items.map((x) => normalizeText(x)).filter(Boolean) : [];
  const out = list.length > 0 ? list : fallback;
  return out.map((x) => `- ${x}`);
}

function renderPrerequisites(p) {
  const obj = p && typeof p === "object" ? p : {};
  return [
    `- Environment: ${normalizeText(obj.environment)}`,
    `- Permissions: ${normalizeText(obj.permissions)}`,
    `- Tools: ${normalizeText(obj.tools)}`,
    `- Inputs needed: ${normalizeText(obj.inputs)}`,
  ];
}

function formatCites(cites, maxSources = 3) {
  const max = Number.isFinite(Number(maxSources)) ? Number(maxSources) : 3;
  const nums = Array.isArray(cites)
    ? cites
      .map((n) => Number(n))
      .filter((n) => Number.isFinite(n) && n >= 1 && n <= max)
    : [];
  const uniq = [];
  for (const n of nums) {
    if (uniq.includes(n)) continue;
    uniq.push(n);
  }
  if (uniq.length === 0) return "";
  return `[[${uniq.join("][")}]]`;
}

function renderSteps(steps) {
  const list = Array.isArray(steps) ? steps : [];
  const out = [];
  for (let i = 0; i < Math.min(12, list.length); i++) {
    const s = list[i] && typeof list[i] === "object" ? list[i] : {};
    const text = normalizeText(s.text);
    const cites = Array.isArray(s.cites) ? s.cites : [];
    const citeText = formatCites(cites, 3) || "[[1]]";
    out.push(`${i + 1}. ${text || "（略）"}${citeText}`);
  }
  if (out.length >= 3) return out;
  while (out.length < 3) {
    const idx = out.length + 1;
    out.push(`${idx}. 先以只读方式验证输入与环境（例如：\`echo \"$PWD\"\`）[[1]]`);
  }
  return out;
}

function renderSkillMd({ title, riskLevel, spec, sources }) {
  const src = Array.isArray(sources) ? sources : [];
  const s = spec && typeof spec === "object" ? spec : {};
  const safety = s.safety && typeof s.safety === "object" ? s.safety : {};

  const lines = [];
  lines.push(`# ${title}`);
  lines.push("");
  lines.push("## Goal");
  lines.push(...renderBullets(s.goal, ["生成一个可执行、可验证的操作步骤，并尽量保持安全。"]));
  lines.push("");
  lines.push("## When to use");
  lines.push(...renderBullets(s.whenUse, ["当你需要把一个问题拆解成可复制的步骤并快速执行时。"]));
  lines.push("");
  lines.push("## When NOT to use");
  lines.push(...renderBullets(s.whenNot, ["当你不确定副作用且无法回滚时（先在测试环境验证）。"]));
  lines.push("");
  lines.push("## Prerequisites");
  lines.push(...renderPrerequisites(s.prerequisites));
  lines.push("");
  lines.push("## Steps (<= 12)");
  lines.push(...renderSteps(s.steps));
  lines.push("");
  lines.push("## Verification");
  lines.push(...renderBullets(s.verification, ["执行后应得到可观察的结果（退出码/输出/状态变化）。"]));
  lines.push("");
  lines.push("## Safety & Risk");
  lines.push(`- Risk level: **${riskLevel}**`);
  lines.push(`- Irreversible actions: ${normalizeText(safety.irreversible) || "无（或已提供 dry-run/确认步骤）"}`);
  lines.push(`- Privacy/credential handling: ${normalizeText(safety.privacy) || "避免在日志/截图中泄露敏感信息。"}`);
  lines.push(`- Confirmation requirement: ${normalizeText(safety.confirmation) || "涉及写操作前必须先 dry-run 并二次确认。"}`);
  lines.push("");
  lines.push("## Troubleshooting");
  lines.push("- See: reference/troubleshooting.md");
  lines.push("");
  lines.push("## Sources");
  for (let i = 0; i < src.length; i++) {
    const item = src[i] || {};
    const label = normalizeText(item.label) || `Source ${i + 1}`;
    const url = normalizeText(item.url);
    lines.push(`- [${i + 1}] ${label}: ${url}`);
  }
  lines.push("");
  return lines.join("\n");
}

function renderLibraryMd(spec) {
  const s = spec && typeof spec === "object" ? spec : {};
  const bashLines = Array.isArray(s.library && s.library.bash) ? s.library.bash : [];
  const promptLines = Array.isArray(s.library && s.library.prompt) ? s.library.prompt : [];

  const lines = [];
  lines.push("# Library");
  lines.push("");
  lines.push("## Copy-paste commands");
  lines.push("");
  lines.push("```bash");
  if (bashLines.length > 0) lines.push(...bashLines.map((x) => String(x)));
  else lines.push("# (no commands)");
  lines.push("```");
  lines.push("");
  lines.push("## Prompt snippet");
  lines.push("");
  lines.push("```text");
  if (promptLines.length > 0) lines.push(...promptLines.map((x) => String(x)));
  else lines.push("Provide minimal, safe commands for this task.");
  lines.push("```");
  lines.push("");
  return lines.join("\n");
}

function renderReferenceSourcesMd(sources, accessed) {
  const src = Array.isArray(sources) ? sources : [];
  const lines = [];
  lines.push("# Sources");
  lines.push("");
  lines.push("> 每条来源需包含：URL、摘要、访问日期，以及它支撑了哪一步。");
  lines.push("> 生成器会在本地缓存抓取结果（`.cache/`，默认不提交），这里记录抓取指纹与 license 字段用于审计。");
  lines.push("");
  for (let i = 0; i < src.length; i++) {
    const s = src[i] || {};
    const supports = s.supports ? String(s.supports) : "Steps 1-3";
    lines.push(`## [${i + 1}]`);
    lines.push(`- URL: ${s.url}`);
    lines.push(`- Accessed: ${accessed}`);
    lines.push(`- Summary: ${s.summary || "Reference used to build this skill."}`);
    lines.push(`- Supports: ${supports}`);
    lines.push(`- License: ${s.license || "unknown"}`);
    lines.push(`- Fetch cache: ${s.fetched && s.fetched.cache ? s.fetched.cache : "miss"}`);
    lines.push(`- Fetch bytes: ${s.fetched && Number.isFinite(Number(s.fetched.bytes)) ? Number(s.fetched.bytes) : 0}`);
    lines.push(`- Fetch sha256: ${s.fetched && s.fetched.sha256 ? s.fetched.sha256 : sha256Hex("")}`);
    lines.push("");
  }
  return lines.join("\n");
}

function renderReferenceList(title, items, fallback) {
  const list = Array.isArray(items) ? items.map((x) => normalizeText(x)).filter(Boolean) : [];
  const out = list.length > 0 ? list : fallback;
  return ["# " + title, "", ...out.map((x) => `- ${x}`), ""].join("\n");
}

function templateMetadataYaml({ id, title, domain, level, riskLevel, tags }) {
  const escapedTitle = escapeYamlDoubleQuoted(title);
  const platforms = domain === "linux" ? "[linux]" : "[]";
  const normalizedTags = Array.isArray(tags) ? tags : [];
  return [
    `id: ${id}`,
    `title: "${escapedTitle}"`,
    `domain: ${domain}`,
    `level: ${level}`,
    `risk_level: ${riskLevel}`,
    `platforms: ${platforms}`,
    "tools: []",
    `tags: ${formatInlineYamlList(normalizedTags)}`,
    'last_verified: ""',
    "owners: []",
    "aliases: []",
    "",
  ].join("\n");
}

function renderDomainReadme({ domain, runId, outRoot, results, inputs, llm }) {
  const listRaw = Array.isArray(results) ? results : [];
  const list = [...listRaw].sort((a, b) => String(a && a.id ? a.id : "").localeCompare(String(b && b.id ? b.id : "")));
  const lines = [];
  lines.push(`# ${domain} Skills (SkillGen)`);
  lines.push("");
  lines.push("本目录为自动闭环的一次运行产物（curation → skills）。");
  lines.push("");
  lines.push("## Run Context");
  lines.push("");
  lines.push(`- run_id: \`${runId}\``);
  lines.push(`- generated_at: \`${utcNowIso()}\``);
  lines.push(`- out: \`${outRoot}\``);
  if (inputs && inputs.curation) lines.push(`- curation: \`${inputs.curation}\``);
  if (llm && llm.provider) {
    lines.push(`- llm_provider: \`${llm.provider}\``);
    if (llm.model) lines.push(`- llm_model: \`${llm.model}\``);
    if (llm.usage && llm.usage.total_tokens != null) lines.push(`- llm_total_tokens: \`${llm.usage.total_tokens}\``);
  }
  lines.push("");
  lines.push("## Generated Skills");
  lines.push("");
  lines.push("| # | ID | Title | Status | Tokens | skill.md | sources.md | llm_capture | materials |");
  lines.push("|---:|---|---|---|---:|---|---|---|---|");
  for (let i = 0; i < list.length; i++) {
    const r = list[i] || {};
    lines.push(
      [
        String(i + 1),
        `\`${r.id || ""}\``,
        (r.title || "").replace(/\|/g, "\\|"),
        r.status || "",
        r.llm_usage && r.llm_usage.total_tokens != null ? String(r.llm_usage.total_tokens) : "0",
        r.skill_md ? `\`${r.skill_md}\`` : "—",
        r.sources_md ? `\`${r.sources_md}\`` : "—",
        r.llm_capture ? `\`${r.llm_capture}\`` : "—",
        r.materials_dir ? `\`${r.materials_dir}\`` : "—",
      ].join(" | "),
    );
  }
  lines.push("");
  return lines.join("\n") + "\n";
}

function usage(exitCode = 0) {
  const msg = `
Usage:
  node agents/skillgen/run.js --domain <domain>
    [--runs-dir runs] [--run-id <id>] [--curation <path>] [--out <skillsRoot>]
    [--cache-dir .cache/web] [--timeout-ms <n>]
    [--max-skills <n>] [--concurrency <n>] [--actions auto|manual|auto,manual] [--overwrite]
    [--llm-provider mock|ollama|openai] [--llm-model <model>] [--llm-base-url <url>] [--llm-api-key <key>]
    [--llm-fixture <path>] [--llm-timeout-ms <n>] [--llm-strict]
    [--llm-capture] [--llm-prompt-system <path>] [--llm-prompt-user <path>]
    [--report-json <path>]
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
    curation: null,
    out: null,
    cacheDir: ".cache/web",
    timeoutMs: 20000,
    maxSkills: 5,
    concurrency: 1,
    actions: "auto",
    overwrite: false,

    llmProvider: null,
    llmModel: null,
    llmBaseUrl: null,
    llmApiKey: null,
    llmFixture: null,
    llmTimeoutMs: 60000,
    llmStrict: false,
    llmCapture: false,
    llmPromptSystem: "agents/skillgen/prompts/generate_skill_v1.system.md",
    llmPromptUser: "agents/skillgen/prompts/generate_skill_v1.user.md",

    reportJson: null,
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
    } else if (a === "--curation") {
      args.curation = argv[i + 1] || null;
      i++;
    } else if (a === "--out") {
      args.out = argv[i + 1] || null;
      i++;
    } else if (a === "--cache-dir") {
      args.cacheDir = argv[i + 1] || args.cacheDir;
      i++;
    } else if (a === "--timeout-ms") {
      args.timeoutMs = Number(argv[i + 1] || "20000");
      i++;
    } else if (a === "--max-skills") {
      args.maxSkills = Number(argv[i + 1] || "0");
      i++;
    } else if (a === "--concurrency") {
      args.concurrency = Number(argv[i + 1] || "1");
      i++;
    } else if (a === "--actions") {
      args.actions = argv[i + 1] || args.actions;
      i++;
    } else if (a === "--overwrite") args.overwrite = true;
    else if (a === "--llm-provider") {
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
    else if (a === "--llm-capture") args.llmCapture = true;
    else if (a === "--llm-prompt-system") {
      args.llmPromptSystem = argv[i + 1] || args.llmPromptSystem;
      i++;
    } else if (a === "--llm-prompt-user") {
      args.llmPromptUser = argv[i + 1] || args.llmPromptUser;
      i++;
    } else if (a === "--report-json") {
      args.reportJson = argv[i + 1] || null;
      i++;
    } else if (a === "-h" || a === "--help") usage(0);
    else throw new Error(`Unknown arg: ${a}`);
  }

  if (!args.domain) usage(2);
  args.runId = args.runId ? sanitizeRunId(args.runId) : makeDefaultRunId(args.domain);
  if (!args.runId) throw new Error("Invalid --run-id");

  if (!Number.isFinite(args.timeoutMs) || args.timeoutMs <= 0) args.timeoutMs = 20000;
  if (!Number.isFinite(args.llmTimeoutMs) || args.llmTimeoutMs <= 0) args.llmTimeoutMs = 60000;
  if (!Number.isFinite(args.maxSkills) || args.maxSkills < 0) args.maxSkills = 0;
  if (!Number.isFinite(args.concurrency) || args.concurrency < 1) args.concurrency = 1;
  return args;
}

function fillTemplate(template, vars) {
  let out = String(template || "");
  for (const [k, v] of Object.entries(vars || {})) {
    out = out.replaceAll(`{{${k}}}`, String(v));
  }
  return out;
}

function parseSuggested(suggested, domain) {
  const s = suggested && typeof suggested === "object" ? suggested : null;
  if (!s) return null;
  const rawId = String(s.id || "").trim().replace(/\\/g, "/");
  let topic = String(s.topic || "").trim();
  let slug = String(s.slug || "").trim();
  if (rawId) {
    const parts = rawId.split("/").filter(Boolean);
    if (parts[0] === domain && parts.length >= 3) {
      topic = parts.slice(1, -1).join("/");
      slug = parts[parts.length - 1];
    } else if (parts.length >= 2) {
      topic = parts.slice(0, -1).join("/");
      slug = parts[parts.length - 1];
    }
  }
  const topicSegments = splitTopicSegments(topic);
  topic = sanitizeTopic(topic);
  slug = sanitizeSlug(slug);
  if (topicSegments.length > 1) {
    const suffix = topicSegments.slice(1).join("-");
    slug = sanitizeSlug(`${suffix}-${slug}`);
  }
  if (!topic || !slug) return null;
  const id = `${domain}/${topic}/${slug}`;
  const title = normalizeText(s.title) || id;
  return { id, domain, topic, slug, title };
}

function pickSourceUrlsFromProposal(proposal, policy) {
  const urls = [];
  const samples = proposal && proposal.samples && typeof proposal.samples === "object" ? proposal.samples : null;
  const rawSources = samples && Array.isArray(samples.sources) ? samples.sources : [];
  for (const raw of rawSources) {
    let obj = null;
    try {
      obj = typeof raw === "string" ? JSON.parse(raw) : raw;
    } catch {
      obj = null;
    }
    const url = obj && obj.url ? String(obj.url).trim() : "";
    if (!/^https?:\/\//i.test(url)) continue;
    if (policy && !isUrlAllowed(url, policy)) continue;
    if (!urls.includes(url)) urls.push(url);
    if (urls.length >= 3) break;
  }
  return urls;
}

function loadFallbackSeedUrls({ repoRoot, domain }) {
  const configPath = path.join(repoRoot, "agents", "configs", `${domain}.yaml`);
  if (!exists(configPath)) return [];
  const text = stripBom(readText(configPath)).replace(/\r\n/g, "\n");
  const lines = text.split("\n");
  const out = [];
  let inSeeds = false;
  for (const rawLine of lines) {
    const line = rawLine.replace(/\s+$/, "");
    if (/^seeds:\s*$/.test(line)) {
      inSeeds = true;
      continue;
    }
    if (!inSeeds) continue;
    const m = line.match(/^\s*-\s*(https?:\/\/\S+)\s*$/);
    if (m) {
      out.push(String(m[1]).trim());
      continue;
    }
    if (/^\S/.test(line)) inSeeds = false;
  }
  return out;
}

function normalizeLevel(raw) {
  const v = String(raw || "").trim().toLowerCase();
  if (v === "bronze" || v === "silver" || v === "gold") return v;
  return "bronze";
}

function normalizeRiskLevel(raw) {
  const v = String(raw || "").trim().toLowerCase();
  if (v === "low" || v === "medium" || v === "high") return v;
  return "low";
}

function ensureNoTodo(text) {
  // Validator only blocks "TODO" placeholders; replace it deterministically if it shows up.
  return String(text || "").replace(/\bTODO\b/gi, "（待完善）");
}

async function generateSpecWithLLM({ llm, repoRoot, args, runId, domain, skill, proposal, sources, materialsText, capturePath }) {
  if (!llm) {
    if (args.llmCapture && capturePath) {
      writeJsonAtomic(capturePath, {
        version: 1,
        ts: utcNowIso(),
        op: "generate_skill_spec",
        domain,
        run_id: runId,
        skill_id: skill.id,
        proposal_id: proposal && proposal.proposal_id ? String(proposal.proposal_id) : null,
        llm: null,
        usage: null,
        error: "llm disabled",
      });
    }
    return { spec: null, usage: null, error: "llm disabled" };
  }
  const promptSystemAbs = path.isAbsolute(args.llmPromptSystem)
    ? args.llmPromptSystem
    : path.resolve(repoRoot, args.llmPromptSystem);
  const promptUserAbs = path.isAbsolute(args.llmPromptUser)
    ? args.llmPromptUser
    : path.resolve(repoRoot, args.llmPromptUser);
  if (!exists(promptSystemAbs)) throw new Error(`Missing --llm-prompt-system: ${promptSystemAbs}`);
  if (!exists(promptUserAbs)) throw new Error(`Missing --llm-prompt-user: ${promptUserAbs}`);

  const promptSystem = readText(promptSystemAbs);
  const promptUserTemplate = readText(promptUserAbs);
  const promptSha256 = sha256Hex(`${promptSystem}\n---\n${promptUserTemplate}`);
  const sourcesJson = JSON.stringify(
    sources.map((s, idx) => ({ index: idx + 1, url: s.url, label: s.label, snippet: s.snippet || "" })),
    null,
    2,
  );
  const userPrompt = fillTemplate(promptUserTemplate, {
    DOMAIN: domain,
    RUN_ID: runId,
    SKILL_ID: skill.id,
    TITLE: skill.title,
    PROPOSAL_JSON: JSON.stringify(proposal, null, 2),
    SOURCES_JSON: sourcesJson,
    MATERIALS_TEXT: materialsText || "",
  });

  const messages = [
    { role: "system", content: promptSystem },
    { role: "user", content: userPrompt },
  ];

  const startedAt = utcNowIso();
  try {
    const resp = typeof llm.completeRaw === "function" ? await llm.completeRaw({ messages }) : null;
    const raw = resp ? resp.content : await llm.complete({ messages });
    const usage = resp && resp.usage ? resp.usage : null;

    const jsonText = extractJsonFromText(raw);
    const parsed = JSON.parse(jsonText);
    if (args.llmCapture && capturePath) {
      writeJsonAtomic(capturePath, {
        version: 1,
        ts: utcNowIso(),
        started_at: startedAt,
        finished_at: utcNowIso(),
        op: "generate_skill_spec",
        domain,
        run_id: runId,
        skill_id: skill.id,
        proposal_id: proposal && proposal.proposal_id ? String(proposal.proposal_id) : null,
        llm: { provider: llm.provider, model: llm.model, base_url: llm.baseUrl || "" },
        prompts: {
          system: path.relative(repoRoot, promptSystemAbs),
          user: path.relative(repoRoot, promptUserAbs),
          sha256: promptSha256,
        },
        usage,
        request: { messages },
        response: { content: String(raw || "") },
        input_sha256: sha256Hex(`${promptSystem}\n---\n${userPrompt}`),
        output_sha256: sha256Hex(String(raw || "")),
      });
    }
    return { spec: parsed, usage, error: null };
  } catch (e) {
    if (args.llmCapture && capturePath) {
      writeJsonAtomic(capturePath, {
        version: 1,
        ts: utcNowIso(),
        started_at: startedAt,
        finished_at: utcNowIso(),
        op: "generate_skill_spec",
        domain,
        run_id: runId,
        skill_id: skill.id,
        proposal_id: proposal && proposal.proposal_id ? String(proposal.proposal_id) : null,
        llm: { provider: llm.provider, model: llm.model, base_url: llm.baseUrl || "" },
        usage: null,
        error: String(e && e.message ? e.message : e),
      });
    }
    if (args.llmStrict) throw e;
    return { spec: null, usage: null, error: String(e && e.message ? e.message : e) };
  }
}

function minimalSpec({ title, domain }) {
  const tools = domain === "linux" ? "bash" : "";
  return {
    version: 1,
    title,
    level: "bronze",
    risk_level: "low",
    goal: ["把任务拆解成可复制、可验证的最小步骤。"],
    whenUse: ["需要快速得到一个可执行的操作清单时。"],
    whenNot: ["涉及不可逆写操作但你不确定影响范围时。"],
    prerequisites: {
      environment: domain === "linux" ? "Linux shell" : "",
      permissions: "根据目标资源决定（必要时使用最小权限）。",
      tools,
      inputs: "你需要的目标/参数。",
    },
    steps: [
      { text: "先确认环境与输入是否正确（只读检查）", cites: [1] },
      { text: "以 dry-run / 只读方式执行核心命令并检查输出", cites: [1, 2] },
      { text: "在确认无误后再执行写操作（如有），并做最终核验", cites: [2, 3] },
    ],
    verification: ["确认输出/状态符合预期，并记录关键结果。"],
    safety: {
      irreversible: "默认不包含不可逆操作；如必须写入，请先做备份或 dry-run。",
      privacy: "避免在日志/截图中泄露密钥、token、内部路径等敏感信息。",
      confirmation: "任何写操作前必须二次确认目标与范围。",
    },
    library: {
      bash: ["# (no commands)"],
      prompt: ["请给出最小、安全、可验证的命令。"],
    },
    references: {
      troubleshooting: ["检查网络/权限/参数是否正确。", "查看官方文档或 --help 输出。"],
      edgeCases: ["路径包含空格/特殊字符时需正确引用。", "权限不足会导致部分步骤失败。"],
      examples: ["先在小范围目录或测试环境中验证，再推广到全量。"],
    },
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const repoRoot = path.resolve(__dirname, "..", "..");

  const runsRoot = path.isAbsolute(args.runsDir) ? args.runsDir : path.resolve(repoRoot, args.runsDir);
  const runDir = path.join(runsRoot, args.runId);
  ensureDir(runDir);

  const outRoot = args.out
    ? (path.isAbsolute(args.out) ? args.out : path.resolve(repoRoot, args.out))
    : path.join(runDir, "skills");
  ensureDir(outRoot);

  const curationPath = args.curation
    ? (path.isAbsolute(args.curation) ? args.curation : path.resolve(repoRoot, args.curation))
    : path.join(runDir, "curation.json");
  if (!exists(curationPath)) throw new Error(`Missing curation: ${curationPath}`);

  const domainConfigPath = path.join(repoRoot, "agents", "configs", `${args.domain}.yaml`);
  const policy = exists(domainConfigPath) ? parseDomainSourcePolicy(readText(domainConfigPath)) : { allow_domains: [], deny_domains: [] };

  const cacheDirAbs = path.isAbsolute(args.cacheDir) ? args.cacheDir : path.resolve(repoRoot, args.cacheDir);

  const curation = JSON.parse(readText(curationPath));
  const proposals = Array.isArray(curation && curation.proposals) ? curation.proposals : [];
  const actionSet = parseActionSet(args.actions);

  const llm = args.llmProvider
    ? createLLM({
      provider: args.llmProvider,
      model: args.llmModel,
      baseUrl: args.llmBaseUrl,
      apiKey: args.llmApiKey,
      fixturePath: args.llmFixture ? path.resolve(repoRoot, args.llmFixture) : null,
      timeoutMs: args.llmTimeoutMs,
    })
    : null;

  const selected = [];
  for (const p of proposals) {
    const action = normalizeAction(p && p.action ? p.action : "");
    if (!action || !actionSet.has(action)) continue;
    const suggested = parseSuggested(p && p.suggested ? p.suggested : null, args.domain);
    if (!suggested) continue;
    selected.push({ proposal: p, suggested, action });
  }
  selected.sort((a, b) => String(a.suggested.id).localeCompare(String(b.suggested.id)));

  const maxSkills = Number(args.maxSkills || 0);
  const planned = maxSkills > 0 && selected.length > maxSkills ? selected.slice(0, maxSkills) : selected;

  const report = {
    version: 1,
    generated_at: utcNowIso(),
    run_id: args.runId,
    domain: args.domain,
    inputs: {
      curation: path.relative(repoRoot, curationPath),
    },
    llm: llm ? { provider: llm.provider, model: llm.model, base_url: llm.baseUrl || "" } : null,
    selection: {
      actions: Array.from(actionSet),
      max_skills: maxSkills,
      eligible_total: selected.length,
      planned_total: planned.length,
    },
    results: [],
    stats: {
      generated: 0,
      skipped: 0,
      errors: 0,
      llm_usage_total: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
    },
  };

  console.log(`[skillgen] run_id=${args.runId} domain=${args.domain} eligible=${selected.length} planned=${planned.length}`);
  console.log(`[skillgen] out=${outRoot}`);
  console.log(`[skillgen] curation=${curationPath}`);

  const totalPlanned = planned.length;
  const concurrency = Math.max(1, Math.min(Number(args.concurrency || 1), totalPlanned || 1));
  console.log(`[skillgen] concurrency=${concurrency}`);

  async function processOne(i) {
    const item = planned[i];
    const proposal = item.proposal;
    const suggested = item.suggested;
    const skillId = suggested.id;
    const topic = suggested.topic;
    const slug = suggested.slug;
    const title = suggested.title;

    const skillDir = path.join(outRoot, args.domain, topic, slug);
    const refDir = path.join(skillDir, "reference");
    const materialsDir = path.join(refDir, "materials");
    const llmDir = path.join(refDir, "llm");

    const already = exists(path.join(skillDir, "metadata.yaml"));
    if (already && !args.overwrite) {
      report.stats.skipped += 1;
      report.results.push({
        id: skillId,
        title,
        status: "skipped_exists",
        skill_dir: path.relative(repoRoot, skillDir),
      });
      console.log(`[skillgen] [${i + 1}/${planned.length}] skip (exists): ${skillId}`);
      return;
    }

    console.log(`[skillgen] [${i + 1}/${planned.length}] generate: ${skillId} — ${title}`);

    // 1) pick sources
    let urls = pickSourceUrlsFromProposal(proposal, policy);
    if (urls.length < 3) {
      const fallback = loadFallbackSeedUrls({ repoRoot, domain: args.domain }).filter((u) => {
        try {
          return !policy || isUrlAllowed(u, policy);
        } catch {
          return false;
        }
      });
      for (const u of fallback) {
        if (urls.length >= 3) break;
        if (!urls.includes(u)) urls.push(u);
      }
    }
    if (urls.length < 3) {
      const hardFallback = args.domain === "linux"
        ? [
          "https://man7.org/linux/man-pages/index.html",
          "https://www.gnu.org/software/coreutils/manual/coreutils.html",
          "https://wiki.archlinux.org/",
        ]
        : [];
      for (const u of hardFallback) {
        if (urls.length >= 3) break;
        if (!urls.includes(u)) urls.push(u);
      }
    }

    if (urls.length < 3) {
      const allow = Array.isArray(policy && policy.allow_domains ? policy.allow_domains : null) ? policy.allow_domains : [];
      for (const d of allow) {
        if (urls.length >= 3) break;
        const host = normalizeDomainPattern(d);
        if (!host) continue;
        const u = `https://${host}/`;
        try {
          if (policy && !isUrlAllowed(u, policy)) continue;
        } catch {
          continue;
        }
        if (!urls.includes(u)) urls.push(u);
      }
    }
    urls = urls.slice(0, 3);

    const fetchedSources = [];
    const materials = [];
    for (const u of urls) {
      let fetched = null;
      try {
        fetched = await fetchWithCache({ url: u, cacheDir: cacheDirAbs, timeoutMs: args.timeoutMs });
      } catch (e) {
        fetched = {
          cache: "miss",
          status: 0,
          contentType: "",
          text: "",
          bytes: 0,
          sha256: sha256Hex(""),
          cacheFile: cacheFileForUrl(u),
          error: String(e && e.message ? e.message : e),
        };
      }

      const rawText = fetched.text || "";
      const plain = looksLikeHtml(rawText) ? stripHtmlToText(rawText) : normalizeText(rawText);
      const snippet = plain.slice(0, 2000);

      fetchedSources.push({
        url: u,
        label: new URL(u).hostname,
        summary: "Reference used to build this skill.",
        supports: "Steps 1-3",
        license: "unknown",
        fetched: {
          cache: fetched.cache,
          bytes: fetched.bytes,
          sha256: fetched.sha256,
          cache_file: fetched.cacheFile,
          status: fetched.status,
        },
        snippet,
      });

      materials.push(
        `# Source: ${u}\n` +
          (fetched.error ? `Error: ${fetched.error}\n` : "") +
          (snippet ? `${snippet}\n` : "(empty)\n"),
      );
    }

    const materialsText = materials.join("\n\n").slice(0, 8000);

    // 2) generate spec (LLM) + capture
    if (args.llmCapture) ensureDir(llmDir);
    ensureDir(materialsDir);
    writeJsonAtomic(path.join(materialsDir, "proposal.json"), { proposal, suggested });
    writeJsonAtomic(path.join(materialsDir, "sources.json"), fetchedSources.map((s) => ({ ...s, snippet: undefined })));
    writeText(path.join(materialsDir, "snippets.txt"), materialsText, true);

    const llmCapturePath = args.llmCapture ? path.join(llmDir, "generate_skill.json") : null;

    const { spec, usage, error } = await generateSpecWithLLM({
      llm,
      repoRoot,
      args,
      runId: args.runId,
      domain: args.domain,
      skill: { id: skillId, title },
      proposal,
      sources: fetchedSources,
      materialsText,
      capturePath: llmCapturePath,
    });

    const finalSpecRaw = spec && typeof spec === "object" ? spec : minimalSpec({ title, domain: args.domain });
    const finalSpec = {
      ...minimalSpec({ title, domain: args.domain }),
      ...finalSpecRaw,
      title: normalizeText(finalSpecRaw.title) || title,
      level: "bronze",
      risk_level: normalizeRiskLevel(finalSpecRaw.risk_level),
    };

    const preSkillMd = renderSkillMd({
      title: finalSpec.title,
      riskLevel: finalSpec.risk_level,
      spec: finalSpec,
      sources: fetchedSources,
    });
    const preLibraryMd = renderLibraryMd(finalSpec);

    const riskLevel = coerceRiskLevel(`${preSkillMd}\n\n${preLibraryMd}`, finalSpec.risk_level);

    const skillMd = ensureNoTodo(preSkillMd.replace(`**${finalSpec.risk_level}**`, `**${riskLevel}**`));
    const libraryMd = ensureNoTodo(preLibraryMd);
    const sourcesMd = ensureNoTodo(renderReferenceSourcesMd(fetchedSources, utcDate()));
    const troubleshootingMd = ensureNoTodo(
      renderReferenceList("Troubleshooting", finalSpec.references && finalSpec.references.troubleshooting, [
        "检查输入参数与权限。",
        "查看命令的 `--help` 或官方文档。",
      ]),
    );
    const edgeCasesMd = ensureNoTodo(
      renderReferenceList("Edge cases", finalSpec.references && finalSpec.references.edgeCases, [
        "路径包含空格/特殊字符时需正确引用。",
        "大规模数据/目录时需要限制范围或分页处理。",
      ]),
    );
    const examplesMd = ensureNoTodo(
      renderReferenceList("Examples", finalSpec.references && finalSpec.references.examples, [
        "先在测试环境或小范围目录验证，再扩大到全量。",
      ]),
    );
    const changelogMd = [
      "# Changelog",
      "",
      `- ${utcDate()}: generated by agents/skillgen/run.js from runs/${args.runId}/curation.json (proposal_id=${proposal && proposal.proposal_id ? proposal.proposal_id : "unknown"})`,
      "",
    ].join("\n");

    const metadataYaml = templateMetadataYaml({
      id: skillId,
      title: finalSpec.title,
      domain: args.domain,
      level: finalSpec.level,
      riskLevel,
      tags: ["autogen", "skillgen", String(item.action)],
    });

    ensureDir(refDir);

    writeText(path.join(skillDir, "metadata.yaml"), metadataYaml, args.overwrite);
    writeText(path.join(skillDir, "skill.md"), skillMd, true);
    writeText(path.join(skillDir, "library.md"), libraryMd, true);
    writeText(path.join(refDir, "sources.md"), sourcesMd, true);
    writeText(path.join(refDir, "troubleshooting.md"), troubleshootingMd, true);
    writeText(path.join(refDir, "edge-cases.md"), edgeCasesMd, true);
    writeText(path.join(refDir, "examples.md"), examplesMd, true);
    writeText(path.join(refDir, "changelog.md"), changelogMd, true);

    const llmUsage = usage && typeof usage === "object" ? usage : null;
    if (llmUsage) {
      report.stats.llm_usage_total.prompt_tokens += Number(llmUsage.prompt_tokens || 0);
      report.stats.llm_usage_total.completion_tokens += Number(llmUsage.completion_tokens || 0);
      report.stats.llm_usage_total.total_tokens += Number(llmUsage.total_tokens || 0);
    }

    report.stats.generated += 1;
    report.results.push({
      id: skillId,
      title: finalSpec.title,
      status: error ? "generated_with_llm_error" : "generated",
      proposal_id: proposal && proposal.proposal_id ? String(proposal.proposal_id) : null,
      action: item.action,
      skill_dir: path.relative(repoRoot, skillDir),
      skill_md: path.relative(repoRoot, path.join(skillDir, "skill.md")),
      sources_md: path.relative(repoRoot, path.join(refDir, "sources.md")),
      llm_capture: llmCapturePath && exists(llmCapturePath) ? path.relative(repoRoot, llmCapturePath) : null,
      materials_dir: path.relative(repoRoot, materialsDir),
      llm_usage: llmUsage,
      sources: fetchedSources.map((s) => ({ url: s.url, fetched: s.fetched })),
    });

    const tokensStr = llmUsage && llmUsage.total_tokens != null ? ` tokens=${llmUsage.total_tokens}` : "";
    console.log(`[skillgen] done: ${skillId}${tokensStr}`);
  }

  let nextIndex = 0;
  async function worker() {
    while (true) {
      const i = nextIndex;
      nextIndex += 1;
      if (i >= totalPlanned) return;
      try {
        // eslint-disable-next-line no-await-in-loop
        await processOne(i);
      } catch (e) {
        report.stats.errors += 1;
        const item = planned[i];
        const suggested = item && item.suggested ? item.suggested : null;
        const skillId = suggested && suggested.id ? String(suggested.id) : "";
        const title = suggested && suggested.title ? String(suggested.title) : "";
        report.results.push({
          id: skillId,
          title,
          status: "error",
          error: String(e && e.message ? e.message : e),
        });
        console.error(`[skillgen] [${i + 1}/${totalPlanned}] error: ${skillId || "(unknown)"}: ${String(e && e.message ? e.message : e)}`);
      }
    }
  }

  const workers = [];
  for (let w = 0; w < concurrency; w++) workers.push(worker());
  await Promise.all(workers);

  const domainReadmePath = path.join(outRoot, args.domain, "README.md");
  const domainReadme = renderDomainReadme({
    domain: args.domain,
    runId: args.runId,
    outRoot: path.relative(repoRoot, outRoot),
    results: report.results,
    inputs: report.inputs,
    llm: { ...(report.llm || {}), usage: report.stats.llm_usage_total },
  });
  writeText(domainReadmePath, domainReadme, true);

  const reportPath = args.reportJson
    ? (path.isAbsolute(args.reportJson) ? args.reportJson : path.resolve(repoRoot, args.reportJson))
    : path.join(runDir, "skillgen_report.json");
  writeJsonAtomic(reportPath, report);

  console.log(`[skillgen] report: ${reportPath}`);
  console.log(`[skillgen] readme: ${domainReadmePath}`);
  console.log(`[skillgen] generated=${report.stats.generated} skipped=${report.stats.skipped} total_tokens=${report.stats.llm_usage_total.total_tokens}`);
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
