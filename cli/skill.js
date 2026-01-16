#!/usr/bin/env node
/* eslint-disable no-console */

const fs = require("fs");
const path = require("path");
const childProcess = require("child_process");

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

function loadSkillsLocal(repoRoot) {
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

    const metaText = readText(metadataPath);
    const id = parseSimpleYamlScalar(metaText, "id") || rel;
    const title = parseSimpleYamlScalar(metaText, "title") || id;
    const domain = parseSimpleYamlScalar(metaText, "domain") || parts[0];
    const level = parseSimpleYamlScalar(metaText, "level") || "bronze";
    const riskLevel = parseSimpleYamlScalar(metaText, "risk_level") || "low";

    skills.push({
      id,
      title,
      domain,
      level,
      risk_level: riskLevel,
      dir: dirPath,
      rel_dir: `skills/${rel}`,
    });
  }

  skills.sort((a, b) => a.id.localeCompare(b.id));
  return skills;
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
    }))
    .filter((s) => s.id);
}

function usage(exitCode = 0) {
  const msg = `
Usage:
  node cli/skill.js list [--json]
  node cli/skill.js search <query> [--json]
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

  const id = String(skill && skill.id ? skill.id : "").trim().replace(/\\/g, "/").replace(/^\/+/, "");
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
  const flags = { json: false, clipboard: false, file: "skill", online: false, baseUrl: null, indexUrl: null, timeoutMs: 15000 };
  const rest = [];
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === "--json") flags.json = true;
    else if (a === "--clipboard") flags.clipboard = true;
    else if (a === "--online") flags.online = true;
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
  const skills = remote ? await loadSkillsRemote(remote) : loadSkillsLocal(repoRoot);

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
  const skill = skills.find((s) => s.id === id);
  if (!skill) {
    console.error(`Skill not found: ${id}`);
    process.exit(1);
  }

  if (command === "show") {
    if (!remote) {
      const filePath = pickFile(skill.dir, flags.file);
      console.log(readText(filePath));
      return;
    }

    const relPath = remoteFilePathFor(skill, flags.file);
    const url = new URL(relPath, remote.baseUrl).toString();
    const r = await fetchWithTimeout(url, remote.timeoutMs);
    if (!r.ok) throw new Error(`Failed to load ${flags.file} (${r.status}): ${url}`);
    process.stdout.write(r.text);
    return;
  }

  if (command === "copy") {
    let content = "";
    if (!remote) {
      const filePath = pickFile(skill.dir, flags.file);
      content = readText(filePath);
    } else {
      const relPath = remoteFilePathFor(skill, flags.file);
      const url = new URL(relPath, remote.baseUrl).toString();
      const r = await fetchWithTimeout(url, remote.timeoutMs);
      if (!r.ok) throw new Error(`Failed to load ${flags.file} (${r.status}): ${url}`);
      content = r.text;
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
      const filePath = pickFile(skill.dir, flags.file);
      openFile(filePath);
      console.log(filePath);
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
