/* eslint-disable no-console */

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

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

function utcDate() {
  return new Date().toISOString().slice(0, 10);
}

function sha256Hex(text) {
  return crypto.createHash("sha256").update(String(text || ""), "utf8").digest("hex");
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
    return { text, fromCache: true };
  }
  const text = await fetchText(url, timeoutMs);
  fs.writeFileSync(cachePath, text, "utf8");
  if (log) console.log(`Fetched (net):   ${url} (${text.length} chars)`);
  return { text, fromCache: false };
}

function formatCites(cites) {
  if (!Array.isArray(cites) || cites.length === 0) return "";
  const parts = cites.map((c) => String(c)).join("][");
  return `[[${parts}]]`;
}

function ensureTrailingNewline(text) {
  const t = String(text || "");
  return t.endsWith("\n") ? t : `${t}\n`;
}

function joinLines(lines) {
  return ensureTrailingNewline((Array.isArray(lines) ? lines : []).join("\n"));
}

function renderBullets(items) {
  const out = [];
  for (const item of Array.isArray(items) ? items : []) out.push(`- ${item}`);
  if (out.length === 0) out.push("- TODO");
  return out;
}

function renderPrerequisites(prerequisites) {
  const p = prerequisites || {};
  return [
    `- Environment: ${p.environment || ""}`.trimEnd(),
    `- Permissions: ${p.permissions || ""}`.trimEnd(),
    `- Tools: ${p.tools || ""}`.trimEnd(),
    `- Inputs needed: ${p.inputs || ""}`.trimEnd(),
  ];
}

function renderSteps(steps) {
  const out = [];
  const list = Array.isArray(steps) ? steps : [];
  if (list.length === 0) return ["1. TODO"];
  for (let i = 0; i < list.length; i++) {
    const step = list[i];
    const text = String(step && step.text ? step.text : "").trim();
    out.push(`${i + 1}. ${text || "TODO"}${formatCites(step && step.cites ? step.cites : [])}`);
  }
  return out;
}

async function fetchSourcesWithEvidence(sources, cacheDir, timeoutMs, log) {
  const fetched = [];
  for (const s of Array.isArray(sources) ? sources : []) {
    const r = await fetchWithCache(s.url, cacheDir, timeoutMs, log);
    fetched.push({
      ...s,
      fetched: {
        cache: r.fromCache ? "hit" : "miss",
        bytes: Buffer.byteLength(r.text, "utf8"),
        sha256: sha256Hex(r.text),
      },
    });
  }
  return fetched;
}

function renderSkillMd({ title, riskLevel, spec, sources }) {
  const src = Array.isArray(sources) ? sources : [];
  const safety = spec.safety || {};

  const lines = [];
  lines.push(`# ${title}`);
  lines.push("");
  lines.push("## Goal");
  lines.push(...renderBullets(spec.goal));
  lines.push("");
  lines.push("## When to use");
  lines.push(...renderBullets(spec.whenUse));
  lines.push("");
  lines.push("## When NOT to use");
  lines.push(...renderBullets(spec.whenNot));
  lines.push("");
  lines.push("## Prerequisites");
  lines.push(...renderPrerequisites(spec.prerequisites));
  lines.push("");
  lines.push("## Steps (<= 12)");
  lines.push(...renderSteps(spec.steps));
  lines.push("");
  lines.push("## Verification");
  lines.push(...renderBullets(spec.verification));
  lines.push("");
  lines.push("## Safety & Risk");
  lines.push(`- Risk level: **${riskLevel}**`);
  lines.push(`- Irreversible actions: ${safety.irreversible || ""}`.trimEnd());
  lines.push(`- Privacy/credential handling: ${safety.privacy || ""}`.trimEnd());
  lines.push(`- Confirmation requirement: ${safety.confirmation || ""}`.trimEnd());
  lines.push("");
  lines.push("## Troubleshooting");
  lines.push("- See: reference/troubleshooting.md");
  lines.push("");
  lines.push("## Sources");
  for (let i = 0; i < src.length; i++) {
    const s = src[i];
    lines.push(`- [${i + 1}] ${s.label}: ${s.url}`);
  }
  lines.push("");
  return joinLines(lines);
}

function renderLibraryMd(spec) {
  const bashLines = Array.isArray(spec.library && spec.library.bash) ? spec.library.bash : ["# TODO"];
  const promptLines = Array.isArray(spec.library && spec.library.prompt) ? spec.library.prompt : ["TODO"];

  const lines = [];
  lines.push("# Library");
  lines.push("");
  lines.push("## Copy-paste commands");
  lines.push("");
  lines.push("```bash");
  lines.push(...bashLines);
  lines.push("```");
  lines.push("");
  lines.push("## Prompt snippet");
  lines.push("");
  lines.push("```text");
  lines.push(...promptLines);
  lines.push("```");
  lines.push("");
  return joinLines(lines);
}

function renderReferenceSourcesMd(sources, accessed) {
  const src = Array.isArray(sources) ? sources : [];
  const lines = [];
  lines.push("# Sources");
  lines.push("");
  lines.push("> 每条来源需包含：URL、摘要、访问日期，以及它支撑了哪一步。");
  lines.push("> 生成器会在本地缓存抓取结果（`.cache/`，默认不提交），这里记录抓取指纹与 license 审计字段用于审计。");
  lines.push("");
  for (let i = 0; i < src.length; i++) {
    const s = src[i];
    lines.push(`## [${i + 1}]`);
    lines.push(`- URL: ${s.url}`);
    lines.push(`- Accessed: ${accessed}`);
    lines.push(`- Summary: ${s.summary || ""}`.trimEnd());
    lines.push(`- Supports: ${s.supports || ""}`.trimEnd());
    lines.push(`- License: ${s.license || "unknown"}`.trimEnd());
    lines.push(`- Fetch cache: ${s.fetched.cache}`);
    lines.push(`- Fetch bytes: ${s.fetched.bytes}`);
    lines.push(`- Fetch sha256: ${s.fetched.sha256}`);
    lines.push("");
  }
  return joinLines(lines);
}

function renderReferenceTroubleshootingMd(spec) {
  const body = Array.isArray(spec.references && spec.references.troubleshooting) ? spec.references.troubleshooting : ["TODO"];
  return joinLines(["# Troubleshooting", "", ...body, ""]);
}

function renderReferenceEdgeCasesMd(spec) {
  const body = Array.isArray(spec.references && spec.references.edgeCases) ? spec.references.edgeCases : ["TODO"];
  return joinLines(["# Edge cases", "", ...body, ""]);
}

function renderReferenceExamplesMd(spec) {
  const body = Array.isArray(spec.references && spec.references.examples) ? spec.references.examples : ["TODO"];
  return joinLines(["# Examples", "", ...body, ""]);
}

function renderReferenceChangelogMd(accessed, key) {
  return joinLines(["# Changelog", "", `- ${accessed}: generated by agents/run_local.js --capture (${key})`, ""]);
}

