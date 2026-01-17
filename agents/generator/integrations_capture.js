/* eslint-disable no-console */

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const { getRepoUrlLicenseMap, lookupLicenseForUrl, loadUrlLicensePairsFromSourcesMd } = require("./license_lookup");

const REPO_ROOT = path.resolve(__dirname, "..", "..");

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
  if (typeof fetch !== "function") throw new Error("Global fetch() not available. Use Node.js 18+.");

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
  const licenseMap = getRepoUrlLicenseMap(REPO_ROOT);
  const fetched = [];
  for (const s of Array.isArray(sources) ? sources : []) {
    const rawLicense = s && s.license ? String(s.license).trim() : "";
    const resolvedLicense = rawLicense || lookupLicenseForUrl(s && s.url ? s.url : "", licenseMap) || "";

    const r = await fetchWithCache(s.url, cacheDir, timeoutMs, log);
    fetched.push({
      ...s,
      license: resolvedLicense || "unknown",
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
  const body = Array.isArray(spec.references && spec.references.troubleshooting)
    ? spec.references.troubleshooting
    : ["(none)"];
  return joinLines(["# Troubleshooting", "", ...body, ""]);
}

function renderReferenceEdgeCasesMd(spec) {
  const body = Array.isArray(spec.references && spec.references.edgeCases) ? spec.references.edgeCases : ["(none)"];
  return joinLines(["# Edge cases", "", ...body, ""]);
}

function renderReferenceExamplesMd(spec) {
  const body = Array.isArray(spec.references && spec.references.examples) ? spec.references.examples : ["(none)"];
  return joinLines(["# Examples", "", ...body, ""]);
}

function renderReferenceChangelogMd(accessed, key) {
  return joinLines(["# Changelog", "", `- ${accessed}: generated by agents/run_local.js --capture (${key})`, ""]);
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

const INTEGRATIONS_CAPTURE_SPECS = {
  "slack/incoming-webhooks": {
    sources: [
      {
        label: "Slack API - Incoming Webhooks",
        url: "https://api.slack.com/messaging/webhooks",
        summary: "Slack Incoming Webhooks 的基本概念、创建方式、请求格式与示例。",
        supports: "Steps 1-5, 8",
        license: "unknown",
      },
      {
        label: "Slack API - Sending messages",
        url: "https://api.slack.com/messaging/sending",
        summary: "Slack 发送消息的常用格式与注意事项（payload、blocks、错误与限制等）。",
        supports: "Steps 5-7",
        license: "unknown",
      },
      {
        label: "Slack API - OAuth & Permissions (security context)",
        url: "https://api.slack.com/authentication",
        summary: "Slack 认证/权限的基础说明，用于强调凭证/URL 等敏感信息的安全边界。",
        supports: "Steps 2-4, 8",
        license: "unknown",
      },
    ],
    goal: ["用 Incoming Webhooks 安全地向 Slack channel 发送消息，并避免凭证泄露与误发。"],
    whenUse: [
      "需要从脚本/CI/服务端快速发送通知到 Slack",
      "不需要用户交互，也不想引入完整的 bot token 流程",
    ],
    whenNot: [
      "需要以用户身份操作或读取数据（应使用 OAuth + Web API）",
      "Webhook URL 可能被泄露且你无法及时轮转（先补齐密钥管理）",
    ],
    prerequisites: {
      environment: "能发起 HTTPS 请求的环境（本地 shell / CI / 后端服务均可）",
      permissions: "有权限在目标 Slack workspace 安装/配置 app 或创建 webhook",
      tools: "`curl`（可选，用于快速测试）",
      inputs: "Webhook URL、目标 channel（由 Slack 配置决定）、消息文本或 blocks payload",
    },
    steps: [
      { text: "确认消息目标与使用方式：只做通知（webhook）还是需要更复杂能力（Web API/OAuth）。", cites: [2, 3] },
      { text: "在 Slack 中创建/获取 Incoming Webhook，并拿到 webhook URL（不要在聊天/工单里明文传播）。", cites: [1, 3] },
      { text: "把 webhook URL 存到密钥管理（CI secret / 环境变量），避免写进仓库与日志。", cites: [3] },
      {
        text: "先做最小化联通测试：`curl -X POST -H 'Content-type: application/json' --data '{\"text\":\"hello\"}' \"$SLACK_WEBHOOK_URL\"`",
        cites: [1],
      },
      { text: "需要富文本时，用 blocks 组装 payload（先在小范围 channel 验证格式与展示）。", cites: [2] },
      { text: "处理失败与限流：记录 HTTP 状态码；遇到 429/失败时做指数退避重试并告警。", cites: [2] },
      { text: "对消息做最小必要内容输出：避免把敏感信息（token/PII/内部链接）推送到公共 channel。", cites: [2, 3] },
      { text: "如果怀疑泄露或滥用，立即轮转 webhook（重新生成并替换 secret），并回收旧 URL。", cites: [1, 3] },
    ],
    verification: [
      "Slack channel 中出现预期消息（文本/blocks 渲染正确）",
      "失败场景能在日志中定位（状态码/响应体/重试次数），且不会打印 webhook URL 明文",
    ],
    safety: {
      irreversible: "向错误的 channel 发送消息可能造成信息泄露；泄露 webhook URL 可能导致滥发消息",
      privacy: "不要把 webhook URL、token、PII 写入 repo/日志/截图；避免在公共 channel 推送敏感内容",
      confirmation: "先在测试/私有 channel 做 dry-run，再切换到生产 channel；上线前做一次泄露风险检查",
    },
    library: {
      bash: [
        "# Set your webhook URL via env var (do NOT commit it)",
        "export SLACK_WEBHOOK_URL='https://hooks.slack.com/services/.../.../...'",
        "",
        "# Minimal message",
        "curl -X POST -H 'Content-type: application/json' --data '{\"text\":\"hello\"}' \"$SLACK_WEBHOOK_URL\"",
        "",
        "# Blocks example (keep it small; validate in a test channel first)",
        "curl -X POST -H 'Content-type: application/json' --data '{\"blocks\":[{\"type\":\"section\",\"text\":{\"type\":\"mrkdwn\",\"text\":\"*Build* succeeded\"}}]}' \"$SLACK_WEBHOOK_URL\"",
      ],
      prompt: [
        "You are an integration engineer. Write a safe plan to send Slack notifications via Incoming Webhooks.",
        "Constraints:",
        "- Do not paste webhook URLs or tokens in output.",
        "- Provide steps <= 12 with a verification step.",
        "- Include a brief security note on secret storage and rotation.",
      ],
    },
    references: {
      troubleshooting: [
        "## 4xx / 5xx from Slack",
        "- 确认 webhook URL 是否有效、是否指向正确 workspace/channel。",
        "- 检查 payload 是否为有效 JSON，且 `Content-type: application/json` 已设置。",
        "",
        "## 429 rate limited",
        "- 做指数退避重试；在 CI/批量通知场景增加聚合与降噪。",
      ],
      edgeCases: [
        "- 不同 channel 的可见性不同（public/private）；避免把敏感通知发送到 public channel。",
        "- blocks 结构复杂时，建议先在测试 channel 逐步迭代 payload。",
      ],
      examples: [
        "```bash",
        "# Send a CI summary",
        "curl -X POST -H 'Content-type: application/json' --data '{\"text\":\"CI: ✅ tests passed\"}' \"$SLACK_WEBHOOK_URL\"",
        "```",
      ],
    },
  },
  "github/create-issue-rest-api": {
    sources: [
      {
        label: "GitHub docs: REST API - Create an issue",
        url: "https://docs.github.com/en/rest/issues/issues?apiVersion=2022-11-28#create-an-issue",
        summary: "创建 issue 的 REST API 端点、请求体字段与响应结构说明。",
        supports: "Steps 3-4, 7",
        license: "unknown",
      },
      {
        label: "GitHub docs: Managing your personal access tokens",
        url: "https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens",
        summary: "token 创建、存储与安全实践（最小权限、轮转与泄露风险）。",
        supports: "Steps 1-2, 4-5, 8",
        license: "unknown",
      },
      {
        label: "GitHub docs: Rate limits for the REST API",
        url: "https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api",
        summary: "REST API 的速率限制说明与响应头字段（用于退避重试策略）。",
        supports: "Steps 6",
        license: "unknown",
      },
    ],
    goal: ["用 GitHub REST API 安全创建 issue，并确保 token 最小权限且不泄露。"],
    whenUse: [
      "需要从脚本/CI/服务端把事件写入 GitHub issue（告警、审计、例行任务等）",
      "想先用 curl 验证最小可行，再接入 SDK/服务化",
    ],
    whenNot: [
      "需要复杂交互或大规模批量写入（更适合 SDK + 幂等 + 重试封装）",
      "无法安全保管 token（先补齐 secret 管理与访问控制）",
    ],
    prerequisites: {
      environment: "能访问 `api.github.com` 的环境",
      permissions: "对目标仓库有创建 issue 权限",
      tools: "`curl`（或任意 HTTP 客户端）",
      inputs: "`owner/repo`、issue 标题/正文、token 的安全存储方式",
    },
    steps: [
      {
        text: "准备最小权限 token（PAT/细粒度 token），并存入密钥管理或环境变量；不要写进仓库或日志。",
        cites: [2],
      },
      { text: "确认目标仓库与创建权限：`owner/repo` 正确，且 token 能访问该仓库。", cites: [2] },
      { text: "构造创建 issue 请求：对 `POST /repos/{owner}/{repo}/issues` 提供 `title`（可选 `body/labels/assignees`）。", cites: [1] },
      {
        text: "用 curl 发送请求（示例）：`curl -sS -X POST -H \"Authorization: Bearer $GITHUB_TOKEN\" -H \"Accept: application/vnd.github+json\" https://api.github.com/repos/<owner>/<repo>/issues -d '{\"title\":\"...\"}'`",
        cites: [1, 2],
      },
      { text: "处理失败：检查 HTTP 状态码与响应体；对 401/403 优先排查 token 权限与仓库可见性。", cites: [2] },
      { text: "处理速率限制：对 403/429 场景读取 rate limit 响应头，并做退避重试。", cites: [3] },
      { text: "做幂等：用 run-id/去重键避免重试导致重复 issue（必要时先搜索后创建）。", cites: [1] },
      { text: "验收：确认 issue 创建成功且字段正确；同时确认日志中没有泄露 token。", cites: [2] },
    ],
    verification: [
      "issue 在目标仓库中可见，标题/正文/标签符合预期",
      "失败场景（权限不足/速率限制）能在日志中定位原因",
      "任意日志/输出中不包含 token 明文",
    ],
    safety: {
      irreversible: "创建 issue 会写入仓库历史；自动化重试可能造成重复 issue（需幂等）",
      privacy: "token 属于高敏感凭证；禁止打印、禁止提交；及时轮转与最小权限",
      confirmation: "先在测试仓库验证，再对生产仓库启用；上线前做一次日志脱敏检查",
    },
    library: {
      bash: [
        "# Store token securely (example: env var in your shell/CI secret)",
        "export GITHUB_TOKEN='***'",
        "",
        "# Create an issue",
        "OWNER='<owner>'",
        "REPO='<repo>'",
        "",
        "curl -sS -X POST \\",
        "  -H \"Authorization: Bearer $GITHUB_TOKEN\" \\",
        "  -H \"Accept: application/vnd.github+json\" \\",
        "  \"https://api.github.com/repos/${OWNER}/${REPO}/issues\" \\",
        "  -d '{\"title\":\"Automation report\",\"body\":\"Created by a script. (Do not paste tokens here)\"}'",
      ],
      prompt: [
        "You are an automation engineer. Write a safe workflow to create a GitHub issue via the REST API.",
        "Constraints:",
        "- Never print tokens.",
        "- Include idempotency guidance and rate-limit handling.",
        "- Steps <= 12 with verification.",
      ],
    },
    references: {
      troubleshooting: [
        "## 401 Unauthorized",
        "- 检查：token 是否正确注入（环境变量/secret）、是否过期/已撤销。",
        "- 处理：重新生成并轮转 token；确认请求头使用 `Authorization: Bearer ...`。",
        "",
        "## 403 Forbidden",
        "- 检查：token 权限是否足够、仓库是否私有、是否触发 rate limit。",
        "- 处理：补齐最小权限；若是速率限制则按响应头做退避。",
        "",
        "## 重复创建 issue",
        "- 处理：在标题/正文加入 run-id；或先搜索已有 issue 再决定创建（幂等）。",
      ],
      edgeCases: [
        "- 对私有仓库：确保 token 授权范围覆盖目标 repo，并避免在公开日志打印 repo URL + token。",
        "- 对高频告警：建议做聚合/降噪，避免触发 rate limit 或造成 issue 噪音。",
      ],
      examples: [
        "```bash",
        "# Create a simple issue (replace owner/repo)",
        "curl -sS -X POST -H \"Authorization: Bearer $GITHUB_TOKEN\" -H \"Accept: application/vnd.github+json\" \\",
        "  https://api.github.com/repos/<owner>/<repo>/issues -d '{\"title\":\"hello\"}'",
        "```",
      ],
    },
  },
};

async function captureIntegrationsSkill({
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
  const spec = INTEGRATIONS_CAPTURE_SPECS[key];
  if (!spec) {
    if (strict) throw new Error(`No capture spec for integrations/${key}`);
    return null;
  }

  const specSources = Array.isArray(spec.sources) ? spec.sources : [];
  const canonicalPath = path.join(REPO_ROOT, "skills", "integrations", topic, slug, "reference", "sources.md");
  const canonicalPairs = loadUrlLicensePairsFromSourcesMd(canonicalPath);
  const sourcesInput =
    canonicalPairs.length >= specSources.length
      ? specSources.map((s, i) => {
        const c = canonicalPairs[i] || {};
        return {
          ...s,
          url: c.url || s.url,
          license: c.license || s.license,
        };
      })
      : specSources;

  if (sourcePolicy) {
    for (const s of sourcesInput) {
      if (!isUrlAllowed(s.url, sourcePolicy)) {
        throw new Error(`[source_policy] blocked URL for integrations/${key}: ${s.url}`);
      }
    }
  }

  const accessed = utcDate();
  const sources = await fetchSourcesWithEvidence(sourcesInput, cacheDir, timeoutMs, log);
  if (strict) {
    for (const s of Array.isArray(sources) ? sources : []) {
      const lic = String(s && s.license ? s.license : "").trim();
      if (!lic || /^unknown\b/i.test(lic)) {
        throw new Error(`[license] missing license mapping for integrations/${key}: ${s && s.url ? s.url : ""}`);
      }
    }
  }

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

module.exports = { captureIntegrationsSkill };
