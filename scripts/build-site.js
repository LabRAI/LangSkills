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

function readJson(filePath) {
  const raw = readText(filePath);
  try {
    return JSON.parse(raw);
  } catch (e) {
    throw new Error(`Invalid JSON: ${filePath} (${String(e && e.message ? e.message : e)})`);
  }
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
    const kind = parseSimpleYamlScalar(metaText, "kind") || "atomic";
    const hiddenRaw = parseSimpleYamlScalar(metaText, "hidden");
    const hidden = hiddenRaw ? /^true$/i.test(String(hiddenRaw).trim()) : false;

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
      });
    }
  }

  out.sort((a, b) => a.id.localeCompare(b.id));
  return out;
}

function computeIndexCounts(allSkills) {
  const counts = {
    total: 0,
    atomic: 0,
    parameterized: 0,
    composite: 0,
    by_level: { bronze: 0, silver: 0, gold: 0 },
  };

  const skills = Array.isArray(allSkills) ? allSkills : [];
  counts.total = skills.length;
  for (const s of skills) {
    const kind = String((s && s.kind) || "atomic").trim().toLowerCase();
    if (kind === "parameterized") counts.parameterized++;
    else if (kind === "composite") counts.composite++;
    else counts.atomic++;

    const level = String((s && s.level) || "bronze").trim().toLowerCase();
    if (level === "gold") counts.by_level.gold++;
    else if (level === "silver") counts.by_level.silver++;
    else counts.by_level.bronze++;
  }

  return counts;
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

  const atomicSkills = args.syntheticCount > 0 ? generateSyntheticSkills(args.syntheticCount) : loadSkills(skillsRoot);
  const skillsets = args.syntheticCount > 0 ? null : loadSkillsets(skillsRoot);
  const paramSkills = args.syntheticCount > 0 ? [] : expandParameterizedSkillsets(atomicSkills, skillsets);

  const seen = new Map();
  const allSkillsInternal = [...atomicSkills, ...paramSkills].filter((s) => s && s.id);
  for (const s of allSkillsInternal) {
    const prev = seen.get(s.id);
    if (prev) {
      throw new Error(`Duplicate skill id in index build: '${s.id}' (from ${prev.kind || "unknown"} and ${s.kind || "unknown"})`);
    }
    seen.set(s.id, s);
  }

  allSkillsInternal.sort((a, b) => a.id.localeCompare(b.id));

  const visibleSkillsInternal = allSkillsInternal.filter((s) => !(s && s.hidden));
  const skills = visibleSkillsInternal.map((s) => ({
    id: s.id,
    title: s.title,
    domain: s.domain,
    level: s.level,
    risk_level: s.risk_level,
    ...(s.template ? { template: s.template } : null),
    ...(s.kind ? { kind: s.kind } : null),
  }));

  const counts = computeIndexCounts(visibleSkillsInternal);
  const index = {
    schema_version: 2,
    generated_at: new Date().toISOString(),
    skills_count: skills.length,
    counts,
    skills,
  };

  const pretty = skills.length <= 5000;
  writeText(path.join(outDir, "index.json"), pretty ? JSON.stringify(index, null, 2) : JSON.stringify(index));

  copyFile(path.join(websiteSrc, "index.html"), path.join(outDir, "index.html"));
  copyFile(path.join(websiteSrc, "style.css"), path.join(outDir, "style.css"));
  copyFile(path.join(websiteSrc, "app.js"), path.join(outDir, "app.js"));

  if (!args.noCopySkills && args.syntheticCount <= 0) {
    copySkillContent(skillsRoot, outDir, atomicSkills);
  }

  console.log(`Built site: ${outDir}`);
  console.log(`Skills indexed: ${skills.length}`);
}

main();
