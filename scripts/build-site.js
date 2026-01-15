#!/usr/bin/env node
/* eslint-disable no-console */

const fs = require("fs");
const path = require("path");

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

function writeText(filePath, content) {
  ensureDir(path.dirname(filePath));
  fs.writeFileSync(filePath, content, "utf8");
}

function copyFile(src, dst) {
  ensureDir(path.dirname(dst));
  fs.copyFileSync(src, dst);
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

function loadSkills(skillsRoot) {
  const skills = [];
  for (const dirPath of walkDirs(skillsRoot)) {
    const metadataPath = path.join(dirPath, "metadata.yaml");
    if (!exists(metadataPath)) continue;

    const rel = path.relative(skillsRoot, dirPath).split(path.sep).join("/");
    const parts = rel.split("/");
    if (parts.length !== 3) continue;
    const [domain, topic, slug] = parts;

    const metaText = readText(metadataPath);
    const id = parseSimpleYamlScalar(metaText, "id") || rel;
    const title = parseSimpleYamlScalar(metaText, "title") || id;
    const level = parseSimpleYamlScalar(metaText, "level") || "bronze";
    const riskLevel = parseSimpleYamlScalar(metaText, "risk_level") || "low";

    const skillPath = path.join(dirPath, "skill.md");
    const libraryPath = path.join(dirPath, "library.md");
    const sourcesPath = path.join(dirPath, "reference", "sources.md");

    skills.push({
      id,
      title,
      domain,
      topic,
      slug,
      level,
      risk_level: riskLevel,
      skill_md: exists(skillPath) ? readText(skillPath) : "",
      library_md: exists(libraryPath) ? readText(libraryPath) : "",
      sources_md: exists(sourcesPath) ? readText(sourcesPath) : "",
    });
  }

  skills.sort((a, b) => a.id.localeCompare(b.id));
  return skills;
}

function parseArgs(argv) {
  const out = { outDir: null, skillsRoot: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--out") {
      out.outDir = argv[i + 1] || null;
      i++;
    } else if (a === "--skills-root") {
      out.skillsRoot = argv[i + 1] || null;
      i++;
    }
  }
  return out;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const repoRoot = path.resolve(__dirname, "..");
  const skillsRoot = args.skillsRoot ? path.resolve(repoRoot, args.skillsRoot) : path.join(repoRoot, "skills");
  const outDir = args.outDir ? path.resolve(repoRoot, args.outDir) : path.join(repoRoot, "website", "dist");
  const websiteSrc = path.join(repoRoot, "website", "src");

  if (!exists(skillsRoot)) throw new Error(`Missing skills root: ${skillsRoot}`);
  if (!exists(websiteSrc)) throw new Error(`Missing website src: ${websiteSrc}`);

  ensureDir(outDir);

  const skills = loadSkills(skillsRoot);
  const index = {
    generated_at: new Date().toISOString(),
    skills_count: skills.length,
    skills,
  };

  writeText(path.join(outDir, "index.json"), JSON.stringify(index, null, 2));

  copyFile(path.join(websiteSrc, "index.html"), path.join(outDir, "index.html"));
  copyFile(path.join(websiteSrc, "style.css"), path.join(outDir, "style.css"));
  copyFile(path.join(websiteSrc, "app.js"), path.join(outDir, "app.js"));

  console.log(`Built site: ${outDir}`);
  console.log(`Skills indexed: ${skills.length}`);
}

main();
