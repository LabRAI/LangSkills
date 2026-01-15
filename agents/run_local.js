#!/usr/bin/env node
/* eslint-disable no-console */

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const { captureLinuxSkill } = require("./generator/linux_capture");
const { createLLM, rewriteMarkdown } = require("./llm");

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

function readText(filePath) {
  return fs.readFileSync(filePath, "utf8");
}

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function ensureNewline(text) {
  const t = text == null ? "" : String(text);
  return t.endsWith("\n") ? t : `${t}\n`;
}

function writeText(filePath, content, overwrite) {
  if (!overwrite && exists(filePath)) return { written: false };
  ensureDir(path.dirname(filePath));
  fs.writeFileSync(filePath, ensureNewline(content), "utf8");
  return { written: true };
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

function parseDomainConfigYaml(yamlText) {
  const text = stripBom(String(yamlText || "")).replace(/\r\n/g, "\n");
  const lines = text.split("\n");

  let domain = null;
  const topics = [];
  const sourcePolicy = { allow_domains: [], deny_domains: [] };

  let inTopics = false;
  let inSourcePolicy = false;
  let collectAllow = false;
  let collectDeny = false;
  let current = null;

  for (const rawLine of lines) {
    const line = rawLine.replace(/\s+$/, "");
    if (!line.trim()) continue;
    if (/^\s*#/.test(line)) continue;

    if (!inTopics) {
      if (/^source_policy:\s*$/.test(line)) {
        inSourcePolicy = true;
        collectAllow = false;
        collectDeny = false;
        continue;
      }
      if (/^topics:\s*$/.test(line)) {
        inTopics = true;
        inSourcePolicy = false;
        current = null;
        continue;
      }
    }

    const domainMatch = line.match(/^domain:\s*(.+?)\s*$/);
    if (domainMatch && !inTopics) {
      domain = unquoteScalar(domainMatch[1]);
      continue;
    }

    if (inSourcePolicy && !inTopics) {
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

  return { domain, topics, source_policy: sourcePolicy };
}

function escapeYamlDoubleQuoted(text) {
  return String(text || "").replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

function utcDate() {
  return new Date().toISOString().slice(0, 10);
}

function templateSkillMd(title, riskLevel) {
  return `# ${title}

## Goal
- TODO

## When to use
- TODO

## When NOT to use
- TODO

## Prerequisites
- Environment:
- Permissions:
- Tools:
- Inputs needed:

## Steps (<= 12)
1. TODO

## Verification
- TODO

## Safety & Risk
- Risk level: **${riskLevel}**
- Irreversible actions:
- Privacy/credential handling:
- Confirmation requirement:

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] TODO
- [2] TODO
- [3] TODO
`;
}

function templateLibraryMd() {
  return `# Library

## Copy-paste commands

\`\`\`bash
# TODO
\`\`\`

## Prompt snippet

\`\`\`text
TODO
\`\`\`
`;
}

function templateMetadataYaml(domain, topic, slug, title, level, riskLevel) {
  const escapedTitle = escapeYamlDoubleQuoted(title);
  const platforms = domain === "linux" ? "[linux]" : "[]";
  return `id: ${domain}/${topic}/${slug}
title: "${escapedTitle}"
domain: ${domain}
level: ${level || "bronze"}
risk_level: ${riskLevel || "low"}
platforms: ${platforms}
tools: []
tags: []
last_verified: ""
owners: []
aliases: []
`;
}

function templateReferenceSourcesMd() {
  return `# Sources

> 每条来源需包含：URL、摘要、访问日期，以及它支撑了哪一步。

## [1]
- URL: TODO
- Accessed: YYYY-MM-DD
- Summary: TODO
- Supports: TODO
- License: TODO

## [2]
- URL: TODO
- Accessed: YYYY-MM-DD
- Summary: TODO
- Supports: TODO
- License: TODO

## [3]
- URL: TODO
- Accessed: YYYY-MM-DD
- Summary: TODO
- Supports: TODO
- License: TODO
`;
}

function templateReferenceTroubleshootingMd() {
  return `# Troubleshooting

TODO: 记录常见失败现象、原因、修复方式与验证方法。
`;
}

function templateReferenceEdgeCasesMd() {
  return `# Edge cases

TODO: 记录版本差异、边界条件与容易踩坑的组合。
`;
}

function templateReferenceExamplesMd() {
  return `# Examples

TODO: 放更长的可复制示例（避免塞进 skill.md）。
`;
}

function templateReferenceChangelogMd() {
  return `# Changelog

- YYYY-MM-DD: init skeleton
`;
}

function cachePathForUrl(cacheDir, url) {
  const hash = crypto.createHash("sha256").update(String(url)).digest("hex").slice(0, 16);
  return path.join(cacheDir, `${hash}.txt`);
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
      headers: { "User-Agent": "skill-agent" },
      signal: controller.signal,
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status} for ${url}`);
    return await resp.text();
  } finally {
    clearTimeout(t);
  }
}

async function fetchWithCache(url, cacheDir, timeoutMs, log) {
  ensureDir(cacheDir);
  const cachePath = cachePathForUrl(cacheDir, url);
  if (exists(cachePath)) {
    const text = readText(cachePath);
    if (log) console.log(`Fetched (cache): ${url} (${text.length} chars)`);
    return { text, fromCache: true, cachePath };
  }
  const text = await fetchText(url, timeoutMs);
  fs.writeFileSync(cachePath, text, "utf8");
  if (log) console.log(`Fetched (net):   ${url} (${text.length} chars)`);
  return { text, fromCache: false, cachePath };
}

async function captureLinuxFindFiles({ title, riskLevel }) {
  const sources = [
    { id: 1, label: "man7 find(1)", url: "https://man7.org/linux/man-pages/man1/find.1.html" },
    { id: 2, label: "GNU findutils manual (find)", url: "https://www.gnu.org/software/findutils/manual/html_mono/find.html" },
    { id: 3, label: "POSIX find specification", url: "https://pubs.opengroup.org/onlinepubs/9699919799/utilities/find.html" },
  ];

  const accessed = utcDate();
  for (const s of sources) {
    await fetchWithCache(s.url, captureLinuxFindFiles.cacheDir, captureLinuxFindFiles.timeoutMs, true);
  }

  const skillMd = `# ${title}

## Goal
- 用 \`find\` 在指定目录树中按条件查找文件/目录，并安全地输出/统计/进一步处理结果。

## When to use
- 需要按名称、类型、时间、大小等条件筛选文件/目录
- 需要把“匹配到的路径列表”交给后续命令处理（统计/归档/清理等）

## When NOT to use
- 只需要在已知的少量目录里手动定位（\`ls\`/\`tree\` 更快）
- 你不确定匹配条件是否会命中大量文件且后续操作不可逆（先用 dry-run 预览）

## Prerequisites
- Environment: Linux shell
- Permissions: 读取目标目录（某些目录可能需要 sudo）
- Tools: \`find\`
- Inputs needed: 起始目录（root）、匹配条件（例如 name/type/mtime/size）

## Steps (<= 12)
1. 先用最小条件做 dry-run：\`find <root> -type f -name '<pattern>' -print\`（只打印，不做修改）[[1]]
2. 用 \`-iname\` 做不区分大小写匹配：\`find . -type f -iname '*.log'\`[[1]]
3. 用 \`-type\` 限定对象：\`f\` 文件、\`d\` 目录、\`l\` 符号链接（例如：\`find . -type d -name 'node_modules'\`）[[1]]
4. 用时间条件筛选：\`-mtime -7\`（最近 7 天修改过）、\`-mmin -30\`（最近 30 分钟）[[1]]
5. 用大小筛选：\`-size +100M\`（大于 100MB）或 \`-size -10k\`（小于 10KB）[[1]]
6. 限制搜索深度：\`-maxdepth N\` / \`-mindepth N\`（避免扫太深）[[1]]
7. 组合条件：默认是 AND；需要 OR 时用括号：\`find . \\( -name '*.jpg' -o -name '*.png' \\) -type f\`[[1]]
8. 需要对结果执行命令时优先用 \`-exec ... {} +\`（相比 \`-exec ... {} \\;\` 更少起进程）：\`find . -type f -name '*.tmp' -exec rm -i {} +\`（高风险：先确认）[[1][3]]

## Verification
- 确认命中数量：\`find <root> ... -print | wc -l\`
- 抽样检查：把 \`-print\` 输出重定向到文件后人工审阅（尤其在删除/改权限前）

## Safety & Risk
- Risk level: **${riskLevel}**
- Irreversible actions: \`-delete\` / \`rm\` / \`-exec\` 可能不可逆
- Privacy/credential handling: 避免把敏感路径/文件名复制到公开渠道（日志/截图）
- Confirmation requirement: 任何写操作先 \`-print\` 预览，再执行；必要时加 \`-maxdepth\`/更严格条件

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] ${sources[0].label}: ${sources[0].url}
- [2] ${sources[1].label}: ${sources[1].url}
- [3] ${sources[2].label}: ${sources[2].url}
`;

  const libraryMd = `# Library

## Copy-paste commands

\`\`\`bash
# 1) Find files by name (dry-run print only)
find . -type f -name '*.log' -print

# 2) Find directories by name
find . -type d -name 'node_modules' -print

# 3) Find files modified in last 7 days
find /var/log -type f -mtime -7 -print

# 4) Find big files (>100MB) (may produce permission errors)
find / -type f -size +100M -print 2>/dev/null
\`\`\`

## Prompt snippet

\`\`\`text
You are a Linux assistant. Write a safe, minimal find(1) command.
Inputs: root directory, filter conditions (name/type/time/size), and whether the output is for read-only listing or a write operation.
Rules:
- Always provide a dry-run print-only command first.
- Steps <= 12, include a verification step.
\`\`\`
`;

  const sourcesMd = `# Sources

> 每条来源需包含：URL、摘要、访问日期，以及它支撑了哪一步。

## [1]
- URL: ${sources[0].url}
- Accessed: ${accessed}
- Summary: find(1) man page，覆盖常用选项（-name/-type/-mtime/-size/-maxdepth/-exec 等）。
- Supports: Steps 1-8 (命令语义与选项用法)

## [2]
- URL: ${sources[1].url}
- Accessed: ${accessed}
- Summary: GNU findutils 的官方手册，对 find 的语法/表达式组合/执行动作有更完整说明。
- Supports: Steps 7-8 (表达式组合、-exec 行为)

## [3]
- URL: ${sources[2].url}
- Accessed: ${accessed}
- Summary: POSIX find 规范，提供可移植语义参考（跨发行版/实现差异时对齐）。
- Supports: Steps 1-5 (基础语义与可移植用法)
`;

  const troubleshootingMd = `# Troubleshooting

## Permission denied
- 现象：输出包含大量 \`Permission denied\`
- 处理：把错误输出重定向：\`2>/dev/null\`；或缩小 root；或在必要时使用 \`sudo\`（谨慎）

## Too many results / slow
- 加 \`-maxdepth\` 限制深度
- 先用更严格的 \`-name/-type\` 再加其他条件

## Filenames with spaces/newlines
- 避免用简单的管道+空格分割；优先用 \`-exec ... {} +\` 或使用 \`-print0\` 搭配 \`xargs -0\`
`;

  const edgeCasesMd = `# Edge cases

- 不同 find 实现（GNU find vs busybox find）可能在部分选项上有差异；以 \`find --help\` / man page 为准。
- \`-exec ... {} +\` 与 \`-exec ... {} \\;\` 行为不同（批量 vs 单个），注意命令是否支持批量参数。
`;

  const examplesMd = `# Examples

\`\`\`bash
# Find files newer than a reference file
find . -type f -newer ./reference.txt -print

# Find and list sizes (warning: may be slow on /)
find / -type f -size +100M -exec ls -lh {} + 2>/dev/null
\`\`\`
`;

  const changelogMd = `# Changelog

- ${accessed}: generated by agents/run_local.js --capture (find-files)
`;

  return { skillMd, libraryMd, sourcesMd, troubleshootingMd, edgeCasesMd, examplesMd, changelogMd };
}

function templateDomainReadme(domain, topics) {
  const lines = [];
  lines.push(`# ${domain} Skills`);
  lines.push("");
  lines.push(`本目录包含 ${domain} domain 的 skills。`);
  lines.push("");
  lines.push("## 目录约定");
  lines.push("");
  lines.push(`- 路径：\`skills/${domain}/<topic>/<slug>/\``);
  lines.push("- 每个 skill：`skill.md` + `library.md` + `metadata.yaml` + `reference/`");
  lines.push("");
  lines.push("## Topics");
  lines.push("");
  lines.push("| # | ID | Path | Risk | Level |");
  lines.push("|---:|---|---|---:|---:|");

  let index = 1;
  for (const t of topics) {
    const id = String(t.id || "").trim();
    const [topic, slug] = id.split("/");
    const p = `skills/${domain}/${topic}/${slug}/`;
    lines.push(`| ${index} | \`${domain}/${id}\` | \`${p}\` | **${t.risk_level || "low"}** | ${t.level || "bronze"} |`);
    index++;
  }

  lines.push("");
  return lines.join("\n");
}

function usage(exitCode = 0) {
  const msg = `
Usage:
  node agents/run_local.js --domain <domain> [--topic <topic/id>] [--out <skillsRoot>] [--overwrite] [--dry-run] [--capture]
    [--llm-provider mock|ollama|openai] [--llm-model <model>] [--llm-base-url <url>] [--llm-api-key <key>]
    [--llm-fixture <path>] [--llm-timeout-ms <n>] [--llm-strict]

Examples:
  node agents/run_local.js --domain linux --out skills
  node agents/run_local.js --domain linux --topic filesystem/find-files --out skills --overwrite
  node agents/run_local.js --domain linux --topic filesystem/find-files --out skills --overwrite --capture
  node agents/run_local.js --domain linux --topic filesystem/find-files --out /tmp/skill-llm-out --overwrite --capture --llm-provider mock --llm-fixture agents/llm/fixtures/rewrite.json
  node agents/run_local.js --domain linux --topic filesystem/find-files --out /tmp/skill-llm-out --overwrite --capture --llm-provider ollama --llm-model qwen2.5:7b
  node agents/run_local.js --domain linux --out C:\\temp\\skills --dry-run

Notes:
  - Reads config from: agents/configs/<domain>.yaml
  - Generates: skills/<domain>/<topic>/<slug>/* (skeleton templates)
  - With --capture: tries to fetch sources and write non-TODO content for supported topics
  - With --llm-provider: rewrites captured markdown (skill/library) for quality (keeps citations/commands)
`;
  if (exitCode === 0) console.log(msg.trim());
  else console.error(msg.trim());
  process.exit(exitCode);
}

function parseArgs(argv) {
  const args = {
    domain: null,
    topic: null,
    out: "skills",
    overwrite: false,
    dryRun: false,
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
  };

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--domain") {
      args.domain = argv[i + 1] || null;
      i++;
    } else if (a === "--topic") {
      args.topic = argv[i + 1] || null;
      i++;
    } else if (a === "--out") {
      args.out = argv[i + 1] || "skills";
      i++;
    } else if (a === "--overwrite") args.overwrite = true;
    else if (a === "--dry-run") args.dryRun = true;
    else if (a === "--capture") args.capture = true;
    else if (a === "--capture-strict") args.captureStrict = true;
    else if (a === "--cache-dir") {
      args.cacheDir = argv[i + 1] || ".cache/web";
      i++;
    } else if (a === "--timeout-ms") {
      args.timeoutMs = Number(argv[i + 1] || "20000");
      i++;
    }
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
    else if (a === "-h" || a === "--help") usage(0);
    else throw new Error(`Unknown arg: ${a}`);
  }

  if (!args.domain) usage(2);
  return args;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const repoRoot = path.resolve(__dirname, "..");
  const configPath = path.join(repoRoot, "agents", "configs", `${args.domain}.yaml`);
  if (!exists(configPath)) throw new Error(`Missing config: ${configPath}`);

  const cfg = parseDomainConfigYaml(readText(configPath));
  if (cfg.domain !== args.domain) {
    throw new Error(`Config domain mismatch: expected ${args.domain} but got ${cfg.domain}`);
  }

  const allTopics = cfg.topics;
  let topicsToGenerate = allTopics;
  if (args.topic) {
    const raw = String(args.topic).trim();
    const normalized = raw.split("/").length === 3 ? raw.split("/").slice(1).join("/") : raw;
    topicsToGenerate = topicsToGenerate.filter((t) => t.id === normalized);
    if (topicsToGenerate.length === 0) throw new Error(`Topic not found in config: ${args.topic}`);
  }

  const outRoot = path.isAbsolute(args.out) ? args.out : path.resolve(repoRoot, args.out);
  const domainRoot = path.join(outRoot, cfg.domain);

  const llm = args.llmProvider
    ? createLLM({
      provider: args.llmProvider,
      model: args.llmModel,
      baseUrl: args.llmBaseUrl,
      apiKey: args.llmApiKey,
      fixturePath: args.llmFixture ? path.resolve(repoRoot, args.llmFixture) : null,
      timeoutMs: Number.isFinite(args.llmTimeoutMs) ? args.llmTimeoutMs : 60000,
    })
    : null;

  let created = 0;
  let updated = 0;
  let skipped = 0;

  // domain README
  {
    const readmePath = path.join(domainRoot, "README.md");
    const content = templateDomainReadme(cfg.domain, allTopics);
    const before = exists(readmePath);
    if (args.dryRun) {
      console.log(`[dry-run] write ${path.relative(repoRoot, readmePath)}`);
    } else {
      const r = writeText(readmePath, content, args.overwrite);
      if (r.written) {
        if (before) updated++;
        else created++;
      } else {
        skipped++;
      }
    }
  }

  for (const t of topicsToGenerate) {
    const id = String(t.id || "").trim();
    const parts = id.split("/");
    if (parts.length !== 2) throw new Error(`Invalid topic id (expected topic/slug): ${id}`);
    const [topic, slug] = parts;

    const title = String(t.title || `${cfg.domain}/${topic}/${slug}`).trim();
    const riskLevel = String(t.risk_level || "low").trim();
    const level = String(t.level || "bronze").trim();

    const skillDir = path.join(domainRoot, topic, slug);
    const refDir = path.join(skillDir, "reference");

    let payload = null;
    if (args.capture && cfg.domain === "linux") {
      try {
        payload = await captureLinuxSkill({
          topic,
          slug,
          title,
          riskLevel,
          cacheDir: path.resolve(repoRoot, args.cacheDir),
          timeoutMs: Number.isFinite(args.timeoutMs) ? args.timeoutMs : 20000,
          log: true,
          strict: args.captureStrict,
          sourcePolicy: cfg.source_policy || null,
        });
      } catch (e) {
        if (args.captureStrict) throw e;
        console.error(`[capture] failed for linux/${topic}/${slug}: ${String(e && e.message ? e.message : e)}`);
        payload = null;
      }
    }

    if (payload && llm) {
      try {
        payload.skillMd = await rewriteMarkdown({ markdown: payload.skillMd, llm, kind: "skill.md" });
        payload.libraryMd = await rewriteMarkdown({ markdown: payload.libraryMd, llm, kind: "library.md" });
      } catch (e) {
        if (args.llmStrict) throw e;
        console.error(`[llm] rewrite failed for ${cfg.domain}/${topic}/${slug}: ${String(e && e.message ? e.message : e)}`);
      }
    }

    const writes = [
      { p: path.join(skillDir, "skill.md"), c: payload ? payload.skillMd : templateSkillMd(title, riskLevel) },
      { p: path.join(skillDir, "library.md"), c: payload ? payload.libraryMd : templateLibraryMd() },
      { p: path.join(skillDir, "metadata.yaml"), c: templateMetadataYaml(cfg.domain, topic, slug, title, level, riskLevel) },
      { p: path.join(refDir, "sources.md"), c: payload ? payload.sourcesMd : templateReferenceSourcesMd() },
      { p: path.join(refDir, "troubleshooting.md"), c: payload ? payload.troubleshootingMd : templateReferenceTroubleshootingMd() },
      { p: path.join(refDir, "edge-cases.md"), c: payload ? payload.edgeCasesMd : templateReferenceEdgeCasesMd() },
      { p: path.join(refDir, "examples.md"), c: payload ? payload.examplesMd : templateReferenceExamplesMd() },
      { p: path.join(refDir, "changelog.md"), c: payload ? payload.changelogMd : templateReferenceChangelogMd() },
    ];

    for (const w of writes) {
      const rel = path.relative(repoRoot, w.p);
      if (args.dryRun) {
        console.log(`[dry-run] write ${rel}`);
        continue;
      }
      const before = exists(w.p);
      const r = writeText(w.p, w.c, args.overwrite);
      if (!r.written) skipped++;
      else if (before) updated++;
      else created++;
    }
  }

  console.log(
    `Done. domain=${cfg.domain} topics=${topicsToGenerate.length} out=${outRoot} created=${created} updated=${updated} skipped=${skipped} overwrite=${args.overwrite} dry_run=${args.dryRun}`,
  );
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
