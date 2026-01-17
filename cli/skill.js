#!/usr/bin/env node
/* eslint-disable no-console */

const fs = require("fs");
const path = require("path");
const childProcess = require("child_process");
const os = require("os");

process.stdout.on("error", (err) => {
  if (err && err.code === "EPIPE") process.exit(0);
});

function normalizeBaseUrl(url) {
  let v = String(url || "").trim();
  if (!v) return "";
  if (!v.endsWith("/")) v += "/";
  return v;
}

function normalizeIndexUrl(url) {
  const v = String(url || "").trim();
  if (!v) return "";
  if (v.toLowerCase().endsWith("index.json")) return v;
  if (v.endsWith("/")) return `${v}index.json`;
  return `${v}/index.json`;
}

function renderTemplate(text, skill) {
  const id = String(skill && skill.id ? skill.id : "");
  const parts = id.split("/");
  const domain = String(skill && skill.domain ? skill.domain : parts[0] || "");
  const topic = String(parts[1] || "");
  const slug = String(parts[2] || "");
  const title = String(skill && skill.title ? skill.title : "");
  const level = String(skill && skill.level ? skill.level : "");
  const risk = String(skill && skill.risk_level ? skill.risk_level : "");

  const vars = { id, domain, topic, slug, title, level, risk_level: risk };
  return String(text || "").replace(/\{\{([a-zA-Z0-9_]+)\}\}/g, (m, k) => (k in vars ? vars[k] : m));
}

function baseUrlFromIndexUrl(indexUrl) {
  const u = new URL(String(indexUrl || "").trim());
  u.hash = "";
  u.search = "";
  u.pathname = u.pathname.replace(/index\.json$/i, "");
  if (!u.pathname.endsWith("/")) u.pathname += "/";
  return u.toString();
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

function tryReadGitOriginUrl(repoRoot) {
  try {
    const configPath = path.join(repoRoot, ".git", "config");
    if (!exists(configPath)) return null;
    const text = readText(configPath).replace(/\r\n/g, "\n");
    const m = text.match(/\[remote\s+"origin"\][\s\S]*?\n\s*url\s*=\s*(.+?)\s*(?:\n|$)/i);
    if (!m) return null;
    return String(m[1] || "").trim() || null;
  } catch {
    return null;
  }
}

function parseGitHubOwnerRepo(remoteUrl) {
  const v = String(remoteUrl || "").trim();
  if (!v) return null;

  const m = v.match(/github\.com[:/](?<owner>[^/]+?)\/(?<repo>[^/]+?)(?:\.git)?$/i);
  if (!m || !m.groups) return null;

  const owner = String(m.groups.owner || "").trim();
  const repo = String(m.groups.repo || "").trim();
  if (!owner || !repo) return null;
  return { owner, repo };
}

function defaultRemoteIndexUrl(repoRoot) {
  const env = String(process.env.SKILL_REMOTE_INDEX_URL || "").trim();
  if (env) return env;

  const origin = tryReadGitOriginUrl(repoRoot);
  const parsed = parseGitHubOwnerRepo(origin);
  if (!parsed) return null;
  const host = String(parsed.owner || "").trim().toLowerCase();
  return `https://${host}.github.io/${parsed.repo}/index.json`;
}

function parseSimpleYamlScalar(text, key) {
  const re = new RegExp(`^${key}:\\s*(.+?)\\s*$`, "m");
  const m = text.match(re);
  if (!m) return null;
  let value = m[1].trim();
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    value = value.slice(1, -1);
  }
  return value;
}

function parseSimpleYamlBool(text, key) {
  const raw = parseSimpleYamlScalar(text, key);
  if (raw === null) return null;
  const v = String(raw).trim().toLowerCase();
  if (v === "true") return true;
  if (v === "false") return false;
  return null;
}

function walkDirs(rootDir) {
  const dirs = [];
  const stack = [rootDir];
  while (stack.length > 0) {
    const current = stack.pop();
    const entries = fs.readdirSync(current, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      const full = path.join(current, entry.name);
      dirs.push(full);
      stack.push(full);
    }
  }
  return dirs;
}