const LINUX_CAPTURE_SPECS = {
  "filesystem/find-files": {
    sources: [
      {
        label: "man7 find(1)",
        url: "https://man7.org/linux/man-pages/man1/find.1.html",
        summary: "find(1) 选项与表达式（-name/-type/-mtime/-size/-maxdepth/-exec 等）。",
        supports: "Steps 1-8",
      },
      {
        label: "GNU findutils manual (find)",
        url: "https://www.gnu.org/software/findutils/manual/html_mono/find.html",
        summary: "GNU findutils 官方手册（表达式组合、-exec 行为、可移植性注意点）。",
        supports: "Steps 7-8",
      },
      {
        label: "POSIX find specification",
        url: "https://pubs.opengroup.org/onlinepubs/9699919799/utilities/find.html",
        summary: "POSIX find 规范（可移植语义参考）。",
        supports: "Steps 1-6",
      },
    ],
    goal: ["用 `find` 在目录树中按条件查找文件/目录，并安全地输出/统计/进一步处理结果。"],
    whenUse: [
      "需要按名称、类型、时间、大小等条件筛选文件/目录",
      "需要把“匹配到的路径列表”交给后续命令处理（统计/归档/清理等）",
    ],
    whenNot: [
      "只需要在已知的少量目录里手动定位（`ls`/`tree` 更快）",
      "你不确定匹配条件会命中多少文件且后续操作不可逆（先 dry-run 预览）",
    ],
    prerequisites: {
      environment: "Linux shell",
      permissions: "读取目标目录（某些目录可能需要 sudo）",
      tools: "`find`",
      inputs: "起始目录（root）、匹配条件（name/type/mtime/size）、是否只读或写操作",
    },
    steps: [
      { text: "先做 dry-run：`find <root> -type f -name '<pattern>' -print`（只打印不修改）", cites: [1] },
      { text: "不区分大小写：`find . -type f -iname '*.log' -print`", cites: [1] },
      { text: "限定对象类型：`-type f|d|l`（例如：`find . -type d -name 'node_modules' -print`）", cites: [1] },
      { text: "按时间筛选：`-mtime -7` / `-mmin -30`（先 print）", cites: [1] },
      { text: "按大小筛选：`-size +100M` / `-size -10k`（先 print）", cites: [1] },
      { text: "限制深度：`-maxdepth N` / `-mindepth N`（避免扫太深）", cites: [1] },
      { text: "组合条件：`find . \\( -name '*.jpg' -o -name '*.png' \\) -type f -print`", cites: [1, 2] },
      { text: "写操作优先 `-exec ... {} +`，并要求交互确认：`find . -name '*.tmp' -type f -exec rm -i {} +`", cites: [1, 2, 3] },
    ],
    verification: [
      "确认命中数量：`find <root> ... -print | wc -l`",
      "抽样检查：把 `-print` 输出重定向到文件后人工审阅（尤其在删除/改权限前）",
    ],
    safety: {
      irreversible: "`-delete` / `rm` / `-exec` 可能不可逆",
      privacy: "避免把敏感路径/文件名复制到公开渠道（日志/截图）",
      confirmation: "任何写操作先 `-print` 预览，再执行；必要时加 `-maxdepth`/更严格条件",
    },
    library: {
      bash: [
        "# 1) Find files by name (dry-run print only)",
        "find . -type f -name '*.log' -print",
        "",
        "# 2) Find directories by name",
        "find . -type d -name 'node_modules' -print",
        "",
        "# 3) Find files modified in last 7 days",
        "find /var/log -type f -mtime -7 -print",
        "",
        "# 4) Find big files (>100MB) (may produce permission errors)",
        "find / -type f -size +100M -print 2>/dev/null",
      ],
      prompt: [
        "You are a Linux assistant. Write a safe, minimal find(1) command.",
        "Inputs: root directory, filter conditions (name/type/time/size), and whether the output is for read-only listing or a write operation.",
        "Rules:",
        "- Always provide a dry-run print-only command first.",
        "- Steps <= 12, include a verification step.",
      ],
    },
    references: {
      troubleshooting: [
        "## Permission denied",
        "- 现象：输出包含大量 `Permission denied`",
        "- 处理：把错误输出重定向：`2>/dev/null`；或缩小 root；必要时使用 `sudo`（谨慎）",
      ],
      edgeCases: [
        "- 不同 find 实现（GNU find vs busybox find）可能在部分选项上有差异；以 `find --help` / man page 为准。",
        "- `-exec ... {} +` 与 `-exec ... {} \\;` 行为不同（批量 vs 单个）。",
      ],
      examples: [
        "```bash",
        "find . -type f -newer ./reference.txt -print",
        "```",
      ],
    },
  },

  "filesystem/locate-which-whereis": {
    sources: [
      {
        label: "POSIX command (command -v)",
        url: "https://pubs.opengroup.org/onlinepubs/9699919799/utilities/command.html",
        summary: "POSIX `command`（包含 `command -v` 用于查询命令解析结果）。",
        supports: "Steps 1,5",
      },
      {
        label: "GNU Bash manual",
        url: "https://www.gnu.org/software/bash/manual/bash.html",
        summary: "Bash 手册（type、命令解析与相关行为）。",
        supports: "Step 2",
      },
      {
        label: "Arch man: which(1)",
        url: "https://man.archlinux.org/man/which.1.en.txt",
        summary: "which(1) 查询 PATH 中可执行文件。",
        supports: "Step 3",
      },
      {
        label: "Arch man: whereis(1)",
        url: "https://man.archlinux.org/man/whereis.1.en.txt",
        summary: "whereis(1) 定位二进制/源码/manpage。",
        supports: "Step 4",
      },
      {
        label: "Arch man: plocate(1) (provides locate)",
        url: "https://man.archlinux.org/man/plocate.1.en.txt",
        summary: "plocate/locate 基于数据库快速查找文件（现代 locate 实现之一）。",
        supports: "Step 4-5",
      },
    ],
    goal: ["快速定位命令/文件位置，并确认 shell 最终会执行哪个候选。"],
    whenUse: ["同名命令很多，需要确认实际执行路径", "需要快速定位文件/二进制/文档位置"],
    whenNot: ["你已经持有明确的绝对路径且不涉及 shell 解析"],
    prerequisites: {
      environment: "Linux shell (bash/zsh)",
      permissions: "读取 PATH 目录与目标文件；locate 依赖数据库权限",
      tools: "`command`/`type`，可选 `which`/`whereis`/`locate`",
      inputs: "命令名或文件名关键字",
    },
    steps: [
      { text: "优先用可移植方式：`command -v <cmd>`（返回将被执行的路径或空）", cites: [1] },
      { text: "查看所有解析结果（alias/function/builtin/path）：`type -a <cmd>`", cites: [2] },
      { text: "只看 PATH 中可执行文件：`which -a <cmd>`", cites: [3] },
      { text: "定位二进制/源码/manpage：`whereis <cmd>`；按文件名全盘找：`locate <name>`", cites: [4, 5] },
      { text: "验证：对 `command -v` 的路径做 `ls -l` / 运行 `<cmd> --version`（如适用）", cites: [1] },
    ],
    verification: ["`command -v` 返回的路径与预期一致", "`type -a` 中没有意外的 alias/function 遮蔽"],
    safety: {
      irreversible: "无（读操作）",
      privacy: "输出路径可能包含用户名/项目名，分享前脱敏",
      confirmation: "无",
    },
    library: {
      bash: [
        "command -v python",
        "type -a python",
        "which -a python",
        "whereis python",
        "locate bashrc | head",
      ],
      prompt: [
        "Given a Linux command name, show how to locate what will be executed.",
        "Prefer: command -v, then type -a; mention whereis/locate as optional.",
      ],
    },
    references: {
      troubleshooting: [
        "## locate returns stale paths",
        "- locate 基于数据库：可能过时；必要时更新数据库（例如 updatedb，需权限）。",
      ],
      edgeCases: [
        "- alias/function 可能遮蔽同名二进制；用 `type -a` 查明。",
        "- PATH 顺序决定优先级；必要时打印 `$PATH` 排查。",
      ],
      examples: [
        "```bash",
        "type -a git",
        "command -v git",
        "whereis git",
        "```",
      ],
    },
  },

  "filesystem/safe-delete": {
    sources: [
      {
        label: "GNU coreutils manual: rm invocation",
        url: "https://www.gnu.org/software/coreutils/manual/html_node/rm-invocation.html",
        summary: "rm 选项（-i/-I/-r/-- 等）与语义说明。",
        supports: "Steps 2-4",
      },
      {
        label: "POSIX rm specification",
        url: "https://pubs.opengroup.org/onlinepubs/9699919799/utilities/rm.html",
        summary: "POSIX rm 语义（可移植行为参考）。",
        supports: "Steps 2-4",
      },
      {
        label: "Arch man: rm(1)",
        url: "https://man.archlinux.org/man/rm.1.en.txt",
        summary: "rm(1) man page（交互确认与递归删除）。",
        supports: "Steps 2-4",
      },
    ],
    goal: ["安全删除文件/目录：先预览，再确认，再执行（避免误删）。"],
    whenUse: ["清理临时文件/构建产物", "需要批量删除但希望可审阅清单"],
    whenNot: ["不确定匹配范围（先 `find ... -print`）", "涉及生产/关键数据（先备份/走审批）"],
    prerequisites: {
      environment: "Linux shell",
      permissions: "对目标路径有删除权限（可能需要 sudo）",
      tools: "`rm`（可选 `find`）",
      inputs: "目标路径/匹配模式",
    },
    steps: [
      { text: "先 dry-run 列出将删除目标：`ls -la -- <path>` 或 `find ... -print`", cites: [1, 3] },
      { text: "单个/少量目标：用交互确认 `rm -i -- <path>`", cites: [1, 3] },
      { text: "大量目标：用 `rm -I`（一次性确认）而不是无脑 `-f`", cites: [1, 3] },
      { text: "目录删除更谨慎：`rm -rI -- <dir>`；批量用 find 两阶段：先 print，再 `-exec rm -i`", cites: [1, 2, 3] },
    ],
    verification: ["确认目标不存在：`test ! -e <path> && echo ok`", "如果在 git 仓库：`git status` 确认没有误删"],
    safety: {
      irreversible: "删除通常不可逆（尤其绕过回收站时）",
      privacy: "删除清单/路径可能包含敏感信息，分享前脱敏",
      confirmation: "任何批量删除必须先 dry-run 输出清单并人工审阅；避免使用 `rm -rf`",
    },
    library: {
      bash: [
        "find . -type f -name '*.tmp' -print",
        "rm -i -- ./some-file.tmp",
        "rm -rI -- ./build/",
        "find . -type f -name '*.tmp' -exec rm -i {} +",
      ],
      prompt: [
        "Write a safe deletion plan for Linux.",
        "Always provide a dry-run listing first; avoid rm -rf; require confirmation for recursive operations.",
      ],
    },
    references: {
      troubleshooting: [
        "## Permission denied",
        "- 先确认权限/属主：`ls -l`；必要时用 `sudo`（注意删除范围）。",
      ],
      edgeCases: ["- 文件名以 `-` 开头：务必加 `--` 结束选项（例如 `rm -- -weirdname`）。"],
      examples: [
        "```bash",
        "find . -type d -empty -print",
        "find . -type d -empty -exec rmdir {} +",
        "```",
      ],
    },
  },

  "filesystem/symlink-hardlink": {
    sources: [
      {
        label: "GNU coreutils manual: ln invocation",
        url: "https://www.gnu.org/software/coreutils/manual/html_node/ln-invocation.html",
        summary: "ln 的软链接/硬链接语义与常用选项。",
        supports: "Steps 1-3",
      },
      {
        label: "POSIX ln specification",
        url: "https://pubs.opengroup.org/onlinepubs/9699919799/utilities/ln.html",
        summary: "POSIX ln 规范（可移植语义）。",
        supports: "Steps 1-2",
      },
      {
        label: "Arch man: ln(1)",
        url: "https://man.archlinux.org/man/ln.1.en.txt",
        summary: "ln(1) man page。",
        supports: "Steps 1-3",
      },
    ],
    goal: ["创建与验证符号链接/硬链接，并理解它们的差异与限制。"],
    whenUse: ["需要给同一个文件提供多个路径入口（硬链接）", "需要用一个路径指向另一个路径（符号链接）"],
    whenNot: ["你不希望链接随目标移动/删除而失效（符号链接可能变成 broken link）"],
    prerequisites: {
      environment: "Linux shell",
      permissions: "对目标目录有写权限",
      tools: "`ln`（可选 `ls`/`stat`）",
      inputs: "target 路径与 link 名称",
    },
    steps: [
      { text: "创建符号链接：`ln -s <target> <link>`", cites: [1, 3] },
      { text: "创建硬链接：`ln <existing_file> <new_link>`（通常要求同一文件系统）", cites: [1, 2] },
      { text: "验证：`ls -l <link>` / `ls -li <file> <link>`（看 inode 是否相同）", cites: [3] },
    ],
    verification: ["硬链接的 inode 相同；符号链接指向正确目标", "使用链接访问文件无误"],
    safety: {
      irreversible: "覆盖/替换链接可能改变依赖指向",
      privacy: "链接可能暴露目录结构；共享前脱敏",
      confirmation: "覆盖前先 `ls -l` 确认现状与目标",
    },
    library: {
      bash: ["ln -s ./config/prod.yaml ./config/current.yaml", "ln ./data.db ./data.db.link", "ls -li ./data.db ./data.db.link"],
      prompt: ["Explain symlink vs hardlink and give safe commands to create and verify them."],
    },
    references: {
      troubleshooting: ["## Broken symlink", "- target 不存在或路径变化；修复 target 或重建链接。"],
      edgeCases: ["- 硬链接通常不能跨文件系统；对目录的硬链接一般受限。"],
      examples: ["```bash", "ln -s ../shared/config.yaml ./config/config.yaml", "```"],
    },
  },

  "filesystem/permissions-chmod": {
    sources: [
      {
        label: "GNU coreutils manual: chmod invocation",
        url: "https://www.gnu.org/software/coreutils/manual/html_node/chmod-invocation.html",
        summary: "chmod 权限修改语法（符号/数字）与常用选项。",
        supports: "Steps 2-4",
      },
      {
        label: "POSIX chmod specification",
        url: "https://pubs.opengroup.org/onlinepubs/9699919799/utilities/chmod.html",
        summary: "POSIX chmod 规范（可移植语义）。",
        supports: "Steps 2-3",
      },
      {
        label: "Arch man: chmod(1)",
        url: "https://man.archlinux.org/man/chmod.1.en.txt",
        summary: "chmod(1) man page。",
        supports: "Steps 1-4",
      },
    ],
    goal: ["安全地修改文件/目录权限（chmod 符号/数字写法）。"],
    whenUse: ["脚本需要可执行权限", "修复权限过宽/过严导致的访问问题"],
    whenNot: ["你不确定递归修改影响范围（先列清单）"],
    prerequisites: {
      environment: "Linux shell",
      permissions: "对目标是 owner 或具备 sudo",
      tools: "`chmod`（可选 `find`）",
      inputs: "目标路径 + 期望权限（符号或数字）",
    },
    steps: [
      { text: "查看当前权限：`ls -l <path>`", cites: [3] },
      { text: "符号写法：`chmod u+x <script>` / `chmod go-rwx <file>`", cites: [1, 3] },
      { text: "数字写法常见：文件 `644`、目录 `755`（例如：`chmod 644 file`）", cites: [1, 2] },
      { text: "递归更谨慎：优先用 find 区分目录/文件再 chmod（避免目录被设成 644）", cites: [1, 3] },
    ],
    verification: ["重新 `ls -l` 确认权限变化", "实际执行/访问一次确认问题解决"],
    safety: {
      irreversible: "权限过宽会引入安全风险；过严可能导致服务不可用",
      privacy: "无",
      confirmation: "递归操作前先列出目标清单并确认；生产环境需变更记录",
    },
    library: {
      bash: [
        "chmod u+x ./script.sh",
        "chmod 644 ./file.txt",
        "chmod 755 ./dir",
        "find ./dir -type d -exec chmod 755 {} +",
        "find ./dir -type f -exec chmod 644 {} +",
      ],
      prompt: ["Given a path and desired access, produce a minimal chmod plan with verification and safety notes."],
    },
    references: {
      troubleshooting: ["## Still permission denied", "- 可能是属主不对（用 chown 修复），或上级目录缺少执行位（目录需要 x 才能进入）。"],
      edgeCases: ["- 目录必须有执行位（x）才能 `cd` 进入；仅有读位（r）不够。"],
      examples: ["```bash", "find . -type d -exec chmod u+rwx,go+rx {} +", "```"],
    },
  },

  "filesystem/ownership-chown": {
    sources: [
      {
        label: "GNU coreutils manual: chown invocation",
        url: "https://www.gnu.org/software/coreutils/manual/html_node/chown-invocation.html",
        summary: "chown 的语法、递归选项（-R）与符号链接遍历策略（-H/-L/-P）。",
        supports: "Steps 3-5",
      },
      {
        label: "GNU coreutils manual: chgrp invocation",
        url: "https://www.gnu.org/software/coreutils/manual/html_node/chgrp-invocation.html",
        summary: "chgrp 的语法与常用选项。",
        supports: "Steps 2-3",
      },
      {
        label: "Arch man: chown(1)",
        url: "https://man.archlinux.org/man/chown.1.en.txt",
        summary: "chown(1) man page（user:group、-R、-h 等）。",
        supports: "Steps 1-5",
      },
    ],
    goal: ["用 `chown`/`chgrp` 正确设置文件属主与属组，避免递归误操作导致权限或服务问题。"],
    whenUse: [
      "服务/容器需要把目录交给特定用户运行（例如 `www-data`/`nginx`）",
      "项目目录需要共享给某个组并统一权限策略",
      "修复“Permission denied”但权限位（chmod）本身无误的情况",
    ],
    whenNot: [
      "你不清楚递归范围或目标目录里包含系统关键路径（先列清单）",
      "在生产机上临时“试试看”解决问题（先做最小变更并记录）",
    ],
    prerequisites: {
      environment: "Linux shell",
      permissions: "通常需要 sudo/root（或你是文件 owner）",
      tools: "`chown` / `chgrp`（可选 `ls`/`stat`/`find`）",
      inputs: "目标路径 + 期望的 user[:group]（是否递归）",
    },
    steps: [
      { text: "确认当前属主/属组：`ls -l <path>` 或 `stat -c '%U:%G %n' <path>`", cites: [3] },
      { text: "只改属组（共享目录常用）：`chgrp <group> <path>`", cites: [2] },
      { text: "改属主/属组：`chown <user>:<group> <path>`（只改属主可省略 `:<group>`）", cites: [1, 3] },
      {
        text: "递归前先做范围确认（dry-run 思路）：抽样列出子项并确认不会扫到挂载点/软链接树",
        cites: [3],
      },
      { text: "递归修改（谨慎）：`chown -R <user>:<group> <dir>`；遇到符号链接按需选择 `-P/-H/-L`", cites: [1, 3] },
      { text: "验证：`ls -l <dir> | head`（必要时只抽样检查关键文件）", cites: [3] },
    ],
    verification: ["抽样 `ls -l` 确认属主/属组符合预期", "以目标用户实际读写/启动一次服务验证问题已解决"],
    safety: {
      irreversible: "错误的 owner/group 可能导致服务不可用或把敏感文件暴露给不该访问的用户/组",
      privacy: "无（但变更记录中避免暴露敏感路径）",
      confirmation: "递归操作前必须明确范围；优先在小目录试跑并抽样验证，再扩大范围",
    },
    library: {
      bash: [
        "# Change owner and group for a single path",
        "sudo chown app:app ./data",
        "",
        "# Change group only (common for shared folders)",
        "sudo chgrp developers ./shared",
        "",
        "# Recursive change (be careful)",
        "sudo chown -R app:app ./var/app",
      ],
      prompt: [
        "Given a target path and desired owner/group, produce a safe chown/chgrp plan.",
        "Rules: include a pre-check step, avoid unsafe recursion, and include verification.",
      ],
    },
    references: {
      troubleshooting: [
        "## Operation not permitted / Permission denied",
        "- 你可能缺少权限：用 `sudo` 运行，或先确认当前用户是否为 owner。",
        "",
        "## Symlink ownership surprises",
        "- `chown` 默认更改“链接指向的目标”；如果你想改链接本身，参考 `-h` 选项（并理解影响）。",
      ],
      edgeCases: [
        "- `-R` 递归时对符号链接的处理可用 `-P/-H/-L` 控制；不要默认跟随到意外位置。",
        "- 某些文件系统（NFS/只读挂载/容器卷）可能限制 chown 行为。",
      ],
      examples: [
        "```bash",
        "# Preview a service directory, then fix ownership",
        "ls -ld /var/lib/myservice /var/lib/myservice/* | head",
        "sudo chown -R myservice:myservice /var/lib/myservice",
        "```",
      ],
    },
  },

  "filesystem/acl-basics": {
    sources: [
      {
        label: "Arch man: getfacl(1)",
        url: "https://man.archlinux.org/man/getfacl.1.en.txt",
        summary: "getfacl 查看文件/目录 ACL。",
        supports: "Steps 1,5",
      },
      {
        label: "Arch man: setfacl(1)",
        url: "https://man.archlinux.org/man/setfacl.1.en.txt",
        summary: "setfacl 设置/修改/删除 ACL（-m/-x/-b/-d）。",
        supports: "Steps 2-4,6",
      },
      {
        label: "Arch Wiki: Access Control Lists",
        url: "https://wiki.archlinux.org/title/Access_Control_Lists",
        summary: "ACL 基础概念、mask、默认 ACL 与常见陷阱。",
        supports: "Steps 3-4",
      },
    ],
    goal: ["用 `getfacl`/`setfacl` 为文件或目录提供更细粒度的授权（不必改变 owner/group 或全局 chmod）。"],
    whenUse: ["需要让“额外的某个用户/组”访问某个目录，但不想改 owner/group", "需要目录中新建文件自动继承权限（默认 ACL）"],
    whenNot: ["简单的 owner/group + chmod 就能解决（优先用最简单方案）", "你无法维护 ACL 的复杂度（团队需要一致策略）"],
    prerequisites: {
      environment: "Linux shell",
      permissions: "通常需要 owner 或 sudo",
      tools: "`getfacl` / `setfacl`",
      inputs: "目标路径 + 要授权的 user/group + 权限（r/w/x）",
    },
    steps: [
      { text: "查看现状：`ls -ld <path>` 然后 `getfacl -p <path>`", cites: [1] },
      { text: "给用户追加 ACL：`setfacl -m u:<user>:rw <file>` 或 `setfacl -m u:<user>:rwx <dir>`", cites: [2] },
      { text: "给组追加 ACL：`setfacl -m g:<group>:rx <dir>`（注意 mask 可能限制“有效权限”）", cites: [2, 3] },
      { text: "目录默认 ACL（让新文件继承）：`setfacl -d -m u:<user>:rwx <dir>`", cites: [2, 3] },
      { text: "验证：再次 `getfacl -p <path>`，确认条目与 effective 权限符合预期", cites: [1, 3] },
      { text: "回滚：删单条 `setfacl -x u:<user> <path>`；清空 ACL `setfacl -b <path>`", cites: [2] },
    ],
    verification: ["用目标用户实测：`sudo -u <user> ls <path>` / `cat` / `touch`（按需求验证读写）", "再次 `getfacl` 确认 ACL 已按预期生效或清理"],
    safety: {
      irreversible: "ACL 可能扩大访问范围；误配会造成越权或泄露",
      privacy: "避免在公开渠道分享包含用户/目录结构的 ACL 输出",
      confirmation: "变更前先 `getfacl` 备份（输出到文件）；变更后用目标用户实测",
    },
    library: {
      bash: [
        "# Inspect ACL",
        "getfacl -p ./shared",
        "",
        "# Allow alice to read/write",
        "sudo setfacl -m u:alice:rw ./shared/file.txt",
        "",
        "# Default ACL on directory (new files inherit)",
        "sudo setfacl -d -m u:alice:rwx ./shared",
        "",
        "# Remove alice entry / remove all ACL",
        "sudo setfacl -x u:alice ./shared/file.txt",
        "sudo setfacl -b ./shared",
      ],
      prompt: [
        "Explain ACL vs chmod, then give a minimal setfacl plan to grant a user access to a directory.",
        "Include verification with sudo -u and a rollback step.",
      ],
    },
    references: {
      troubleshooting: [
        "## Operation not supported",
        "- 文件系统/挂载可能不支持 ACL；检查 mount 选项与文件系统类型（参考 Arch Wiki）。",
        "",
        "## ACL looks correct but access still denied",
        "- 检查 `mask::`（有效权限可能被 mask 限制）；需要时调整 mask 或重新设置 ACL。",
      ],
      edgeCases: ["- 默认 ACL 只影响“新建文件/目录”；对已有内容需要单独设置。", "- 复制/打包工具可能会丢失 ACL；需要时使用支持 ACL 的备份方案。"],
      examples: [
        "```bash",
        "# Backup ACL then change",
        "getfacl -R ./shared > ./shared.acl.backup.txt",
        "sudo setfacl -m u:alice:rwx ./shared",
        "```",
      ],
    },
  },

  "filesystem/disk-usage-du-df": {
    sources: [
      {
        label: "GNU coreutils manual: df invocation",
        url: "https://www.gnu.org/software/coreutils/manual/html_node/df-invocation.html",
        summary: "df 查看文件系统容量与使用率（-h、-T、-x 等）。",
        supports: "Steps 1-2,6",
      },
      {
        label: "GNU coreutils manual: du invocation",
        url: "https://www.gnu.org/software/coreutils/manual/html_node/du-invocation.html",
        summary: "du 统计目录/文件占用（-h、--max-depth、-x 等）。",
        supports: "Steps 3-5",
      },
      {
        label: "Arch man: df(1)",
        url: "https://man.archlinux.org/man/df.1.en.txt",
        summary: "df(1) man page。",
        supports: "Steps 1-2,6",
      },
    ],
    goal: ["用 `df` 快速判断哪个文件系统快满，用 `du` 定位具体目录（必要时缩小到 Top N）。"],
    whenUse: ["磁盘告警/写入失败（No space left）", "需要找出占用最大的目录用于清理或迁移"],
    whenNot: ["你需要精确到“哪个进程占用已删除文件”（先用 `lsof`）", "对生产环境做大范围 du 扫描会造成 IO 压力（选择低峰期）"],
    prerequisites: {
      environment: "Linux shell",
      permissions: "读取目录（扫描系统目录通常需要 sudo）",
      tools: "`df` / `du` / `sort` / `tail`",
      inputs: "要排查的挂载点或目录路径",
    },
    steps: [
      { text: "先看全局：`df -hT`（关注 Use% 与文件系统类型）", cites: [1, 3] },
      { text: "排除虚拟 FS：`df -hT -x tmpfs -x devtmpfs`（更聚焦真实磁盘）", cites: [1, 3] },
      { text: "在目标目录找大户：`du -xh --max-depth=1 <dir> | sort -h`", cites: [2] },
      { text: "取 Top N：`du -xh --max-depth=1 <dir> | sort -h | tail -n 20`", cites: [2] },
      { text: "看单目录总量：`du -sh <dir>`（用于快速对比前后）", cites: [2] },
      { text: "清理/迁移后复查：再次 `df -hT` 对比 Use% 变化", cites: [1, 3] },
    ],
    verification: ["`df` Use% 下降符合预期", "对已清理目录 `du -sh` 与清理前对比"],
    safety: {
      irreversible: "清理/删除数据可能不可逆；先备份/确认保留策略",
      privacy: "`du`/路径清单可能泄露业务结构；分享前脱敏",
      confirmation: "先用 du 列出 Top N，逐项确认再删；避免在根目录全量扫描",
    },
    library: {
      bash: [
        "df -hT",
        "df -hT -x tmpfs -x devtmpfs",
        "sudo du -xh --max-depth=1 /var | sort -h | tail -n 20",
        "du -sh /var/log",
      ],
      prompt: [
        "Given a disk-full incident, produce a safe df/du triage plan.",
        "Include commands to identify the full filesystem, the top directories, and a verification step after cleanup.",
      ],
    },
    references: {
      troubleshooting: [
        "## du is slow / permission denied",
        "- 缩小范围（从挂载点下的子目录开始），必要时用 sudo；可把错误输出重定向：`2>/dev/null`。",
        "",
        "## df doesn't drop after deleting files",
        "- 可能有进程仍持有已删除文件句柄（空间未释放）；用 `lsof +L1` 查找并重启/关闭进程。",
      ],
      edgeCases: ["- `df` 与 `du` 数字不同很常见：保留块、快照/overlay、稀疏文件都会造成差异。", "- 大目录 du 扫描会产生 IO 压力；尽量在低峰期执行。"],
      examples: [
        "```bash",
        "# Find the biggest subdirectories under /home",
        "sudo du -xh --max-depth=1 /home | sort -h | tail -n 20",
        "```",
      ],
    },
  },

  "filesystem/archive-tar": {
    sources: [
      {
        label: "Arch man: tar(1)",
        url: "https://man.archlinux.org/man/tar.1.en.txt",
        summary: "tar(1) man page（-c/-x/-t、-C、压缩选项、--strip-components 等）。",
        supports: "Steps 1-5",
      },
      {
        label: "GNU tar manual",
        url: "https://www.gnu.org/software/tar/manual/html_node/index.html",
        summary: "GNU tar 官方手册（创建/解压/列出、压缩、兼容性与安全注意）。",
        supports: "Steps 1-5",
      },
      {
        label: "man7 tar(1)",
        url: "https://man7.org/linux/man-pages/man1/tar.1.html",
        summary: "tar(1) man page 镜像（第三方参考）。",
        supports: "Steps 1-5",
      },
    ],
    goal: ["用 `tar` 安全地打包/解包目录（含 gzip/xz），并在解压前做内容预览与风险控制。"],
    whenUse: ["需要把目录打包传输/备份（保留相对路径结构）", "需要解压别人提供的 tar 包（先预览再落盘）"],
    whenNot: ["解压来源不可信且你无法在隔离目录中操作（先在沙箱/临时目录处理）"],
    prerequisites: {
      environment: "Linux shell",
      permissions: "对目标目录有读权限（解压写入需要写权限）",
      tools: "`tar`（可选 `gzip`/`xz`）",
      inputs: "要打包的路径或待解压的 archive 路径 + 目标目录",
    },
    steps: [
      { text: "创建 tar.gz（推荐用 -C 控制相对路径）：`tar -C <base> -czf out.tar.gz <paths...>`", cites: [1, 2, 3] },
      { text: "解压前先预览：`tar -tzf out.tar.gz | head`（确认没有绝对路径或 `..`）", cites: [1, 2] },
      { text: "解压到指定目录：`tar -xzf out.tar.gz -C <dest>`（尽量先解到空目录）", cites: [1, 2, 3] },
      { text: "xz 压缩：创建 `tar -cJf out.tar.xz ...`；解压 `tar -xJf out.tar.xz -C <dest>`", cites: [1, 2] },
      { text: "需要丢弃顶层目录时用：`--strip-components=1`（先预览确认层级）", cites: [1, 2] },
    ],
    verification: ["解压后检查关键文件是否存在且大小合理：`ls -lah <dest>`", "必要时对关键文件做校验（hash/文件数对比）"],
    safety: {
      irreversible: "解压可能覆盖现有文件；不可信 archive 可能包含路径穿越（`../`）或绝对路径",
      privacy: "打包前确认不包含密钥/凭据/日志；必要时先清理或用排除规则",
      confirmation: "解压前必须先 `tar -t` 预览；优先解到空目录；对不可信内容在隔离环境处理",
    },
    library: {
      bash: [
        "# Create an archive (relative paths)",
        "tar -C ./project -czf project.tar.gz .",
        "",
        "# Preview",
        "tar -tzf project.tar.gz | head",
        "",
        "# Extract to a directory",
        "mkdir -p ./extract && tar -xzf project.tar.gz -C ./extract",
      ],
      prompt: ["Write a safe tar create/extract workflow with preview, extraction destination, and verification steps."],
    },
    references: {
      troubleshooting: [
        "## Not in gzip format / wrong compression flag",
        "- 先 `tar -tf <archive>` 看是否能列出；gzip/xz flag 不匹配时会报错，按实际格式选 `-z`/`-J`。",
        "",
        "## Permission/ownership surprises on extract",
        "- 不要在不理解权限影响时用 root 解压；必要时在空目录中解压并审阅再移动到目标位置。",
      ],
      edgeCases: ["- 文件名包含空格/特殊字符时，优先用预览确认；必要时使用 `--wildcards` 等选项时要更谨慎。", "- 归档中可能带绝对路径；解压前必须预览并拒绝可疑条目。"],
      examples: [
        "```bash",
        "# Extract while stripping top-level directory",
        "mkdir -p ./out",
        "tar -tf bundle.tar.gz | head",
        "tar -xzf bundle.tar.gz -C ./out --strip-components=1",
        "```",
      ],
    },
  },

  "text/view-files-less-tail": {
    sources: [
      {
        label: "Arch man: less(1)",
        url: "https://man.archlinux.org/man/less.1.en.txt",
        summary: "less 分页查看、搜索、跳转与跟随（F）。",
        supports: "Steps 1-2",
      },
      {
        label: "Arch man: tail(1)",
        url: "https://man.archlinux.org/man/tail.1.en.txt",
        summary: "tail 查看末尾与跟随输出（-n、-f、-F）。",
        supports: "Steps 3-5",
      },
      {
        label: "Arch man: head(1)",
        url: "https://man.archlinux.org/man/head.1.en.txt",
        summary: "head 查看开头（-n）。",
        supports: "Steps 2",
      },
    ],
    goal: ["用 `less`/`head`/`tail` 高效查看文件与日志（避免 `cat` 大文件），并用 `tail -F` 跟随滚动日志。"],
    whenUse: ["快速查看配置/输出的开头或结尾", "排查服务日志并实时跟随新输出", "需要在超大文件中查找/跳转（用 less 分页）"],
    whenNot: ["需要结构化分析/聚合统计（用 `awk`/`jq`/日志平台）", "文件包含敏感信息且你要把内容截图/粘贴到公开渠道"],
    prerequisites: {
      environment: "Linux shell",
      permissions: "对目标文件可读",
      tools: "`less` / `head` / `tail`",
      inputs: "目标文件路径（日志/配置/输出）",
    },
    steps: [
      { text: "分页查看：`less -N <file>`（`/pattern` 搜索，`n/N` 跳下/上一个）", cites: [1] },
      { text: "只看开头：`head -n 50 <file>`；或在 less 中直接 `g/G` 跳到开头/末尾", cites: [1, 3] },
      { text: "只看末尾：`tail -n 200 <file>`", cites: [2] },
      { text: "实时跟随：`tail -f <log>`（滚动输出）", cites: [2] },
      { text: "处理日志轮转：用 `tail -F <log>`（文件被替换/重建时更稳）", cites: [2] },
    ],
    verification: ["`tail -f/-F` 能看到新写入的日志行", "`less` 中搜索能定位到期望关键字并能来回跳转"],
    safety: {
      irreversible: "无（只读操作）",
      privacy: "日志/配置可能包含 token/密钥/用户数据；分享前脱敏",
      confirmation: "无",
    },
    library: {
      bash: [
        "less -N /var/log/syslog",
        "head -n 50 /etc/ssh/sshd_config",
        "tail -n 200 /var/log/syslog",
        "tail -F /var/log/nginx/access.log",
      ],
      prompt: ["Given a log file path, suggest a safe less/tail workflow to find errors and follow new lines."],
    },
    references: {
      troubleshooting: [
        "## tail -f stops after log rotation",
        "- 用 `tail -F` 代替 `-f`，对被轮转替换的文件更友好。",
        "",
        "## less shows strange characters",
        "- 可能是二进制/控制字符；避免直接粘贴内容，必要时先确认文件类型。",
      ],
      edgeCases: ["- 超大文件优先用 `tail -n`/`less`，避免 `cat` 全量输出。", "- 日志里可能有 ANSI 颜色码；需要时用 `less -R`（谨慎）。"],
      examples: [
        "```bash",
        "# Follow logs and search a keyword in another terminal",
        "tail -F /var/log/nginx/error.log",
        "```",
      ],
    },
  },

  "text/search-grep-ripgrep": {
    sources: [
      {
        label: "POSIX grep specification",
        url: "https://pubs.opengroup.org/onlinepubs/9699919799/utilities/grep.html",
        summary: "grep 的基本语义、退出码与常用选项。",
        supports: "Steps 1-3",
      },
      {
        label: "Arch man: grep(1)",
        url: "https://man.archlinux.org/man/grep.1.en.txt",
        summary: "GNU grep 选项（-n/-R/-i/-E/-F/-C 等）。",
        supports: "Steps 1-5",
      },
      {
        label: "ripgrep GUIDE (raw)",
        url: "https://raw.githubusercontent.com/BurntSushi/ripgrep/master/GUIDE.md",
        summary: "ripgrep（rg）用法与性能/过滤/忽略规则说明。",
        supports: "Steps 2-6",
      },
      {
        label: "Arch man: rg(1)",
        url: "https://man.archlinux.org/man/rg.1.en.txt",
        summary: "rg(1) man page（--hidden、--glob、--type 等）。",
        supports: "Steps 2-6",
      },
    ],
    goal: ["用 `grep`/`rg` 在代码/日志中快速定位关键字与正则匹配位置（带行号、上下文、过滤规则）。"],
    whenUse: ["排查报错：在仓库中搜索错误码/函数名/配置项", "在日志中找某段时间窗口的异常关键词", "需要批量定位某个模式出现在哪些文件"],
    whenNot: ["需要跨仓库/大规模全文检索（考虑专用搜索服务）", "需要解析结构化日志/JSON（优先用 `jq`）"],
    prerequisites: {
      environment: "Linux shell",
      permissions: "对目标文件可读",
      tools: "`grep`（推荐）/`rg`（更快，默认递归并尊重 .gitignore）",
      inputs: "pattern（关键字/正则） + 搜索路径",
    },
    steps: [
      { text: "单文件带行号：`grep -n 'pattern' file`", cites: [1, 2] },
      { text: "递归搜：优先用 `rg 'pattern' <path>`；或 `grep -R -n 'pattern' <path>`", cites: [2, 3, 4] },
      { text: "忽略大小写/整词：`grep -niw 'pattern' ...`；rg 用 `-i -w`", cites: [1, 2, 4] },
      { text: "正则 vs 纯文本：`grep -E 're'`（正则）/ `grep -F 'literal'`（不解释正则）", cites: [2] },
      { text: "上下文：`grep -n -C 3 'pattern' ...`；rg 用 `-C 3`", cites: [2, 4] },
      { text: "过滤文件/目录：rg 用 `--glob '!node_modules/**'`、`--hidden`；必要时先收敛范围再扩大", cites: [3, 4] },
    ],
    verification: ["抽样打开匹配文件确认命中是否为真（避免误匹配）", "加/减过滤条件，确保结果集符合预期范围"],
    safety: {
      irreversible: "无（只读操作）",
      privacy: "搜索结果可能包含密钥/用户数据；分享前脱敏或只给路径/行号",
      confirmation: "无",
    },
    library: {
      bash: [
        "rg -n \"TODO\" .",
        "rg -n \"password|token|secret\" . --hidden --glob '!node_modules/**'",
        "grep -R -n -C 2 \"ERROR\" /var/log 2>/dev/null | head",
      ],
      prompt: ["Given a pattern and a codebase path, propose a fast rg/grep search plan with context and safe output handling."],
    },
    references: {
      troubleshooting: [
        "## Permission denied spam",
        "- 缩小搜索根目录；或把错误输出重定向：`2>/dev/null`（仅用于只读排查）。",
        "",
        "## Binary file matches",
        "- grep 可能提示二进制匹配；按需排除二进制文件或用工具先识别文件类型。",
      ],
      edgeCases: ["- 正则引擎差异：grep/rg 的正则语法不完全一致；遇到复杂模式先用简单模式验证。", "- 默认忽略规则：rg 会尊重 `.gitignore`；需要包含隐藏文件时加 `--hidden`。"],
      examples: [
        "```bash",
        "# Find a symbol and show 5 lines of context",
        "rg -n -C 5 \"initConfig\" ./src",
        "```",
      ],
    },
  },

  "text/replace-sed": {
    sources: [
      {
        label: "GNU sed manual",
        url: "https://www.gnu.org/software/sed/manual/sed.html",
        summary: "sed 的替换命令、地址范围与常见脚本用法。",
        supports: "Steps 1-5",
      },
      {
        label: "POSIX sed specification",
        url: "https://pubs.opengroup.org/onlinepubs/9699919799/utilities/sed.html",
        summary: "POSIX sed 规范（可移植语义）。",
        supports: "Steps 1-2",
      },
      {
        label: "Arch man: sed(1)",
        url: "https://man.archlinux.org/man/sed.1.en.txt",
        summary: "sed(1) man page（-i、-E 等）。",
        supports: "Steps 1-4",
      },
    ],
    goal: ["用 `sed` 做安全的批量替换：先预览，再就地修改（带备份），最后验证替换结果。"],
    whenUse: ["需要在一批文本文件中替换配置项/URL/路径", "需要对满足条件的行做局部替换（不想手改）"],
    whenNot: ["需要复杂的多行/结构化编辑（优先用专用工具或脚本）", "替换风险高且没有备份/回滚方案"],
    prerequisites: {
      environment: "Linux shell",
      permissions: "对目标文件可读写",
      tools: "`sed`（可选 `rg`/`diff` 用于验证）",
      inputs: "旧字符串/正则 + 新字符串 + 文件路径/文件集合",
    },
    steps: [
      { text: "先预览（不写入）：`sed 's/old/new/g' <file> | head`", cites: [1, 2, 3] },
      { text: "限定范围：例如只替换匹配行：`sed '/^key=/s/old/new/' <file>`", cites: [1, 2] },
      { text: "就地修改并备份：`sed -i.bak 's/old/new/g' <file>`（生成 .bak 便于回滚）", cites: [1, 3] },
      { text: "路径替换建议换分隔符：`sed -i.bak 's|/old/path|/new/path|g' <file>`", cites: [1] },
      { text: "验证：用 `rg old <paths>` 或对比备份 `diff -u <file>.bak <file>`", cites: [1] },
    ],
    verification: ["关键文件 `diff` 符合预期；并且程序/配置可正常加载", "再次搜索 `old` 确认不再出现（或只在注释/文档中出现）"],
    safety: {
      irreversible: "就地修改可能破坏配置/代码；没有备份会难以回滚",
      privacy: "替换内容可能包含凭据/内部域名；分享命令时注意脱敏",
      confirmation: "先预览，再带备份执行；对生产配置文件建议先在副本上验证",
    },
    library: {
      bash: [
        "# Preview",
        "sed 's/foo/bar/g' ./config.ini | head",
        "",
        "# In-place with backup",
        "sed -i.bak 's/foo/bar/g' ./config.ini",
        "",
        "# Rollback",
        "mv ./config.ini.bak ./config.ini",
      ],
      prompt: ["Given old/new strings and target files, produce a safe sed replacement plan with preview, backup, and verification."],
    },
    references: {
      troubleshooting: [
        "## 'sed -i' behaves differently on macOS vs Linux",
        "- 不同实现对 `-i` 参数不同；在 Linux 上建议使用 `-i.bak` 明确生成备份。",
        "",
        "## Special characters break the replacement",
        "- 替换字符串包含 `/`/`&` 等需要转义；或使用不同分隔符（如 `|`）。",
      ],
      edgeCases: ["- 正则匹配默认是“贪婪/最左最长”等实现差异”；先用小样本验证。", "- 批量处理前先在 1-2 个代表文件试跑。"],
      examples: ["```bash", "# Replace only in a section-like prefix", "sed -i.bak '/^\\[prod\\]/,/^\\[/ s|http://old|http://new|g' ./app.ini", "```"],
    },
  },

  "text/parse-awk": {
    sources: [
      {
        label: "POSIX awk specification",
        url: "https://pubs.opengroup.org/onlinepubs/9699919799/utilities/awk.html",
        summary: "awk 的语言与字段/记录处理模型（$1、FS、NR、END 等）。",
        supports: "Steps 1-5",
      },
      {
        label: "GNU gawk manual",
        url: "https://www.gnu.org/software/gawk/manual/gawk.html",
        summary: "gawk 手册（字段分隔、变量传入、常见模式动作）。",
        supports: "Steps 2-5",
      },
      {
        label: "Arch man: awk(1)",
        url: "https://man.archlinux.org/man/awk.1.en.txt",
        summary: "awk(1) man page。",
        supports: "Steps 1-4",
      },
    ],
    goal: ["用 `awk` 对“按行记录、按列字段”的文本做提取、过滤与简单聚合（不写复杂脚本也能解决 80%）。"],
    whenUse: ["从 `ps`/`df`/日志等输出中提取列并做统计", "处理 CSV/TSV/空格分隔表格并导出某些字段"],
    whenNot: ["需要复杂 JSON/嵌套结构解析（优先用 `jq`）", "需要大型数据处理/联表（优先用专用工具或脚本语言）"],
    prerequisites: {
      environment: "Linux shell",
      permissions: "读取输入文件/命令输出",
      tools: "`awk`",
      inputs: "输入文本（文件或管道）+ 目标字段/过滤条件/统计需求",
    },
    steps: [
      { text: "打印列：`awk '{print $1, $3}' <file>`", cites: [1, 3] },
      { text: "指定分隔符：`awk -F',' '{print $1, $2}' data.csv`", cites: [1, 2] },
      { text: "过滤：`awk '$3 > 100 {print $1, $3}' <file>`", cites: [1] },
      { text: "跳过表头：`awk 'NR==1{next} {print $0}' <file>`", cites: [1] },
      { text: "聚合：`awk '{sum+=$2} END{print sum}' <file>`（可配合 -v 传参）", cites: [1, 2] },
    ],
    verification: ["抽样输出确认列选择正确；必要时先 `head` 小样本再跑全量", "用 `wc -l` 或手算对照验证统计结果是否合理"],
    safety: {
      irreversible: "无（只读/输出操作；除非你把输出重定向覆盖原文件）",
      privacy: "避免把包含用户数据的整行输出到公开渠道；优先输出必要字段",
      confirmation: "对生产日志/大文件先用 `head`/小范围验证 awk 逻辑再全量跑",
    },
    library: {
      bash: [
        "# Sum the 2nd column (skip header)",
        "awk 'NR==1{next} {sum+=$2} END{print sum}' data.tsv",
        "",
        "# Filter lines where 3rd column > 100",
        "awk '$3>100 {print $1, $3}' metrics.txt | head",
      ],
      prompt: ["Given a sample line format and a goal (extract/filter/sum), write a minimal awk one-liner plus a verification command."],
    },
    references: {
      troubleshooting: [
        "## Fields are not split as expected",
        "- 默认按空白分隔；CSV/TSV 请设置 `-F','` 或 `-F'\\t'`。",
        "",
        "## Numbers treated as strings",
        "- 确认列中无逗号/单位；必要时先清洗或在 awk 中做转换。",
      ],
      edgeCases: ["- 多个空格/制表混用时字段可能偏移；先打印 `NF` 与各列检查。", "- 对超大文件，awk 仍会全量扫描；先用过滤条件减少数据量。"],
      examples: ["```bash", "# Print first 5 columns with line numbers", "awk '{print NR \":\" $1, $2, $3, $4, $5}' file.txt | head", "```"],
    },
  },

  "network/download-curl-wget": {
    sources: [
      {
        label: "Arch man: curl(1)",
        url: "https://man.archlinux.org/man/curl.1.en.txt",
        summary: "curl 的下载、header、重试/超时、代理与认证相关选项。",
        supports: "Steps 1-6",
      },
      {
        label: "Arch man: wget(1)",
        url: "https://man.archlinux.org/man/wget.1.en.txt",
        summary: "wget 的下载、递归、断点续传与重试/超时选项。",
        supports: "Steps 1,3-6",
      },
      {
        label: "curl docs: manpage",
        url: "https://curl.se/docs/manpage.html",
        summary: "curl 官方 manpage（HTTP 调试与网络选项说明）。",
        supports: "Steps 2-6",
      },
    ],
    goal: ["用 `curl`/`wget` 下载文件并调试 HTTP（查看 header、跟随重定向、重试、代理），同时避免泄露凭据。"],
    whenUse: ["需要下载 artifact/数据集/脚本", "需要排查 HTTP 状态码、重定向与 header", "网络不稳定需要断点续传/重试策略"],
    whenNot: ["需要自动化认证/复杂会话管理（优先用专用 SDK 或脚本）", "不确定 URL 是否可信（避免直接执行下载的脚本）"],
    prerequisites: {
      environment: "Linux shell",
      permissions: "写入目标目录权限",
      tools: "`curl` / `wget`",
      inputs: "URL + 保存位置（可选：代理、header、认证方式）",
    },
    steps: [
      { text: "最简单下载：`curl -LO <url>`（保留远端文件名）或 `wget <url>`", cites: [1, 2] },
      { text: "看响应头/状态码：`curl -I <url>`；需要更详细可用 `curl -v <url>`", cites: [1, 3] },
      { text: "跟随重定向：`curl -L -O <url>`；wget 可用 `--max-redirect` 控制", cites: [1, 2, 3] },
      { text: "断点续传：`curl -C - -LO <url>`；wget 用 `-c`", cites: [1, 2, 3] },
      { text: "重试/超时：`curl --retry 5 --retry-delay 1 --connect-timeout 5 --max-time 30 ...`；wget 用 `--tries/--timeout`", cites: [1, 2, 3] },
      { text: "代理/自定义 header：`curl -x http://proxy:port -H 'Key: Value' ...`（避免把 token 写进 shell history）", cites: [1, 3] },
    ],
    verification: ["下载后校验大小/哈希：`ls -lh` + `sha256sum`（如有官方 checksum）", "用 `file`/`tar -t` 等验证文件格式是否正确"],
    safety: {
      irreversible: "下载本身可逆，但“执行下载内容”可能造成不可逆后果",
      privacy: "避免在命令行/日志中暴露 `Authorization`、cookie、token；必要时用环境变量或 `--config` 文件",
      confirmation: "对不可信 URL 不要 `curl | sh`；先保存、审阅、再执行",
    },
    library: {
      bash: [
        "curl -I https://example.com",
        "curl -L -O https://example.com/file.tar.gz",
        "curl --retry 5 --retry-delay 1 --connect-timeout 5 --max-time 30 -L -O https://example.com/file.tar.gz",
        "wget -c https://example.com/big.iso",
      ],
      prompt: ["Given a URL and constraints (proxy, retry, timeout), output a safe curl/wget download plan with verification and credential-safety notes."],
    },
    references: {
      troubleshooting: [
        "## TLS/SSL errors",
        "- 优先检查系统时间、CA 证书与代理；不要轻易用 `-k/--insecure`（会绕过验证）。",
        "",
        "## 403/401 unauthorized",
        "- 检查是否需要 token/header；避免把 token 直接写在命令行历史里。",
      ],
      edgeCases: ["- 某些下载站会根据 User-Agent/重定向链路返回不同内容；必要时抓 header 验证。", "- 对大文件下载建议使用断点续传与校验和。"],
      examples: ["```bash", "# Download to a specific name", "curl -L -o artifact.tgz https://example.com/artifact.tgz", "```"],
    },
  },

  "network/dns-dig-nslookup": {
    sources: [
      {
        label: "Arch man: dig(1)",
        url: "https://man.archlinux.org/man/dig.1.en.txt",
        summary: "dig 查询 DNS 记录（@server、+short、-x 等）。",
        supports: "Steps 1-4",
      },
      {
        label: "Arch man: nslookup(1)",
        url: "https://man.archlinux.org/man/nslookup.1.en.txt",
        summary: "nslookup 基础查询与交互模式。",
        supports: "Steps 5",
      },
      {
        label: "Arch man: resolv.conf(5)",
        url: "https://man.archlinux.org/man/resolv.conf.5.en.txt",
        summary: "系统解析器配置（nameserver/search/options）。",
        supports: "Steps 6",
      },
    ],
    goal: ["用 `dig`/`nslookup` 排查 DNS：看解析结果、TTL、CNAME 链路，并对比不同解析服务器。"],
    whenUse: ["域名解析异常/不一致（不同网络返回不同 IP）", "需要确认某条记录是否已生效（TTL/缓存）", "排查反向解析或 DNS 服务器配置问题"],
    whenNot: ["问题不在 DNS（例如 TCP 连接被防火墙阻断）", "域名为内部敏感域（避免在公共 DNS 上泄露）"],
    prerequisites: {
      environment: "Linux shell",
      permissions: "无（只读查询；读 /etc/resolv.conf 需要可读）",
      tools: "`dig` / `nslookup`（通常来自 bind-tools）",
      inputs: "域名或 IP + 期望记录类型（A/AAAA/CNAME/TXT/MX）+ 可选 DNS 服务器",
    },
    steps: [
      { text: "快速看 A/AAAA：`dig example.com A +short` / `dig example.com AAAA +short`", cites: [1] },
      { text: "指定解析服务器对比：`dig @1.1.1.1 example.com A +short`（或公司 DNS）", cites: [1] },
      { text: "看 CNAME 链与 TTL：`dig example.com CNAME`（answer 里带 TTL）", cites: [1] },
      { text: "反向解析：`dig -x <ip> +short`", cites: [1] },
      { text: "对比系统工具：`nslookup example.com`（快速 sanity check）", cites: [2] },
      { text: "检查本机 resolver 配置：`cat /etc/resolv.conf`（nameserver/search/options）", cites: [3] },
    ],
    verification: ["对比不同解析器返回是否一致（A/AAAA/CNAME）", "结合 TTL 判断缓存窗口；等待 TTL 后再验证生效"],
    safety: {
      irreversible: "无（只读查询）",
      privacy: "DNS 查询会被解析器记录；内部域名尽量在内网 DNS 上查，不要在公共 DNS 上泄露",
      confirmation: "无",
    },
    library: {
      bash: [
        "dig example.com A +short",
        "dig @1.1.1.1 example.com AAAA +short",
        "dig example.com CNAME",
        "dig -x 8.8.8.8 +short",
        "cat /etc/resolv.conf",
      ],
      prompt: ["Given a domain and symptoms (wrong IP / NXDOMAIN / slow), write a dig-based DNS triage plan including checks with a specific resolver."],
    },
    references: {
      troubleshooting: [
        "## NXDOMAIN vs SERVFAIL",
        "- NXDOMAIN：域名不存在或查询类型不对；SERVFAIL：上游/递归解析失败或 DNSSEC 等问题（需要换 resolver 对比）。",
        "",
        "## Different answers in different networks",
        "- 可能是 split-horizon DNS 或 CDN；用 `dig @<server>` 固定 resolver 再判断。",
      ],
      edgeCases: ["- `ANY` 查询常被禁用/不可靠；优先查明确记录类型（A/AAAA/CNAME/TXT）。", "- `/etc/hosts` 也会影响解析结果；必要时检查。"],
      examples: ["```bash", "# Query TXT record (e.g., SPF)", "dig example.com TXT +short", "```"],
    },
  },

  "network/connectivity-ping-traceroute": {
    sources: [
      {
        label: "Arch man: ping(8)",
        url: "https://man.archlinux.org/man/ping.8.en.txt",
        summary: "ping 的参数（-c、-i、-W 等）与输出含义。",
        supports: "Steps 1-2",
      },
      {
        label: "Arch man: traceroute(8)",
        url: "https://man.archlinux.org/man/traceroute.8.en.txt",
        summary: "traceroute 路由诊断（-n、-I 等）。",
        supports: "Steps 3-4",
      },
      {
        label: "Arch man: tracepath(8)",
        url: "https://man.archlinux.org/man/tracepath.8.en.txt",
        summary: "tracepath 无需特权的路径探测（适合 traceroute 受限时）。",
        supports: "Steps 5",
      },
    ],
    goal: ["用 `ping` 判断是否可达/是否丢包，用 `traceroute/tracepath` 定位网络路径中哪一跳出现问题。"],
    whenUse: ["服务不可达（超时/连接失败）需要先判断网络层问题", "需要区分“本机->网关->公网->目标”哪一段有问题"],
    whenNot: ["目标明确禁止 ICMP（ping 不通不代表 TCP 不通）", "在对方网络做高频探测（避免被判为攻击）"],
    prerequisites: {
      environment: "Linux shell",
      permissions: "某些系统对 ping 需要特权（依发行版而定）；traceroute 某些模式可能需要权限",
      tools: "`ping` / `traceroute` / `tracepath`",
      inputs: "目标主机名或 IP",
    },
    steps: [
      { text: "基础可达性：`ping -c 4 <host>`（看丢包率与 RTT）", cites: [1] },
      { text: "控制等待/次数：`ping -c 10 -W 2 <host>`（减少长时间阻塞）", cites: [1] },
      { text: "路径定位：`traceroute -n <host>`（-n 不做 DNS 解析更快更稳定）", cites: [2] },
      { text: "必要时改用 ICMP：`traceroute -I -n <host>`（在 UDP 被屏蔽时尝试）", cites: [2] },
      { text: "traceroute 受限时：`tracepath <host>`（无需特权，输出 MTU/路径信息）", cites: [3] },
    ],
    verification: ["问题修复后 ping 丢包下降、RTT 恢复正常；traceroute 不再卡在某一跳", "再用应用层验证（curl/ssh）确认服务恢复"],
    safety: {
      irreversible: "无（探测型命令）",
      privacy: "对外发包会暴露你的源 IP 与探测行为；在敏感环境遵循安全策略",
      confirmation: "控制频率与次数（-c）；避免长时间高频 ping",
    },
    library: {
      bash: ["ping -c 4 1.1.1.1", "traceroute -n example.com", "traceroute -I -n example.com", "tracepath example.com"],
      prompt: ["Given a connectivity issue, propose a minimal ping+traceroute workflow with safe rate/timeout settings and interpretation notes."],
    },
    references: {
      troubleshooting: [
        "## ping fails but service still works",
        "- 目标可能禁 ICMP；改用应用层探测（例如 `curl -I` 或 `nc`/`ss`）。",
        "",
        "## traceroute shows * * *",
        "- 中间路由器可能不回 TTL exceeded；不代表一定故障。结合应用层与多地对比。",
      ],
      edgeCases: ["- 运营商/企业网络可能对 traceroute/ICMP 做限速或过滤。", "- IPv6 环境下用 `ping -6`/`traceroute -6` 进行对应诊断。"],
      examples: ["```bash", "# Quick check with timeouts", "ping -c 5 -W 2 example.com", "```"],
    },
  },

  "network/ports-ss-lsof": {
    sources: [
      {
        label: "Arch man: ss(8)",
        url: "https://man.archlinux.org/man/ss.8.en.txt",
        summary: "ss 列出 socket（-l/-n/-t/-u/-p、过滤表达式）。",
        supports: "Steps 1-2,5",
      },
      {
        label: "Arch man: lsof(8)",
        url: "https://man.archlinux.org/man/lsof.8.en.txt",
        summary: "lsof 列出进程打开的文件/网络端口（-i、-nP 等）。",
        supports: "Steps 3,5",
      },
      {
        label: "Arch man: fuser(1)",
        url: "https://man.archlinux.org/man/fuser.1.en.txt",
        summary: "fuser 查询占用某资源的进程（-n tcp/udp）。",
        supports: "Steps 4",
      },
    ],
    goal: ["用 `ss`/`lsof` 找出“谁在监听某个端口/谁占用某个连接”，用于端口冲突与服务排查。"],
    whenUse: ["服务启动失败提示端口被占用", "需要确认某端口是否在监听、由哪个进程监听", "排查异常连接数或可疑监听端口"],
    whenNot: ["你准备直接 kill 进程但不确定影响范围（先确认服务归属与依赖）"],
    prerequisites: {
      environment: "Linux shell",
      permissions: "查看进程信息通常需要 sudo（尤其是 -p 显示进程）",
      tools: "`ss` / `lsof` / `fuser`",
      inputs: "端口号（TCP/UDP）或服务名",
    },
    steps: [
      { text: "列出监听端口：`ss -lntup`（TCP/UDP + 进程）", cites: [1] },
      { text: "按端口过滤：`ss -lntup 'sport = :443'`（或先全量再 grep）", cites: [1] },
      { text: "用 lsof 定位监听者：`sudo lsof -i :443 -sTCP:LISTEN -nP`", cites: [2] },
      { text: "快速拿 PID：`sudo fuser -n tcp 443`（谨慎使用后续 kill）", cites: [3] },
      { text: "验证修复：停止/调整服务后重新 `ss -lntup` 确认端口状态变化", cites: [1] },
    ],
    verification: ["目标端口的监听进程与期望一致（或已释放）", "应用层访问（curl/浏览器）验证服务恢复"],
    safety: {
      irreversible: "kill 错进程可能造成服务中断；端口调整可能影响依赖方",
      privacy: "连接信息可能包含内网 IP/端口；分享前脱敏",
      confirmation: "在 kill 前先确认 PID 对应的服务与 owner；优先用 systemctl 停服务而不是直接 kill",
    },
    library: {
      bash: ["ss -lntup | head", "ss -lntup 'sport = :3000'", "sudo lsof -i :3000 -sTCP:LISTEN -nP", "sudo fuser -n tcp 3000"],
      prompt: ["Given a port conflict, propose an ss/lsof workflow to identify the owning process and safely stop or reconfigure it."],
    },
    references: {
      troubleshooting: [
        "## ss shows no process name",
        "- 需要权限：加 sudo；或系统限制进程信息暴露。",
        "",
        "## Port is used but not LISTEN",
        "- 可能是客户端连接或 TIME_WAIT；检查 `ss -antup` 并理解连接状态。",
      ],
      edgeCases: ["- 容器/网络命名空间下的端口需要在对应 namespace 里查看（docker/podman）。", "- UDP 没有 LISTEN 的概念，使用 `ss -lunp` 查看。"],
      examples: ["```bash", "# Show TCP connections to a port", "ss -antp | rg ':443' | head", "```"],
    },
  },

  "ssh/ssh-keys": {
    sources: [
      {
        label: "Arch man: ssh-keygen(1)",
        url: "https://man.archlinux.org/man/ssh-keygen.1.en.txt",
        summary: "ssh-keygen 生成密钥、类型选择与常用参数。",
        supports: "Steps 1",
      },
      {
        label: "Arch man: ssh-agent(1)",
        url: "https://man.archlinux.org/man/ssh-agent.1.en.txt",
        summary: "ssh-agent/ssh-add 的作用与使用方式。",
        supports: "Steps 2",
      },
      {
        label: "Debian man: authorized_keys(5)",
        url: "https://manpages.debian.org/bookworm/openssh-server/authorized_keys.5.en.html",
        summary: "authorized_keys 文件格式、权限要求与安全注意。",
        supports: "Steps 3-4",
      },
      {
        label: "Arch man: ssh-copy-id(1)",
        url: "https://man.archlinux.org/man/ssh-copy-id.1.en.txt",
        summary: "ssh-copy-id 把公钥安装到远端 authorized_keys。",
        supports: "Steps 3",
      },
    ],
    goal: ["生成 SSH 密钥、正确配置 `ssh-agent` 与 `authorized_keys`，用无密码（或带 passphrase）方式安全登录。"],
    whenUse: ["你需要免密登录服务器/Git 仓库（推荐用 passphrase + agent）", "你需要为某个自动化任务创建单独 key 并做最小授权"],
    whenNot: ["你准备把私钥粘贴到聊天/工单（绝对不要）", "你不理解 key 的用途与权限边界（先学习，再操作）"],
    prerequisites: {
      environment: "Linux shell / OpenSSH client",
      permissions: "本机写入 ~/.ssh；远端需要能修改目标用户的 ~/.ssh/authorized_keys",
      tools: "`ssh-keygen` / `ssh-agent` / `ssh-add` / `ssh`（可选 `ssh-copy-id`）",
      inputs: "密钥用途（人用/CI）、注释（email/host）、远端 user@host（如需登录）",
    },
    steps: [
      { text: "生成密钥（推荐 ed25519）：`ssh-keygen -t ed25519 -C '<comment>' -f ~/.ssh/id_ed25519`（建议设置 passphrase）", cites: [1] },
      { text: "启动 agent 并加载 key：`eval \"$(ssh-agent -s)\"` 然后 `ssh-add ~/.ssh/id_ed25519`", cites: [2] },
      { text: "把公钥安装到远端：`ssh-copy-id -i ~/.ssh/id_ed25519.pub <user>@<host>`（或手动追加到 authorized_keys）", cites: [3, 4] },
      { text: "确认权限：`chmod 700 ~/.ssh`；远端 `chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys`", cites: [3] },
      { text: "验证登录：`ssh -v <user>@<host>`（必要时看使用的 key/agent）", cites: [2] },
    ],
    verification: ["`ssh <user>@<host>` 可直接登录且不会提示 password（或仅提示 passphrase/agent）", "远端 `~/.ssh/authorized_keys` 只包含你期望的公钥"],
    safety: {
      irreversible: "把错误的公钥写入 authorized_keys 可能造成越权；删除现有 key 可能导致你自己无法登录",
      privacy: "私钥必须保密；公钥可公开但仍要避免把敏感注释/内部主机名暴露出去",
      confirmation: "改动远端前先保留现有 authorized_keys 备份；确认至少保留一个可用登录方式（别锁死自己）",
    },
    library: {
      bash: [
        "ssh-keygen -t ed25519 -C \"me@example.com\" -f ~/.ssh/id_ed25519",
        "eval \"$(ssh-agent -s)\"",
        "ssh-add ~/.ssh/id_ed25519",
        "ssh-copy-id -i ~/.ssh/id_ed25519.pub user@host",
        "ssh -v user@host",
      ],
      prompt: ["Create a secure SSH key setup guide for a user, including agent usage, authorized_keys permissions, and a verification login command."],
    },
    references: {
      troubleshooting: [
        "## Permission denied (publickey)",
        "- 检查远端 `~/.ssh` 与 `authorized_keys` 权限；确认公钥已正确追加且没有多余空格/换行。",
        "",
        "## Wrong key is used",
        "- 用 `ssh -v` 看加载的 key；必要时在 `~/.ssh/config` 指定 `IdentityFile`。",
      ],
      edgeCases: ["- 服务器可能禁用 root 登录或只允许特定 key 选项；需要管理员策略配合。", "- 多 key 场景建议为不同用途创建不同 key，并在 authorized_keys 配置限制（command/from 等）。"],
      examples: [
        "```bash",
        "# Show the public key (copy to GitHub/servers)",
        "cat ~/.ssh/id_ed25519.pub",
        "```",
      ],
    },
  },

  "ssh/scp-rsync": {
    sources: [
      {
        label: "Arch man: scp(1)",
        url: "https://man.archlinux.org/man/scp.1.en.txt",
        summary: "scp 的拷贝语法、递归与常用参数。",
        supports: "Steps 1-2",
      },
      {
        label: "Arch man: rsync(1)",
        url: "https://man.archlinux.org/man/rsync.1.en.txt",
        summary: "rsync 增量同步、保留属性（-a）、进度与 dry-run 等。",
        supports: "Steps 3-5",
      },
      {
        label: "rsync official manpage (plain text)",
        url: "https://download.samba.org/pub/rsync/rsync.1",
        summary: "rsync 官方 manpage（参数与语义）。",
        supports: "Steps 3-5",
      },
    ],
    goal: ["在主机间安全传输文件：简单一次性用 `scp`，需要增量/断点/大目录同步优先用 `rsync`（带 dry-run）。"],
    whenUse: ["复制少量文件到远端（scp 简单）", "同步大目录/重复同步（rsync 更快更安全）", "需要保留权限/时间戳并显示进度（rsync -aP）"],
    whenNot: ["你不确定源/目标路径是否正确且准备带 `--delete`（高风险）"],
    prerequisites: {
      environment: "Linux shell / SSH",
      permissions: "远端目标路径写权限；SSH 登录权限",
      tools: "`scp` / `rsync` / `ssh`",
      inputs: "源路径 + 远端 user@host:dest（方向：push/pull）",
    },
    steps: [
      { text: "单文件 scp：`scp <file> <user>@<host>:/path/`（反向拉取：把左右互换）", cites: [1] },
      { text: "目录 scp：`scp -r <dir> <user>@<host>:/path/`（适合一次性拷贝）", cites: [1] },
      { text: "增量同步 rsync：`rsync -avP -e ssh <src>/ <user>@<host>:<dest>/`（注意尾部 `/`）", cites: [2, 3] },
      { text: "先 dry-run：`rsync -avP --dry-run -e ssh <src>/ <user>@<host>:<dest>/`", cites: [2, 3] },
      { text: "谨慎删除同步：仅在确认目标目录无独立数据时使用 `--delete`（建议先 dry-run）", cites: [2, 3] },
    ],
    verification: ["在远端 `ls -lah <dest>` 抽样检查；或比较文件数/大小", "重复跑 rsync 时应很快结束（说明增量生效）"],
    safety: {
      irreversible: "`rsync --delete` 可能删除目标文件；scp/rsync 也可能覆盖同名文件",
      privacy: "传输前确认不包含密钥/凭据；必要时用加密/权限隔离",
      confirmation: "任何涉及覆盖/删除的同步先 dry-run；确认 rsync 的源/目标尾部 `/` 语义",
    },
    library: {
      bash: [
        "scp ./file.txt user@host:/tmp/",
        "scp -r ./dir user@host:/tmp/",
        "rsync -avP --dry-run -e ssh ./dir/ user@host:/tmp/dir/",
        "rsync -avP -e ssh ./dir/ user@host:/tmp/dir/",
      ],
      prompt: ["Given src and dest paths, choose scp or rsync, then output safe commands including dry-run and verification. Warn about --delete and trailing slashes."],
    },
    references: {
      troubleshooting: [
        "## rsync copies everything every time",
        "- 检查是否每次都变更了 mtime/权限；或源/目标路径写错导致没命中增量。",
        "",
        "## Permission denied on remote",
        "- 确认远端目录权限；必要时把目标改到你有权限的目录或通过 sudo+rsync（更复杂，需谨慎）。",
      ],
      edgeCases: ["- rsync 源路径末尾 `/` 影响“同步目录本身 vs 同步目录内容”；先 dry-run 确认。", "- 跨平台（macOS/Linux）权限/ACL 行为可能不同。"],
      examples: ["```bash", "# Pull logs from remote to local", "rsync -avP -e ssh user@host:/var/log/nginx/ ./nginx-logs/", "```"],
    },
  },

  "process/ps-top-kill": {
    sources: [
      {
        label: "Arch man: ps(1)",
        url: "https://man.archlinux.org/man/ps.1.en.txt",
        summary: "ps 查看进程列表与格式化输出。",
        supports: "Steps 1-2",
      },
      {
        label: "Arch man: top(1)",
        url: "https://man.archlinux.org/man/top.1.en.txt",
        summary: "top 实时观察 CPU/内存与排序/过滤。",
        supports: "Steps 3",
      },
      {
        label: "POSIX kill specification",
        url: "https://pubs.opengroup.org/onlinepubs/9699919799/utilities/kill.html",
        summary: "kill 的信号语义与退出码。",
        supports: "Steps 4-5",
      },
      {
        label: "Arch man: kill(1)",
        url: "https://man.archlinux.org/man/kill.1.en.txt",
        summary: "kill(1) man page（信号列表等）。",
        supports: "Steps 4-5",
      },
    ],
    goal: ["用 `ps/top` 找到目标进程与资源瓶颈，用 `kill` 按“先温和后强制”的顺序安全终止进程。"],
    whenUse: ["进程卡死/占用 CPU 或内存异常，需要定位并处理", "服务异常需要确认是否有多个实例/僵尸进程", "脚本启动了错误的后台任务需要停止"],
    whenNot: ["你不确定 PID 属于哪个服务且可能影响生产（先确认 owner/用途）", "systemd 管理的服务（优先 `systemctl stop` 而不是直接 kill）"],
    prerequisites: {
      environment: "Linux shell",
      permissions: "终止其他用户进程通常需要 sudo/root",
      tools: "`ps` / `top` / `kill`",
      inputs: "进程名或 PID（以及你期望的行为：优雅退出/强制终止）",
    },
    steps: [
      { text: "列出进程（抽样定位）：`ps aux | head` 或 `ps -ef | head`", cites: [1] },
      { text: "按需格式化输出：例如 `ps -eo pid,ppid,user,%cpu,%mem,etime,cmd | head`", cites: [1] },
      { text: "实时观察资源：`top`（在 top 内按 `P/M` 排序，看 %CPU/%MEM）", cites: [2] },
      { text: "先优雅终止：`kill -TERM <pid>`（给进程时间清理资源）", cites: [3, 4] },
      { text: "仍不退出再强制：等待几秒后 `kill -KILL <pid>`（最后手段）", cites: [3, 4] },
    ],
    verification: ["`ps`/`top` 中进程不再存在（或资源恢复正常）", "如是服务进程：检查服务是否被自动拉起（systemd/supervisor）并做相应处理"],
    safety: {
      irreversible: "kill 可能导致未保存数据丢失、服务中断；`-KILL` 无法让进程清理资源",
      privacy: "ps/top 输出可能包含命令行参数（token/密码）；分享前脱敏",
      confirmation: "终止前确认 PID 对应服务与影响范围；优先使用服务管理器停服务；严格遵循先 TERM 后 KILL",
    },
    library: {
      bash: [
        "ps -eo pid,user,%cpu,%mem,etime,cmd --sort=-%cpu | head",
        "top",
        "kill -TERM 12345",
        "sleep 5; kill -KILL 12345",
      ],
      prompt: ["Given a suspected runaway process, output a safe investigation (ps/top) and termination (TERM then KILL) plan with verification and service-manager notes."],
    },
    references: {
      troubleshooting: [
        "## Process won't die even with -KILL",
        "- 可能处于不可中断的 D 状态（IO 等待）或是僵尸进程（Z）；Z 需要处理父进程。",
        "",
        "## It keeps coming back",
        "- 可能被 systemd/supervisor 自动重启；应该停对应服务并检查重启策略。",
      ],
      edgeCases: ["- `kill -9` 可能导致数据损坏；仅在明确无更好方案时使用。", "- 终止 PID 前确认不要误杀同名但不同用途的进程。"],
      examples: ["```bash", "# Find top CPU users (ps) and terminate safely", "ps -eo pid,%cpu,%mem,cmd --sort=-%cpu | head", "kill -TERM <pid>", "```"],
    },
  },

  "process/background-nohup": {
    sources: [
      {
        label: "Arch man: nohup(1)",
        url: "https://man.archlinux.org/man/nohup.1.en.txt",
        summary: "nohup 忽略 SIGHUP，并重定向输出。",
        supports: "Steps 1",
      },
      {
        label: "GNU Bash manual: Job Control Builtins",
        url: "https://www.gnu.org/software/bash/manual/html_node/Job-Control-Builtins.html",
        summary: "jobs/bg/fg/disown 等作业控制内建命令。",
        supports: "Steps 2-3",
      },
      {
        label: "Arch man: bash(1)",
        url: "https://man.archlinux.org/man/bash.1.en.txt",
        summary: "bash 作业控制与相关内建命令概述。",
        supports: "Steps 2-3",
      },
    ],
    goal: ["把长任务放到后台并在断开 SSH 后仍持续运行：用 `nohup` + 重定向 + `&`，必要时用 `disown`。"],
    whenUse: ["需要跑一个耗时命令（下载/训练/备份）但不想一直占用终端", "SSH 连接不稳定，担心断线导致任务终止"],
    whenNot: ["任务需要可观测/可管理（优先 systemd/tmux/队列系统）", "你不确定任务是否会无限输出日志或占满磁盘（先设置日志策略）"],
    prerequisites: {
      environment: "Linux shell (bash/zsh)",
      permissions: "执行命令权限 + 写日志文件权限",
      tools: "`nohup`（可选）+ shell job control（`jobs`/`disown`）",
      inputs: "要运行的命令 + 输出日志路径",
    },
    steps: [
      { text: "直接后台运行并记录日志：`nohup <cmd> >out.log 2>&1 &`（注意把 stdout/stderr 都落盘）", cites: [1] },
      { text: "确认作业与 PID：`jobs -l`（或记录 `$!`）", cites: [2, 3] },
      { text: "可选：从 shell 作业表移除并避免 SIGHUP：`disown -h %<job>`", cites: [2, 3] },
      { text: "验证：`tail -n 50 out.log` 看任务是否持续输出；必要时通过 PID 确认仍在运行", cites: [1] },
    ],
    verification: ["断开并重连 SSH 后，任务仍在运行且日志持续增长", "任务完成后退出码/产物符合预期"],
    safety: {
      irreversible: "后台任务可能持续占用 CPU/内存/磁盘；错误脚本可能造成数据破坏",
      privacy: "日志可能包含敏感数据；限制日志权限并避免上传/公开",
      confirmation: "为后台任务设置明确输出文件与停止方式；生产环境优先用可管理的服务/作业系统",
    },
    library: {
      bash: [
        "nohup bash -lc 'long_task --arg value' > long_task.log 2>&1 &",
        "echo \"PID=$!\"",
        "jobs -l",
        "disown -h %1",
        "tail -n 50 long_task.log",
      ],
      prompt: ["Given a long-running command, output a nohup/disown backgrounding recipe with logging, PID capture, and a safe stop/verification suggestion."],
    },
    references: {
      troubleshooting: [
        "## No output appears in log",
        "- 程序可能缓冲输出；确认是否写到 stderr/stdout；必要时调整程序日志参数或用行缓冲工具。",
        "",
        "## Process dies after logout",
        "- 确认用了 nohup 或 disown；某些环境还需要 tmux/systemd 才能稳定托管。",
      ],
      edgeCases: ["- `disown` 是 shell 内建；不同 shell 行为略有差异。", "- `nohup` 默认输出到 `nohup.out`；建议显式重定向到你控制的日志文件。"],
      examples: ["```bash", "# Run a command with timestamped log", "nohup mycmd >\"run.$(date +%F_%H%M%S).log\" 2>&1 &", "```"],
    },
  },

  "process/tmux-session": {
    sources: [
      {
        label: "Arch man: tmux(1)",
        url: "https://man.archlinux.org/man/tmux.1.en.txt",
        summary: "tmux 会话/窗口/面板与常用命令。",
        supports: "Steps 1-5",
      },
      {
        label: "tmux wiki: Getting Started",
        url: "https://github.com/tmux/tmux/wiki/Getting-Started",
        summary: "tmux 基础概念与常用快捷键。",
        supports: "Steps 1-5",
      },
      {
        label: "Debian man: tmux(1)",
        url: "https://manpages.debian.org/bookworm/tmux/tmux.1.en.html",
        summary: "tmux man page（另一份镜像，便于交叉验证）。",
        supports: "Steps 1-5",
      },
    ],
    goal: ["用 `tmux` 创建可断线重连的终端会话：断开 SSH 后任务继续跑，回来再 attach。"],
    whenUse: ["需要在远端跑长任务/多窗口操作，但不想担心断线", "需要多个 pane 并行看日志/运行命令", "需要保留滚动缓冲并在里面搜索"],
    whenNot: ["你需要系统级托管/自启动（优先 systemd）", "你无法安装 tmux 或政策不允许（可退而用 screen/nohup）"],
    prerequisites: {
      environment: "Linux shell + tmux installed",
      permissions: "无（本地会话）",
      tools: "`tmux`",
      inputs: "会话名（可选）+ 你要跑的命令/任务",
    },
    steps: [
      { text: "新建会话：`tmux new -s <name>`（进入后开始执行你的命令）", cites: [1, 2, 3] },
      { text: "分离会话：按 `Ctrl-b d`（detach）", cites: [1, 2] },
      { text: "列出会话：`tmux ls`", cites: [1, 2, 3] },
      { text: "重新连接：`tmux attach -t <name>`", cites: [1, 2, 3] },
      { text: "常用操作：`Ctrl-b c` 新窗口，`Ctrl-b %` 垂直分屏，`Ctrl-b \"` 水平分屏", cites: [1, 2] },
    ],
    verification: ["detach 后 `tmux ls` 仍能看到会话", "重连后原窗口/任务仍在运行"],
    safety: {
      irreversible: "无（会话管理）",
      privacy: "tmux 会话中可能包含敏感输出；共享屏幕/录制前脱敏",
      confirmation: "退出 tmux 前确认任务状态；必要时在会话中记录日志文件位置",
    },
    library: {
      bash: ["tmux new -s work", "# inside tmux: run your command", "tmux ls", "tmux attach -t work"],
      prompt: ["Teach a user how to use tmux for remote work: create, detach, list, attach, and basic window/pane operations, with verification steps."],
    },
    references: {
      troubleshooting: [
        "## Can't attach: no sessions",
        "- 会话可能已退出；重新 `tmux new` 创建并在里面跑任务。",
        "",
        "## Keybindings don't work",
        "- 你的前缀键默认是 `Ctrl-b`；如果被改过，检查 `~/.tmux.conf`。",
      ],
      edgeCases: ["- 多人协作/共享会话需要额外配置与权限控制。", "- 远端系统资源较小，长时间开多个 pane 可能影响性能。"],
      examples: ["```bash", "# Create a tmux session and run a long task", "tmux new -s build", "```"],
    },
  },

  "system/system-info-uname-dmesg": {
    sources: [
      {
        label: "Arch man: uname(1)",
        url: "https://man.archlinux.org/man/uname.1.en.txt",
        summary: "uname 输出内核/架构等信息。",
        supports: "Steps 1",
      },
      {
        label: "Arch man: lsb_release(1)",
        url: "https://man.archlinux.org/man/lsb_release.1.en.txt",
        summary: "lsb_release 输出发行版信息（如果已安装）。",
        supports: "Steps 2",
      },
      {
        label: "Arch man: dmesg(1)",
        url: "https://man.archlinux.org/man/dmesg.1.en.txt",
        summary: "dmesg 查看内核环形缓冲（-T、过滤等）。",
        supports: "Steps 3-4",
      },
    ],
    goal: ["快速收集系统信息与启动/硬件相关日志：用 `uname`/`lsb_release` 标识系统，用 `dmesg` 定位内核级错误。"],
    whenUse: ["需要提交 bug report/排查环境差异（内核版本、架构、发行版）", "排查硬件/驱动/启动相关异常（dmesg）"],
    whenNot: ["日志包含敏感信息且你要发到公开渠道（先脱敏/只截取必要片段）"],
    prerequisites: {
      environment: "Linux shell",
      permissions: "读取 dmesg 在某些系统可能需要 sudo（取决于 dmesg_restrict）",
      tools: "`uname` / `dmesg`（可选 `lsb_release`）",
      inputs: "无（或你要排查的关键字：error/fail 等）",
    },
    steps: [
      { text: "确认内核与架构：`uname -a`（或更简洁 `uname -srmo`）", cites: [1] },
      { text: "确认发行版：`lsb_release -a`（若无该命令，可改用 `/etc/os-release`）", cites: [2] },
      { text: "查看最近内核日志：`dmesg -T | tail -n 200`（带人类可读时间）", cites: [3] },
      { text: "按关键字过滤：`dmesg -T | grep -i 'error\\|fail\\|warn' | tail -n 50`", cites: [3] },
    ],
    verification: ["把 uname/发行版信息与相关 dmesg 片段整理成问题描述，能复现/定位方向更明确"],
    safety: {
      irreversible: "无（只读）",
      privacy: "dmesg 可能包含设备序列号、路径、内核参数等；公开前脱敏",
      confirmation: "如需 sudo 查看 dmesg，先确认安全策略允许并避免把完整日志外发",
    },
    library: {
      bash: ["uname -srmo", "lsb_release -a || cat /etc/os-release", "dmesg -T | tail -n 200", "dmesg -T | grep -i 'error\\|fail\\|warn' | tail -n 50"],
      prompt: ["Given a Linux issue report request, output a minimal uname/lsb_release/dmesg collection checklist with privacy notes."],
    },
    references: {
      troubleshooting: [
        "## dmesg: Operation not permitted",
        "- 可能启用了 `dmesg_restrict`；用 sudo 或改用 `journalctl -k`（systemd 环境）。",
      ],
      edgeCases: ["- `lsb_release` 可能未安装；按发行版安装 lsb-release 包或改读 `/etc/os-release`。"],
      examples: ["```bash", "# Collect a small system info bundle", "uname -a; lsb_release -a 2>/dev/null; dmesg -T | tail -n 80", "```"],
    },
  },

  "system/resources-free-vmstat": {
    sources: [
      {
        label: "Arch man: free(1)",
        url: "https://man.archlinux.org/man/free.1.en.txt",
        summary: "free 查看内存使用（-h）。",
        supports: "Steps 1",
      },
      {
        label: "Arch man: vmstat(8)",
        url: "https://man.archlinux.org/man/vmstat.8.en.txt",
        summary: "vmstat 观察 CPU/内存/IO 统计（间隔与次数）。",
        supports: "Steps 2-3",
      },
      {
        label: "Arch man: iostat(1)",
        url: "https://man.archlinux.org/man/iostat.1.en.txt",
        summary: "iostat（sysstat）观察磁盘 IO（-x、-z 等）。",
        supports: "Steps 3",
      },
    ],
    goal: ["快速区分性能瓶颈来自 CPU、内存还是 IO：用 `free` 看内存，用 `vmstat` 看整体节奏，用 `iostat` 看磁盘。"],
    whenUse: ["机器变慢/延迟升高，需要先做资源层面诊断", "怀疑 swap 抖动或 IO 等待导致吞吐下降"],
    whenNot: ["你需要进程级别的根因（再结合 `top`/`ps`/`pidstat`）"],
    prerequisites: {
      environment: "Linux shell",
      permissions: "通常无需 sudo（iostat 需要 sysstat 包且可能需要权限读取部分统计）",
      tools: "`free` / `vmstat` / `iostat`",
      inputs: "采样间隔与次数（例如 1s * 5 次）",
    },
    steps: [
      { text: "内存概览：`free -h`（关注 available、swap）", cites: [1] },
      { text: "节奏采样：`vmstat 1 5`（看 r/b、si/so、wa 等）", cites: [2] },
      { text: "IO 采样：`iostat -xz 1 5`（看 util、await、svctm 等）", cites: [3] },
      { text: "结合判断：`wa` 高 + iostat await 高 → IO 瓶颈；`si/so` 高 → swap 压力；`r` 高 → CPU 竞争", cites: [2, 3] },
    ],
    verification: ["修复/扩容/限流后再次采样，指标改善且业务延迟恢复", "记录一份“问题时 vs 正常时”的采样对比用于复盘"],
    safety: {
      irreversible: "无（只读采样）",
      privacy: "输出包含主机资源信息；对外分享前确认合规",
      confirmation: "采样本身安全；但不要在高压时运行过重的诊断工具",
    },
    library: {
      bash: ["free -h", "vmstat 1 5", "iostat -xz 1 5"],
      prompt: ["Given a slow server symptom, produce a minimal free/vmstat/iostat triage with how-to-interpret bullets and a verification re-sample."],
    },
    references: {
      troubleshooting: ["## iostat not found", "- 需要安装 sysstat（发行版包名可能为 `sysstat`）。"],
      edgeCases: ["- 容器内看到的资源可能是 cgroup 视角；需要在宿主机对照采样。", "- 虚拟化环境 IO 指标可能受 hypervisor 影响。"],
      examples: ["```bash", "# Quick 10-second sampling", "vmstat 1 10", "iostat -xz 1 10", "```"],
    },
  },

  "systemd/systemctl-service-status": {
    sources: [
      {
        label: "Arch man: systemctl(1)",
        url: "https://man.archlinux.org/man/systemctl.1.en.txt",
        summary: "systemctl 管理 unit（status/start/stop/restart/enable/disable/--failed 等）。",
        supports: "Steps 1-6",
      },
      {
        label: "Arch man: systemd.service(5)",
        url: "https://man.archlinux.org/man/systemd.service.5.en.txt",
        summary: "service unit 文件语义（ExecStart、Restart 等）。",
        supports: "Steps 4",
      },
      {
        label: "Arch man: systemd.unit(5)",
        url: "https://man.archlinux.org/man/systemd.unit.5.en.txt",
        summary: "unit 基础概念与依赖关系（Wants/Requires/After 等）。",
        supports: "Steps 4",
      },
    ],
    goal: ["用 `systemctl` 查看服务状态、启动/停止/重启、设置自启，并在变更前后做最小验证。"],
    whenUse: ["服务启动失败/频繁重启，需要快速看 status 与原因", "需要在机器重启后保持服务自启", "做发布/变更后需要安全重启服务"],
    whenNot: ["你不确定这台机器的业务窗口且准备重启关键服务（先确认影响与回滚）"],
    prerequisites: {
      environment: "Linux with systemd",
      permissions: "通常需要 sudo/root 管理 systemd system units（用户级 unit 另说）",
      tools: "`systemctl`（可选 `journalctl` 配合看日志）",
      inputs: "unit 名称（例如 `nginx.service`）",
    },
    steps: [
      { text: "查看状态：`systemctl status <unit>`（关注 Active、Main PID、最近错误）", cites: [1] },
      { text: "启动/停止/重启：`systemctl start|stop|restart <unit>`（尽量选低峰期）", cites: [1] },
      { text: "重载配置（支持时）：`systemctl reload <unit>`（比 restart 更温和）", cites: [1] },
      { text: "设置自启：`systemctl enable --now <unit>`；取消：`systemctl disable --now <unit>`", cites: [1] },
      { text: "查看 unit 定义：`systemctl cat <unit>`；理解关键字段（ExecStart/Restart/依赖关系）", cites: [1, 2, 3] },
      { text: "看失败列表：`systemctl --failed`；按需 `reset-failed` 清理失败状态（谨慎）", cites: [1] },
    ],
    verification: ["`systemctl is-active <unit>` 为 active；`systemctl is-enabled <unit>` 符合预期", "对外服务用 curl/端口探测做一次端到端验证"],
    safety: {
      irreversible: "重启/停止关键服务会造成中断；错误的 enable/disable 会影响重启后行为",
      privacy: "status/journal 输出可能包含路径与参数；分享前脱敏",
      confirmation: "高风险操作（stop/restart/enable）前确认影响范围与回滚方案；优先 reload；生产环境需变更记录",
    },
    library: {
      bash: [
        "sudo systemctl status nginx",
        "sudo systemctl restart nginx",
        "sudo systemctl enable --now nginx",
        "sudo systemctl cat nginx",
        "sudo systemctl --failed",
      ],
      prompt: ["Given a systemd service issue, output a safe systemctl workflow: status -> (reload/restart) -> enable/disable -> verify. Include risk notes."],
    },
    references: {
      troubleshooting: [
        "## status shows exit-code / failed",
        "- 结合 `journalctl -u <unit>` 查看详细日志；检查 ExecStart、配置文件与依赖。",
        "",
        "## Service keeps restarting",
        "- 可能配置了 Restart=always/on-failure；先看 `systemctl cat <unit>`，再修复根因而不是一直重启。",
      ],
      edgeCases: ["- 用户级 unit（systemctl --user）与系统级 unit 行为不同；权限与路径也不同。", "- 修改 unit 文件后需要 `systemctl daemon-reload` 才生效（谨慎）。"],
      examples: ["```bash", "# Quick triage", "sudo systemctl status myapp", "sudo systemctl restart myapp", "sudo systemctl is-active myapp", "```"],
    },
  },

  "systemd/journalctl-logs": {
    sources: [
      {
        label: "Arch man: journalctl(1)",
        url: "https://man.archlinux.org/man/journalctl.1.en.txt",
        summary: "journalctl 按 unit/时间/boot/级别过滤，并支持 follow 与不同输出格式。",
        supports: "Steps 1-6",
      },
      {
        label: "Arch man: systemd-journald(8)",
        url: "https://man.archlinux.org/man/systemd-journald.8.en.txt",
        summary: "journald 的存储/持久化/限制相关说明。",
        supports: "Steps 6",
      },
      {
        label: "systemd docs: journalctl",
        url: "https://www.freedesktop.org/software/systemd/man/journalctl.html",
        summary: "journalctl 官方文档（补充示例与选项）。",
        supports: "Steps 1-6",
      },
    ],
    goal: ["用 `journalctl` 快速定位 systemd 管理服务/系统的日志：按 unit、时间、boot、优先级过滤，并支持实时跟随。"],
    whenUse: ["服务异常需要看日志（结合 systemctl status）", "排查启动后某个时间窗口的错误/警告", "需要抓取日志作为问题证据（注意脱敏）"],
    whenNot: ["日志包含敏感信息且你要直接公开（先脱敏/裁剪）"],
    prerequisites: {
      environment: "Linux with systemd",
      permissions: "读取系统日志可能需要 sudo 或加入 systemd-journal 组（发行版不同）",
      tools: "`journalctl`",
      inputs: "unit 名称 + 时间范围（可选）",
    },
    steps: [
      { text: "按服务看日志：`journalctl -u <unit> --no-pager`", cites: [1, 3] },
      { text: "实时跟随：`journalctl -u <unit> -f`", cites: [1, 3] },
      { text: "按时间窗口：`journalctl -u <unit> --since '1 hour ago' --until 'now'`", cites: [1, 3] },
      { text: "按 boot：`journalctl -b`（本次启动）或 `journalctl -b -1`（上次启动）", cites: [1, 3] },
      { text: "按优先级：`journalctl -p warning..err -u <unit>`（聚焦警告/错误）", cites: [1, 3] },
      { text: "输出格式：`-o short-iso` 或 `-o json-pretty`；必要时了解 journald 存储策略", cites: [1, 2, 3] },
    ],
    verification: ["能在日志中定位到报错时间点与关键堆栈/错误码，并与 status 对应", "修复后再次 follow，确认错误不再出现"],
    safety: {
      irreversible: "无（只读）",
      privacy: "日志可能包含凭据、用户数据、路径；导出/分享前脱敏",
      confirmation: "避免在公开渠道粘贴完整日志；只截取必要窗口并去标识化",
    },
    library: {
      bash: [
        "sudo journalctl -u nginx --since '2 hours ago' --no-pager | tail -n 200",
        "sudo journalctl -u nginx -f",
        "sudo journalctl -p warning..err -u nginx --since today --no-pager",
      ],
      prompt: ["Given a failing systemd service, output the best journalctl commands to get recent errors, follow live logs, and narrow by time/priority."],
    },
    references: {
      troubleshooting: [
        "## No logs shown",
        "- 可能没有权限；用 sudo 或加入日志读取组；确认服务是否真的写入 journald。",
        "",
        "## Logs rotated / missing",
        "- 检查 journald 的持久化设置与容量限制；必要时调整配置并重启 journald（需谨慎）。",
      ],
      edgeCases: ["- 容器/最小系统可能不使用 journald；需要改用文件日志。", "- `--since` 的解析依实现而定；不确定时用明确时间戳（ISO）。"],
      examples: ["```bash", "# Kernel logs for this boot", "sudo journalctl -k -b --no-pager | tail -n 200", "```"],
    },
  },

  "scheduling/cron-basics": {
    sources: [
      {
        label: "Arch man: crontab(1)",
        url: "https://man.archlinux.org/man/crontab.1.en.txt",
        summary: "crontab 管理用户定时任务（-e/-l/-r）。",
        supports: "Steps 1,5",
      },
      {
        label: "Arch man: crontab(5)",
        url: "https://man.archlinux.org/man/crontab.5.en.txt",
        summary: "crontab 文件格式（时间字段、环境变量、特殊字符串）。",
        supports: "Steps 2-4",
      },
      {
        label: "Arch man: crond(8)",
        url: "https://man.archlinux.org/man/crond.8.en.txt",
        summary: "cron 守护进程与执行环境说明。",
        supports: "Steps 2-4",
      },
    ],
    goal: ["用 `crontab` 安全地配置定时任务：理解最小环境差异、用绝对路径、记录日志，并验证任务确实在跑。"],
    whenUse: ["周期性任务（备份、清理、同步、健康检查）", "临时自动化但不想引入更重的调度系统"],
    whenNot: ["需要依赖复杂环境/密钥管理/失败重试（优先 systemd timers/队列系统）", "任务有高风险写操作且没有回滚/审计策略"],
    prerequisites: {
      environment: "Linux with cron daemon",
      permissions: "编辑自己 crontab；系统级任务需要 sudo/root",
      tools: "`crontab`",
      inputs: "任务命令（建议可重入）+ 计划时间 + 日志输出位置",
    },
    steps: [
      { text: "编辑/查看：`crontab -e` 写入任务；用 `crontab -l` 确认生效", cites: [1] },
      { text: "写任务时用绝对路径，并明确 shell/环境：必要时在 crontab 顶部设置 `SHELL=/bin/bash`、`PATH=...`", cites: [2, 3] },
      { text: "先手动跑命令确认无误，再写入计划表达式：`*/5 * * * * /usr/local/bin/job ...`", cites: [2] },
      { text: "记录日志并避免无上限增长：`... >>/var/log/job.log 2>&1`（配合 logrotate）", cites: [2, 3] },
      { text: "验证：等待一个周期后用 `crontab -l` + 查看日志确认任务确实执行", cites: [1] },
    ],
    verification: ["日志中出现周期性执行记录，且退出码/产物符合预期", "任务在重启后仍按计划执行（如需要）"],
    safety: {
      irreversible: "cron 会自动反复执行；错误任务可能造成持续破坏（删文件、占满磁盘、刷爆接口）",
      privacy: "日志可能包含敏感参数；避免把 secret 写进 crontab（用受控配置/环境）",
      confirmation: "上线前先在测试机/小范围验证；高风险任务加入锁/幂等保护并保留回滚方案",
    },
    library: {
      bash: [
        "crontab -l",
        "crontab -e",
        "# Example line (every 5 minutes):",
        "# */5 * * * * /usr/local/bin/job >>/var/log/job.log 2>&1",
      ],
      prompt: ["Given a command and schedule, write a safe crontab entry including PATH/SHELL notes, logging, and verification steps."],
    },
    references: {
      troubleshooting: [
        "## Works in shell but not in cron",
        "- cron 的 PATH/环境变量更少；使用绝对路径并显式设置 PATH；把 stderr 重定向到日志排查。",
        "",
        "## Job runs too often / wrong timezone",
        "- 检查表达式字段与系统时区；必要时在日志里打印时间戳确认。",
      ],
      edgeCases: ["- 避免在 crontab 里直接写密钥；用受限权限的配置文件或专用 secret 管理。", "- 并发风险：周期短的任务可能重叠执行，需要加锁。"],
      examples: ["```bash", "# Run daily at 02:30 and log", "# 30 2 * * * /usr/local/bin/backup >>/var/log/backup.log 2>&1", "```"],
    },
  },

  "packages/package-manager-basics": {
    sources: [
      {
        label: "Debian man: apt-get(8)",
        url: "https://manpages.debian.org/bookworm/apt/apt-get.8.en.html",
        summary: "apt-get 更新索引、安装/升级/删除、模拟运行等。",
        supports: "Steps 2-5",
      },
      {
        label: "DNF docs: command reference",
        url: "https://dnf.readthedocs.io/en/latest/command_ref.html",
        summary: "dnf install/upgrade/remove/downgrade 等命令参考。",
        supports: "Steps 2-5",
      },
      {
        label: "Arch man: pacman(8)",
        url: "https://man.archlinux.org/man/pacman.8.en.txt",
        summary: "pacman 搜索/安装/升级/移除与缓存包管理。",
        supports: "Steps 2-6",
      },
    ],
    goal: ["在不同发行版上安全管理软件包（apt/dnf/pacman）：先预览变更，再安装/升级/删除，并保留回滚路径。"],
    whenUse: ["需要安装缺失工具或安全更新", "需要升级某个依赖并验证兼容性", "需要卸载冲突包或清理旧版本"],
    whenNot: ["生产环境临时升级且没有维护窗口/回滚方案（高风险）"],
    prerequisites: {
      environment: "Linux（不同发行版包管理器不同）",
      permissions: "通常需要 sudo/root",
      tools: "`apt-get` 或 `dnf` 或 `pacman`",
      inputs: "包名（可选版本）+ 期望动作（install/upgrade/remove）",
    },
    steps: [
      { text: "识别包管理器：Debian/Ubuntu 用 apt；RHEL/Fedora 用 dnf；Arch 用 pacman（按系统选择对应命令）", cites: [1, 2, 3] },
      { text: "刷新索引：apt `sudo apt-get update`；dnf `sudo dnf makecache`；pacman `sudo pacman -Syu`（避免只 -Sy）", cites: [1, 2, 3] },
      { text: "安装包：apt `sudo apt-get install <pkg>`；dnf `sudo dnf install <pkg>`；pacman `sudo pacman -S <pkg>`", cites: [1, 2, 3] },
      { text: "升级：apt `sudo apt-get upgrade`/`dist-upgrade`；dnf `sudo dnf upgrade`；pacman `sudo pacman -Syu`", cites: [1, 2, 3] },
      { text: "卸载：apt `remove/purge`；dnf `remove`；pacman `-R/-Rns`（谨慎清依赖）", cites: [1, 2, 3] },
      { text: "回滚思路：apt 指定版本安装；dnf `downgrade`；pacman 用缓存包 `pacman -U /var/cache/pacman/pkg/...`", cites: [1, 2, 3] },
    ],
    verification: ["确认目标包版本：`<tool> --version` 或查询包信息（apt-cache/dnf info/pacman -Qi）", "运行依赖该包的服务/脚本做一次冒烟测试"],
    safety: {
      irreversible: "升级/移除可能引入依赖变更导致服务不可用；回滚不一定总能成功",
      privacy: "无（但在工单里避免暴露内部仓库地址与 token）",
      confirmation: "生产环境变更前必须预览要安装/删除的包列表并确认维护窗口；高风险变更保留回滚包/快照",
    },
    library: {
      bash: [
        "# Debian/Ubuntu",
        "sudo apt-get update",
        "sudo apt-get install curl",
        "",
        "# Fedora/RHEL",
        "sudo dnf makecache",
        "sudo dnf install curl",
        "",
        "# Arch",
        "sudo pacman -Syu",
        "sudo pacman -S curl",
      ],
      prompt: ["Given a distro family and a desired package action, output safe package-manager commands with a preview/verification step and rollback notes."],
    },
    references: {
      troubleshooting: [
        "## Dependency conflicts / broken packages",
        "- 不要强行卸载关键依赖；先查看冲突链路并按发行版推荐方式修复（可能需要完整升级/同步）。",
        "",
        "## Mirrors/repo unreachable",
        "- 换镜像或检查代理/DNS；避免在网络不稳定时做大升级。",
      ],
      edgeCases: ["- pacman 需要全量同步升级（-Syu）避免部分升级。", "- 企业环境可能有私有仓库与审计要求；遵循内部流程。"],
      examples: ["```bash", "# Simulate apt changes (preview) then apply", "sudo apt-get -s upgrade | head", "sudo apt-get upgrade", "```"],
    },
  },

  "users/user-group-management": {
    sources: [
      {
        label: "Arch man: useradd(8)",
        url: "https://man.archlinux.org/man/useradd.8.en.txt",
        summary: "useradd 创建用户（-m/-s 等）。",
        supports: "Steps 2",
      },
      {
        label: "Arch man: usermod(8)",
        url: "https://man.archlinux.org/man/usermod.8.en.txt",
        summary: "usermod 修改用户（-aG 等）。",
        supports: "Steps 4-5",
      },
      {
        label: "Arch man: groupadd(8)",
        url: "https://man.archlinux.org/man/groupadd.8.en.txt",
        summary: "groupadd 创建用户组。",
        supports: "Steps 3",
      },
      {
        label: "Arch man: id(1)",
        url: "https://man.archlinux.org/man/id.1.en.txt",
        summary: "id 查看用户/组信息（验证用）。",
        supports: "Steps 1,6",
      },
    ],
    goal: ["安全地创建/修改用户与用户组：用 useradd/usermod/groupadd 管理账号，用 id 验证组成员关系（含 sudo 组）。"],
    whenUse: ["新建服务账号/开发账号", "给现有用户追加组权限（例如读日志组、docker 组）", "排查权限问题时确认用户实际组列表"],
    whenNot: ["你准备给用户加 sudo/管理员权限但未走审批（高风险）"],
    prerequisites: {
      environment: "Linux shell",
      permissions: "通常需要 sudo/root",
      tools: "`useradd` / `usermod` / `groupadd` / `id`（可选 `passwd`）",
      inputs: "用户名 + 需要加入的组（是否需要 sudo）",
    },
    steps: [
      { text: "检查现有用户/组：`id <user>`（确认当前 groups）", cites: [4] },
      { text: "创建用户：`sudo useradd -m -s /bin/bash <user>`（-m 创建 home）", cites: [1] },
      { text: "创建组（如需要）：`sudo groupadd <group>`", cites: [3] },
      { text: "把用户加入附加组：`sudo usermod -aG <group> <user>`（不要漏 -a）", cites: [2] },
      { text: "需要 sudo 权限时：加入发行版的 admin 组（常见是 `sudo` 或 `wheel`）并遵循最小授权原则", cites: [2] },
      { text: "验证：重新 `id <user>`；必要时让用户重新登录使组变更生效", cites: [4] },
    ],
    verification: ["`id <user>` 显示期望的 groups", "以该用户实际执行一次目标操作（读写目录/运行命令）验证权限已生效"],
    safety: {
      irreversible: "给错组（尤其 sudo/wheel）会造成越权；删除/修改用户可能影响服务与数据所有权",
      privacy: "账号信息属于敏感资产；公开记录时避免暴露内部用户名规则",
      confirmation: "涉及 sudo/wheel 必须审批；变更前后记录 `id` 输出与变更原因；避免直接改现网关键账号",
    },
    library: {
      bash: ["sudo useradd -m -s /bin/bash appuser", "sudo groupadd developers", "sudo usermod -aG developers appuser", "id appuser"],
      prompt: ["Given a username and required access, output a safe user/group management plan, highlighting sudo/wheel risks and including verification with id."],
    },
    references: {
      troubleshooting: [
        "## Group change not effective",
        "- 用户需要重新登录/重新打开 shell；或使用 `newgrp` 临时切换。",
        "",
        "## Can't switch user / no home",
        "- 创建用户时确保 `-m`；并检查 shell 是否存在（-s）。",
      ],
      edgeCases: ["- 不同发行版的 admin 组不同（sudo vs wheel）；按系统策略选择。", "- 服务账号通常不应允许交互登录；需要时设置更严格的 shell/权限。"],
      examples: ["```bash", "# Add a user to docker group (example)", "sudo usermod -aG docker alice", "id alice", "```"],
    },
  },

  "security/sudoers-best-practice": {
    sources: [
      {
        label: "Arch man: sudoers(5)",
        url: "https://man.archlinux.org/man/sudoers.5.en.txt",
        summary: "sudoers 语法、用户/组规则、include 与安全选项。",
        supports: "Steps 2-4",
      },
      {
        label: "Arch man: visudo(8)",
        url: "https://man.archlinux.org/man/visudo.8.en.txt",
        summary: "visudo 安全编辑 sudoers（语法检查、锁）。",
        supports: "Steps 1-2",
      },
      {
        label: "Arch man: sudo(8)",
        url: "https://man.archlinux.org/man/sudo.8.en.txt",
        summary: "sudo 用法、`sudo -l` 列出授权命令等。",
        supports: "Steps 3-4",
      },
    ],
    goal: ["用 `visudo` 安全管理 sudo 授权：最小权限、可审计、避免把系统锁死或引入特权升级路径。"],
    whenUse: ["需要让某个用户/组执行少量管理命令（最小授权）", "需要为运维脚本配置受限 sudo 权限并可审计"],
    whenNot: ["你准备给人/脚本加 ALL=(ALL) NOPASSWD:ALL（极高风险）", "你不确定 sudoers 语法且没有恢复通道（先在测试机验证）"],
    prerequisites: {
      environment: "Linux with sudo installed",
      permissions: "需要已有管理员权限（root 或现有 sudo）",
      tools: "`visudo` / `sudo`",
      inputs: "要授权的用户/组 + 允许的命令列表（尽量写绝对路径）",
    },
    steps: [
      { text: "永远用 visudo 修改：`sudo visudo`；或写单独文件：`sudo visudo -f /etc/sudoers.d/<name>`", cites: [2] },
      { text: "按最小权限写规则：限定到具体命令的绝对路径（避免通配/编辑器/解释器）", cites: [1] },
      { text: "验证授权：`sudo -l -U <user>` 查看该用户可执行的 sudo 命令", cites: [3] },
      { text: "上线前做一次实测：用目标用户执行被允许的命令；确保“未授权命令”仍被拒绝", cites: [1, 3] },
    ],
    verification: ["`sudo -l -U <user>` 输出符合预期且无多余权限", "目标用户能执行被允许的命令、不能执行未允许的命令"],
    safety: {
      irreversible: "错误 sudoers 可能导致你无法 sudo（锁死）或造成特权提升；NOPASSWD 可能被滥用",
      privacy: "sudoers 规则可能暴露内部路径/账号；分享前脱敏",
      confirmation: "任何新增 sudo 权限必须审批+审计；高风险变更保留恢复通道（root 控制台/救援模式）",
    },
    library: {
      bash: [
        "sudo visudo -f /etc/sudoers.d/deploy",
        "sudo -l -U deploy",
      ],
      prompt: ["Given a required admin task, write a least-privilege sudoers rule using visudo, and include verification commands. Warn about dangerous patterns."],
    },
    references: {
      troubleshooting: [
        "## visudo reports a syntax error",
        "- 不要强行保存；修正语法后再保存。必要时回退到上一份可用配置。",
        "",
        "## User still prompted for password",
        "- 检查是否需要 NOPASSWD（谨慎）；也可能是规则匹配不到（命令路径不一致）。",
      ],
      edgeCases: ["- 避免允许编辑器/解释器（vim/python/bash）等可逃逸到 root shell 的命令。", "- 规则里尽量写绝对路径；不同发行版命令路径可能不同。"],
      examples: [
        "```bash",
        "# Example sudoers.d snippet (edit with visudo)",
        "# deploy ALL=(root) NOPASSWD: /usr/bin/systemctl restart myapp.service",
        "```",
      ],
    },
  },
};

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

