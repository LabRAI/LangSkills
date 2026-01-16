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

    skills.push({
      id,
      title,
      domain,
      topic,
      slug,
      level,
      risk_level: riskLevel,
    });
  }

  skills.sort((a, b) => a.id.localeCompare(b.id));
  return skills;
}

function parseArgs(argv) {
  const out = { outDir: null, skillsRoot: null, noCopySkills: false, syntheticCount: 0 };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--out") {
      out.outDir = argv[i + 1] || null;
      i++;
    } else if (a === "--skills-root") {
      out.skillsRoot = argv[i + 1] || null;
      i++;
    } else if (a === "--no-copy-skills") {
      out.noCopySkills = true;
    } else if (a === "--synthetic-count") {
      out.syntheticCount = Number(argv[i + 1] || "0");
      i++;
    }
  }
  return out;
}

function generateSyntheticSkills(count) {
  const domains = ["linux", "web", "cloud", "data", "productivity", "travel", "integrations", "devtools"];
  const topic = "synthetic";
  const skills = [];

  const total = Math.floor(Number(count));
  if (!Number.isFinite(total) || total <= 0) throw new Error(`--synthetic-count must be a positive integer (got ${count})`);

  for (let i = 0; i < total; i++) {
    const domain = domains[i % domains.length];
    const slug = `s-${String(i + 1).padStart(6, "0")}`;
    const id = `${domain}/${topic}/${slug}`;
    skills.push({
      id,
      title: `Synthetic Skill ${slug}`,
      domain,
      topic,
      slug,
      level: i % 50 === 0 ? "gold" : i % 10 === 0 ? "silver" : "bronze",
      risk_level: "low",
    });
  }

  return skills;
}

function copySkillContent(skillsRoot, outDir, skills) {
  for (const s of skills) {
    const domain = String(s.domain || "").trim();
    const topic = String(s.topic || "").trim();
    const slug = String(s.slug || "").trim();
    if (!domain || !topic || !slug) continue;

    const srcBase = path.join(skillsRoot, domain, topic, slug);
    const dstBase = path.join(outDir, "skills", domain, topic, slug);

    const pairs = [
      { src: path.join(srcBase, "skill.md"), dst: path.join(dstBase, "skill.md") },
      { src: path.join(srcBase, "library.md"), dst: path.join(dstBase, "library.md") },
      { src: path.join(srcBase, "reference", "sources.md"), dst: path.join(dstBase, "reference", "sources.md") },
    ];

    for (const p of pairs) {
      if (!exists(p.src)) continue;
      copyFile(p.src, p.dst);
    }
  }
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const repoRoot = path.resolve(__dirname, "..");
  const skillsRoot = args.skillsRoot ? path.resolve(repoRoot, args.skillsRoot) : path.join(repoRoot, "skills");
  const outDir = args.outDir ? path.resolve(repoRoot, args.outDir) : path.join(repoRoot, "website", "dist");
  const websiteSrc = path.join(repoRoot, "website", "src");

  if (!exists(websiteSrc)) throw new Error(`Missing website src: ${websiteSrc}`);
  if (args.syntheticCount <= 0 && !exists(skillsRoot)) throw new Error(`Missing skills root: ${skillsRoot}`);

  ensureDir(outDir);

  const skillsInternal = args.syntheticCount > 0 ? generateSyntheticSkills(args.syntheticCount) : loadSkills(skillsRoot);
  const skills = skillsInternal.map((s) => ({
    id: s.id,
    title: s.title,
    domain: s.domain,
    level: s.level,
    risk_level: s.risk_level,
  }));
  const index = {
    schema_version: 2,
    generated_at: new Date().toISOString(),
    skills_count: skills.length,
    skills,
  };

  const pretty = skills.length <= 5000;
  writeText(path.join(outDir, "index.json"), pretty ? JSON.stringify(index, null, 2) : JSON.stringify(index));

  copyFile(path.join(websiteSrc, "index.html"), path.join(outDir, "index.html"));
  copyFile(path.join(websiteSrc, "style.css"), path.join(outDir, "style.css"));
  copyFile(path.join(websiteSrc, "app.js"), path.join(outDir, "app.js"));

  if (!args.noCopySkills && args.syntheticCount <= 0) {
    copySkillContent(skillsRoot, outDir, skillsInternal);
  }

  console.log(`Built site: ${outDir}`);
  console.log(`Skills indexed: ${skills.length}`);
}

main();