function readJson(filePath) {
  const raw = readText(filePath);
  try {
    return JSON.parse(raw);
  } catch (e) {
    throw new Error(`Invalid JSON: ${filePath} (${String(e && e.message ? e.message : e)})`);
  }
}

function loadSkillsets(skillsRoot) {
  const p = path.join(skillsRoot, "skillsets.json");
  if (!exists(p)) return null;
  const parsed = readJson(p);
  const schemaVersion = Number(parsed && parsed.schema_version ? parsed.schema_version : 0);
  if (!Number.isFinite(schemaVersion) || schemaVersion < 1) {
    throw new Error(`Invalid skillsets.json schema_version (expected >=1): ${p}`);
  }
  return parsed;
}

function mustFiniteInt(value, label) {
  const n = Number(value);
  if (!Number.isFinite(n) || !Number.isInteger(n)) throw new Error(`${label} must be an integer (got: ${value})`);
  return n;
}

function computeLevelForSeq(seq, rules) {
  const r = rules && typeof rules === "object" ? rules : {};
  const fallback = String(r.default || "bronze").trim().toLowerCase() || "bronze";
  const silverEvery = Number(r.silver_every || 0);
  const goldEvery = Number(r.gold_every || 0);
  if (Number.isFinite(goldEvery) && goldEvery > 0 && seq % goldEvery === 0) return "gold";
  if (Number.isFinite(silverEvery) && silverEvery > 0 && seq % silverEvery === 0) return "silver";
  return fallback;
}

function expandParameterizedSkillsets(atomicSkills, skillsets) {
  const generators = skillsets && Array.isArray(skillsets.parameterized) ? skillsets.parameterized : [];
  if (generators.length === 0) return [];

  const byId = new Map((Array.isArray(atomicSkills) ? atomicSkills : []).map((s) => [s.id, s]));
  const out = [];

  for (const g of generators) {
    const templateId = String(g && g.template_id ? g.template_id : "").trim();
    if (!templateId) throw new Error("skillsets.json parameterized generator is missing template_id");
    const template = byId.get(templateId);
    if (!template) throw new Error(`skillsets.json template_id not found in skills/: ${templateId}`);

    const outputDomain = String(g && g.output_domain ? g.output_domain : template.domain).trim();
    const outputTopic = String(g && g.output_topic ? g.output_topic : "").trim();
    if (!outputDomain) throw new Error(`skillsets.json output_domain is required for template_id=${templateId}`);
    if (!outputTopic) throw new Error(`skillsets.json output_topic is required for template_id=${templateId}`);

    const count = mustFiniteInt(g && g.count ? g.count : 0, `skillsets.json count for template_id=${templateId}`);
    if (count <= 0) throw new Error(`skillsets.json count must be > 0 for template_id=${templateId}`);
    const start = mustFiniteInt(g && g.start ? g.start : 1, `skillsets.json start for template_id=${templateId}`);
    if (start <= 0) throw new Error(`skillsets.json start must be > 0 for template_id=${templateId}`);

    const slugPrefix = String(g && g.slug_prefix ? g.slug_prefix : "").trim();
    const slugPad = mustFiniteInt(g && g.slug_pad ? g.slug_pad : 6, `skillsets.json slug_pad for template_id=${templateId}`);
    if (slugPad < 0 || slugPad > 12) throw new Error(`skillsets.json slug_pad out of range for template_id=${templateId}: ${slugPad}`);

    const titleTemplate = String(g && g.title_template ? g.title_template : "{id}").trim() || "{id}";
    const riskLevel = String(g && g.risk_level ? g.risk_level : template.risk_level).trim() || template.risk_level;
    const kind = "parameterized";

    for (let i = 0; i < count; i++) {
      const seq = i + 1;
      const n = start + i;
      const slug = `${slugPrefix}${String(n).padStart(slugPad, "0")}`;
      const id = `${outputDomain}/${outputTopic}/${slug}`;

      const title = titleTemplate
        .replaceAll("{n}", String(n))
        .replaceAll("{seq}", String(seq))
        .replaceAll("{slug}", slug)
        .replaceAll("{id}", id);

      out.push({
        id,
        title,
        domain: outputDomain,
        topic: outputTopic,
        slug,
        level: computeLevelForSeq(seq, g && g.levels ? g.levels : null),
        risk_level: riskLevel,
        kind,
        template: templateId,
        hidden: false,
        dir: null,
        rel_dir: `skills/${id}`,
      });
    }
  }

  out.sort((a, b) => a.id.localeCompare(b.id));
  return out;
}