async function captureLinuxSkill({
  topic,
  slug,
  title,
  riskLevel,
  cacheDir,
  timeoutMs,
  log = true,
  strict = false,
  sourcePolicy = null,
}) {
  const key = `${topic}/${slug}`;
  const spec = LINUX_CAPTURE_SPECS[key];
  if (!spec) {
    if (strict) throw new Error(`No capture spec for linux/${key}`);
    return null;
  }

  if (sourcePolicy) {
    for (const s of Array.isArray(spec.sources) ? spec.sources : []) {
      if (!isUrlAllowed(s.url, sourcePolicy)) {
        throw new Error(`[source_policy] blocked URL for linux/${key}: ${s.url}`);
      }
    }
  }

  const accessed = utcDate();
  const sources = await fetchSourcesWithEvidence(spec.sources, cacheDir, timeoutMs, log);

  return {
    skillMd: renderSkillMd({ title, riskLevel, spec, sources }),
    libraryMd: renderLibraryMd(spec),
    sourcesMd: renderReferenceSourcesMd(sources, accessed),
    troubleshootingMd: renderReferenceTroubleshootingMd(spec),
    edgeCasesMd: renderReferenceEdgeCasesMd(spec),
    examplesMd: renderReferenceExamplesMd(spec),
    changelogMd: renderReferenceChangelogMd(accessed, key),
  };
}

module.exports = { captureLinuxSkill };
