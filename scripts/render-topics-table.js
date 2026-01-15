#!/usr/bin/env node
/* eslint-disable no-console */

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
  const skills = [];
  for (const dirPath of walkDirs(skillsRoot)) {
    const metadataPath = path.join(dirPath, "metadata.yaml");
    if (!exists(metadataPath)) continue;

    const rel = path.relative(skillsRoot, dirPath).split(path.sep).join("/");
    const parts = rel.split("/");
    if (parts.length !== 3) continue;
    const [domain, topic, slug] = parts;

    const metaText = readText(metadataPath);
    const id = parseSimpleYamlScalar(metaText, "id") || `${domain}/${topic}/${slug}`;
    const title = parseSimpleYamlScalar(metaText, "title") || id;
    const level = parseSimpleYamlScalar(metaText, "level") || "bronze";
    const riskLevel = parseSimpleYamlScalar(metaText, "risk_level") || "low";

    skills.push({ id, title, domain, topic, slug, level, risk_level: riskLevel });
  }
  skills.sort((a, b) => a.id.localeCompare(b.id));
  return skills;
}

function parseArgs(argv) {
  const out = { domain: null, withHeader: false, action: "generated", outPath: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--domain") {
      out.domain = argv[i + 1] || null;
      i++;
    } else if (a === "--with-header") out.withHeader = true;
    else if (a === "--action") {
      out.action = argv[i + 1] || "generated";
      i++;
    } else if (a === "--out") {
      out.outPath = argv[i + 1] || null;
      i++;
    }
  }
  return out;
}

function escapePipes(text) {
  return String(text || "").replace(/\|/g, "\\|");
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const repoRoot = path.resolve(__dirname, "..");
  const skills = loadSkills(repoRoot);
  const filtered = args.domain ? skills.filter((s) => s.domain === args.domain) : skills;

  const lines = [];

  if (args.withHeader) {
    lines.push("| ID | Title | Risk | Level | Action | Notes |");
    lines.push("|---|---|---:|---:|---:|---|");
  }

  for (const s of filtered) {
    lines.push(
      `| ${escapePipes(s.id)} | ${escapePipes(s.title)} | ${s.risk_level} | ${s.level} | ${args.action} | |`,
    );
  }

  if (args.outPath) {
    const outFile = path.resolve(repoRoot, args.outPath);
    fs.mkdirSync(path.dirname(outFile), { recursive: true });
    fs.writeFileSync(outFile, lines.join("\n") + "\n", "utf8");
    console.error(`Wrote: ${outFile}`);
    return;
  }

  for (const line of lines) console.log(line);
}

main();