function parseSkillIdParts(id) {
  const raw = String(id || "").trim();
  const parts = raw.split("/").filter(Boolean);
  if (parts.length !== 3) return null;
  const [domain, topic, slug] = parts;
  if (!domain || !topic || !slug) return null;
  return { domain, topic, slug };
}

function tryResolveParameterizedById({ atomicSkills, skillsets }, id) {
  const parts = parseSkillIdParts(id);
  if (!parts) return null;

  const generators = skillsets && Array.isArray(skillsets.parameterized) ? skillsets.parameterized : [];
  if (generators.length === 0) return null;

  const byId = new Map((Array.isArray(atomicSkills) ? atomicSkills : []).map((s) => [s.id, s]));

  for (const g of generators) {
    const templateId = String(g && g.template_id ? g.template_id : "").trim();
    if (!templateId) continue;
    const template = byId.get(templateId);
    if (!template) throw new Error(`skillsets.json template_id not found in skills/: ${templateId}`);

    const outputDomain = String(g && g.output_domain ? g.output_domain : template.domain).trim();
    const outputTopic = String(g && g.output_topic ? g.output_topic : "").trim();
    if (!outputDomain || !outputTopic) continue;

    if (parts.domain !== outputDomain || parts.topic !== outputTopic) continue;

    const slugPrefix = String(g && g.slug_prefix ? g.slug_prefix : "").trim();
    const slugPad = mustFiniteInt(g && g.slug_pad ? g.slug_pad : 6, `skillsets.json slug_pad for template_id=${templateId}`);
    if (!parts.slug.startsWith(slugPrefix)) continue;
    const suffix = parts.slug.slice(slugPrefix.length);
    if (!/^\d+$/.test(suffix)) continue;
    const n = Number(suffix);
    if (!Number.isFinite(n) || !Number.isInteger(n) || n <= 0) continue;
    const expectedSlug = `${slugPrefix}${String(n).padStart(slugPad, "0")}`;
    if (expectedSlug !== parts.slug) continue;

    const start = mustFiniteInt(g && g.start ? g.start : 1, `skillsets.json start for template_id=${templateId}`);
    const count = mustFiniteInt(g && g.count ? g.count : 0, `skillsets.json count for template_id=${templateId}`);
    if (count <= 0) continue;
    if (n < start || n >= start + count) continue;

    const seq = n - start + 1;
    const titleTemplate = String(g && g.title_template ? g.title_template : "{id}").trim() || "{id}";
    const riskLevel = String(g && g.risk_level ? g.risk_level : template.risk_level).trim() || template.risk_level;
    const slug = parts.slug;
    const fullId = `${outputDomain}/${outputTopic}/${slug}`;
    const title = titleTemplate
      .replaceAll("{n}", String(n))
      .replaceAll("{seq}", String(seq))
      .replaceAll("{slug}", slug)
      .replaceAll("{id}", fullId);

    return {
      id: fullId,
      title,
      domain: outputDomain,
      topic: outputTopic,
      slug,
      level: computeLevelForSeq(seq, g && g.levels ? g.levels : null),
      risk_level: riskLevel,
      kind: "parameterized",
      template: templateId,
      hidden: false,
      dir: null,
      rel_dir: `skills/${fullId}`,
    };
  }

  return null;
}

