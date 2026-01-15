#!/usr/bin/env node
/* eslint-disable no-console */

const fs = require("fs");
const path = require("path");
const childProcess = require("child_process");

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

function loadSkills(repoRoot) {
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

function usage(exitCode = 0) {
  const msg = `
Usage:
  node cli/skill.js list [--json]
  node cli/skill.js search <query> [--json]
  node cli/skill.js show <id> [--file skill|library|sources]
  node cli/skill.js copy <id> [--file library|skill|sources] [--clipboard]
  node cli/skill.js open <id> [--file skill|library|sources]
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
  const flags = { json: false, clipboard: false, file: "skill" };
  const rest = [];
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === "--json") flags.json = true;
    else if (a === "--clipboard") flags.clipboard = true;
    else if (a === "--file") {
      const v = args[i + 1];
      if (!v) throw new Error("--file requires a value");
      flags.file = v;
      i++;
    } else rest.push(a);
  }
  return { flags, rest };
}

async function main() {
  const repoRoot = path.resolve(__dirname, "..");
  const skills = loadSkills(repoRoot);

  const argv = process.argv.slice(2);
  if (argv.length === 0 || argv.includes("-h") || argv.includes("--help")) usage(0);

  const command = argv[0];
  const { flags, rest } = parseFlags(argv.slice(1));

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
    const filePath = pickFile(skill.dir, flags.file);
    console.log(readText(filePath));
    return;
  }

  if (command === "copy") {
    const filePath = pickFile(skill.dir, flags.file);
    const content = readText(filePath);
    if (flags.clipboard) {
      copyToClipboard(content);
      console.error(`Copied to clipboard: ${skill.id} (${flags.file})`);
    } else {
      process.stdout.write(content);
    }
    return;
  }

  if (command === "open") {
    const filePath = pickFile(skill.dir, flags.file);
    openFile(filePath);
    console.log(filePath);
    return;
  }

  usage(2);
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