function dedupeByIdOrThrow(skills, label = "skills") {
  const seen = new Map();
  for (const s of Array.isArray(skills) ? skills : []) {
    if (!s || !s.id) continue;
    const prev = seen.get(s.id);
    if (prev) {
      throw new Error(`Duplicate skill id in ${label}: '${s.id}' (from ${prev.kind || "unknown"} and ${s.kind || "unknown"})`);
    }
    seen.set(s.id, s);
  }
}

function loadLocalContext(repoRoot) {
  const skillsRoot = path.join(repoRoot, "skills");
  if (!exists(skillsRoot)) {
    throw new Error(`Missing skills/ at ${skillsRoot}`);
  }

  const skills = [];
  for (const dirPath of walkDirs(skillsRoot)) {
    const metadataPath = path.join(dirPath, "metadata.yaml");
    if (!exists(metadataPath)) continue;

    const rel = path.relative(skillsRoot, dirPath).split(path.sep).join("/");
    const parts = rel.split("/");
    if (parts.length !== 3) continue;
    const [domainFromPath, topicFromPath, slugFromPath] = parts;

    const metaText = readText(metadataPath);
    const id = parseSimpleYamlScalar(metaText, "id") || rel;
    const title = parseSimpleYamlScalar(metaText, "title") || id;
    const domain = parseSimpleYamlScalar(metaText, "domain") || domainFromPath;
    const topic = parseSimpleYamlScalar(metaText, "topic") || topicFromPath;
    const slug = parseSimpleYamlScalar(metaText, "slug") || slugFromPath;
    const level = parseSimpleYamlScalar(metaText, "level") || "bronze";
    const riskLevel = parseSimpleYamlScalar(metaText, "risk_level") || "low";
    const kind = parseSimpleYamlScalar(metaText, "kind") || "atomic";
    const hidden = parseSimpleYamlBool(metaText, "hidden") || false;

    skills.push({
      id,
      title,
      domain,
      topic,
      slug,
      level,
      risk_level: riskLevel,
      kind,
      hidden,
      dir: dirPath,
      rel_dir: `skills/${rel}`,
    });
  }

  skills.sort((a, b) => a.id.localeCompare(b.id));
  const byId = new Map(skills.map((s) => [s.id, s]));
  const skillsets = loadSkillsets(skillsRoot);
  return { skillsRoot, atomicSkills: skills, byId, skillsets };
}

function loadSkillsLocal({ repoRoot, includeHidden = false, includeParameterized = false }) {
  const ctx = loadLocalContext(repoRoot);
  const atomic = includeHidden ? ctx.atomicSkills : ctx.atomicSkills.filter((s) => !(s && s.hidden));
  const parameterized = includeParameterized ? expandParameterizedSkillsets(ctx.atomicSkills, ctx.skillsets) : [];
  const out = [...atomic, ...parameterized].filter((s) => s && s.id);
  dedupeByIdOrThrow(out, "local skills");
  out.sort((a, b) => a.id.localeCompare(b.id));
  return out;
}

function safeIdToFsPathParts(id) {
  const baseId = String(id || "")
    .trim()
    .replace(/\\/g, "/")
    .replace(/^\/+/, "");
  if (!baseId) throw new Error("Missing skill id");
  if (baseId.includes("..")) throw new Error(`Invalid skill id: ${id}`);
  return baseId.split("/").filter(Boolean);
}

function localFilePathFor({ repoRoot, skill, which }) {
  const templateId = String(skill && skill.template ? skill.template : "").trim();
  if (templateId) {
    const parts = safeIdToFsPathParts(templateId);
    const templateDir = path.join(repoRoot, "skills", ...parts);
    return { filePath: pickFile(templateDir, which), isTemplate: true };
  }

  if (!skill || !skill.dir) throw new Error(`Missing local dir for skill: ${String(skill && skill.id ? skill.id : "")}`);
  return { filePath: pickFile(skill.dir, which), isTemplate: false };
}

function writeTempFile(prefix, filename, content) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  const outPath = path.join(dir, filename);
  fs.writeFileSync(outPath, content, "utf8");
  return outPath;
}

async function fetchWithTimeout(url, timeoutMs) {
  if (typeof fetch !== "function") throw new Error("Global fetch() not available. Use Node.js 18+.");
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), Math.max(1, Number(timeoutMs || 15000)));
  try {
    const resp = await fetch(url, { method: "GET", cache: "no-store", redirect: "follow", signal: controller.signal });
    const text = await resp.text();
    return { ok: resp.ok, status: resp.status, text, contentType: resp.headers.get("content-type") || "" };
  } finally {
    clearTimeout(t);
  }
}

async function loadSkillsRemote({ indexUrl, timeoutMs }) {
  const r = await fetchWithTimeout(indexUrl, timeoutMs);
  if (!r.ok) throw new Error(`Failed to load index.json (${r.status}): ${indexUrl}`);
  let parsed;
  try {
    parsed = JSON.parse(r.text);
  } catch {
    throw new Error(`Invalid JSON from index.json: ${indexUrl}`);
  }
  const skills = Array.isArray(parsed.skills) ? parsed.skills : [];
  return skills
    .map((s) => ({
      id: s && s.id ? String(s.id) : "",
      title: s && s.title ? String(s.title) : "",
      domain: s && s.domain ? String(s.domain) : "",
      level: s && s.level ? String(s.level) : "bronze",
      risk_level: s && s.risk_level ? String(s.risk_level) : "low",
      rel_dir: s && s.id ? `skills/${String(s.id)}` : "",
      files: s && s.files && typeof s.files === "object" ? s.files : null,
      template: s && s.template ? String(s.template) : "",
    }))
    .filter((s) => s.id);
}

function usage(exitCode = 0) {
  const msg = `
Usage:
  node cli/skill.js list [--json] [--include-hidden] [--include-parameterized]
  node cli/skill.js search <query> [--json] [--atomic-only] [--include-hidden]
  node cli/skill.js show <id> [--file skill|library|sources]
  node cli/skill.js copy <id> [--file library|skill|sources] [--clipboard]
  node cli/skill.js open <id> [--file skill|library|sources]

Online mode (HTTP):
  Add one of:
    --base-url <url>   e.g. http://127.0.0.1:4173/ or https://<owner>.github.io/<repo>/
    --index-url <url>  e.g. http://127.0.0.1:4173/index.json
    --online           derive from git origin (or SKILL_REMOTE_INDEX_URL)
`;
  if (exitCode === 0) console.log(msg.trim());
  else console.error(msg.trim());
  process.exit(exitCode);
}

function pickFile(skillDir, which) {
  if (which === "library") return path.join(skillDir, "library.md");
  if (which === "sources") return path.join(skillDir, "reference", "sources.md");
  return path.join(skillDir, "skill.md");
}

function remoteFilePathFor(skill, which) {
  const fileKey = which === "sources" ? "sources" : which;
  const embedded = skill && skill.files && skill.files[fileKey] ? String(skill.files[fileKey]) : "";
  if (embedded) return embedded.replace(/^\/+/, "");

  const baseId = String(skill && (skill.template || skill.id) ? (skill.template || skill.id) : "")
    .trim()
    .replace(/\\/g, "/")
    .replace(/^\/+/, "");
  const id = baseId;
  if (!id) throw new Error("Missing skill id");
  if (id.includes("..")) throw new Error(`Invalid skill id: ${id}`);

  const base = `skills/${id}`;
  if (which === "library") return `${base}/library.md`;
  if (which === "sources") return `${base}/reference/sources.md`;
  return `${base}/skill.md`;
}

function openFile(filePath) {
  const platform = process.platform;
  if (platform === "win32") {
    childProcess.spawn("cmd.exe", ["/c", "start", "", filePath], {
      stdio: "ignore",
      detached: true,
    });
    return;
  }
  if (platform === "darwin") {
    childProcess.spawn("open", [filePath], { stdio: "ignore", detached: true });
    return;
  }
  childProcess.spawn("xdg-open", [filePath], { stdio: "ignore", detached: true });
}

function copyToClipboard(text) {
  const platform = process.platform;
  if (platform === "win32") {
    const p = childProcess.spawnSync("clip.exe", [], { input: text, encoding: "utf8" });
    if (p.status !== 0) throw new Error("Failed to copy via clip.exe");
    return;
  }
  if (platform === "darwin") {
    const p = childProcess.spawnSync("pbcopy", [], { input: text, encoding: "utf8" });
    if (p.status !== 0) throw new Error("Failed to copy via pbcopy");
    return;
  }

  // linux: try wl-copy then xclip
  let p = childProcess.spawnSync("wl-copy", [], { input: text, encoding: "utf8" });
  if (p.status === 0) return;
  p = childProcess.spawnSync("xclip", ["-selection", "clipboard"], {
    input: text,
    encoding: "utf8",
  });
  if (p.status !== 0) throw new Error("Failed to copy via wl-copy/xclip");
}

function parseFlags(args) {
  const flags = {
    json: false,
    clipboard: false,
    file: "skill",
    online: false,
    baseUrl: null,
    indexUrl: null,
    timeoutMs: 15000,
    atomicOnly: false,
    includeHidden: false,
    includeParameterized: false,
  };
  const rest = [];
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === "--json") flags.json = true;
    else if (a === "--clipboard") flags.clipboard = true;
    else if (a === "--online") flags.online = true;
    else if (a === "--atomic-only") flags.atomicOnly = true;
    else if (a === "--include-hidden") flags.includeHidden = true;
    else if (a === "--include-parameterized") flags.includeParameterized = true;
    else if (a === "--file") {
      const v = args[i + 1];
      if (!v) throw new Error("--file requires a value");
      flags.file = v;
      i++;
    } else if (a === "--base-url") {
      const v = args[i + 1];
      if (!v) throw new Error("--base-url requires a value");
      flags.baseUrl = v;
      i++;
    } else if (a === "--index-url") {
      const v = args[i + 1];
      if (!v) throw new Error("--index-url requires a value");
      flags.indexUrl = v;
      i++;
    } else if (a === "--timeout-ms") {
      const v = args[i + 1];
      if (!v) throw new Error("--timeout-ms requires a value");
      flags.timeoutMs = Number(v);
      i++;
    } else rest.push(a);
  }
  return { flags, rest };
}

function resolveRemoteConfig(flags, repoRoot) {
  const timeoutMs = Number.isFinite(flags.timeoutMs) ? flags.timeoutMs : 15000;

  let indexUrl = flags.indexUrl ? normalizeIndexUrl(flags.indexUrl) : "";
  let baseUrl = flags.baseUrl ? normalizeBaseUrl(flags.baseUrl) : "";

  if (!indexUrl && baseUrl) indexUrl = normalizeIndexUrl(baseUrl);
  if (!indexUrl && flags.online) indexUrl = defaultRemoteIndexUrl(repoRoot) || "";
  if (!indexUrl) return null;

  if (!baseUrl) baseUrl = baseUrlFromIndexUrl(indexUrl);
  return { baseUrl, indexUrl, timeoutMs };
}

async function main() {
  const repoRoot = path.resolve(__dirname, "..");

  const argv = process.argv.slice(2);
  if (argv.length === 0 || argv.includes("-h") || argv.includes("--help")) usage(0);

  const command = argv[0];
  const { flags, rest } = parseFlags(argv.slice(1));

  const remote = resolveRemoteConfig(flags, repoRoot);
  let localCtx = null;
  let skills = [];
  if (remote) {
    skills = await loadSkillsRemote(remote);
    if ((command === "list" || command === "search") && flags.atomicOnly) {
      skills = skills.filter((s) => !(s && s.template));
    }
  } else if (command === "list") {
    skills = loadSkillsLocal({
      repoRoot,
      includeHidden: flags.includeHidden,
      includeParameterized: flags.includeParameterized,
    });
  } else if (command === "search") {
    skills = loadSkillsLocal({
      repoRoot,
      includeHidden: flags.includeHidden,
      includeParameterized: !flags.atomicOnly,
    });
  } else {
    // Keep show/copy/open fast by not expanding parameterized skills unless needed.
    localCtx = loadLocalContext(repoRoot);
    skills = localCtx.atomicSkills;
  }

  if (command === "list") {
    if (flags.json) console.log(JSON.stringify(skills, null, 2));
    else skills.forEach((s) => console.log(`${s.id}\t[${s.level}/${s.risk_level}]\t${s.title}`));
    return;
  }

  if (command === "search") {
    const query = rest.join(" ").trim();
    if (!query) usage(2);
    const q = query.toLowerCase();
    const hits = skills.filter(
      (s) =>
        s.id.toLowerCase().includes(q) ||
        s.title.toLowerCase().includes(q) ||
        s.domain.toLowerCase().includes(q),
    );
    if (flags.json) console.log(JSON.stringify(hits, null, 2));
    else hits.forEach((s) => console.log(`${s.id}\t[${s.level}/${s.risk_level}]\t${s.title}`));
    return;
  }

  const id = rest[0];
  if (!id) usage(2);
  let skill = skills.find((s) => s.id === id);
  if (!skill && !remote && localCtx) {
    // Allow direct resolution of parameterized skills without enumerating 100k entries.
    skill = tryResolveParameterizedById(localCtx, id);
  }
  if (!skill) {
    console.error(`Skill not found: ${id}`);
    process.exit(1);
  }

  if (command === "show") {
    if (!remote) {
      const { filePath, isTemplate } = localFilePathFor({ repoRoot, skill, which: flags.file });
      const content = readText(filePath);
      process.stdout.write(isTemplate ? renderTemplate(content, skill) : content);
      return;
    }

    const relPath = remoteFilePathFor(skill, flags.file);
    const url = new URL(relPath, remote.baseUrl).toString();
    const r = await fetchWithTimeout(url, remote.timeoutMs);
    if (!r.ok) throw new Error(`Failed to load ${flags.file} (${r.status}): ${url}`);
    const content = skill.template ? renderTemplate(r.text, skill) : r.text;
    process.stdout.write(content);
    return;
  }

  if (command === "copy") {
    let content = "";
    if (!remote) {
      const { filePath, isTemplate } = localFilePathFor({ repoRoot, skill, which: flags.file });
      content = readText(filePath);
      if (isTemplate) content = renderTemplate(content, skill);
    } else {
      const relPath = remoteFilePathFor(skill, flags.file);
      const url = new URL(relPath, remote.baseUrl).toString();
      const r = await fetchWithTimeout(url, remote.timeoutMs);
      if (!r.ok) throw new Error(`Failed to load ${flags.file} (${r.status}): ${url}`);
      content = skill.template ? renderTemplate(r.text, skill) : r.text;
    }
    if (flags.clipboard) {
      copyToClipboard(content);
      console.error(`Copied to clipboard: ${skill.id} (${flags.file})`);
    } else {
      process.stdout.write(content);
    }
    return;
  }

  if (command === "open") {
    if (!remote) {
      const { filePath, isTemplate } = localFilePathFor({ repoRoot, skill, which: flags.file });
      if (!isTemplate) {
        openFile(filePath);
        console.log(filePath);
        return;
      }

      const rendered = renderTemplate(readText(filePath), skill);
      const safeName = `${String(skill.id || "skill").replace(/[^a-zA-Z0-9._-]+/g, "_")}-${flags.file}.md`;
      const outPath = writeTempFile("skill-open-", safeName, rendered);
      openFile(outPath);
      console.log(outPath);
      return;
    }

    const relPath = remoteFilePathFor(skill, flags.file);
    const url = new URL(relPath, remote.baseUrl).toString();
    openFile(url);
    console.log(url);
    return;
  }

  usage(2);
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
