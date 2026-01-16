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

function readText(filePath) {
  return fs.readFileSync(filePath, "utf8");
}

function writeText(filePath, content) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, content, "utf8");
}

function ensureTrailingNewline(text) {
  const t = String(text || "");
  return t.endsWith("\n") ? t : `${t}\n`;
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

function parseArgs(argv) {
  const out = { skillsRoot: "skills", dryRun: false, licenseValue: "unknown" };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--skills-root") {
      out.skillsRoot = argv[i + 1] || out.skillsRoot;
      i++;
    } else if (a === "--license") {
      out.licenseValue = argv[i + 1] || out.licenseValue;
      i++;
    } else if (a === "--dry-run") out.dryRun = true;
    else if (a === "-h" || a === "--help") {
      console.log("Usage: node scripts/backfill-sources-license.js [--skills-root <path>] [--license <text>] [--dry-run]");
      process.exit(0);
    } else {
      throw new Error(`Unknown arg: ${a}`);
    }
  }
  return out;
}

function splitBlocks(lines) {
  const blocks = [];
  let current = [];
  for (const line of lines) {
    if (/^##\s+\[\d+\]\s*$/.test(line) && current.length > 0) {
      blocks.push(current);
      current = [line];
    } else {
      current.push(line);
    }
  }
  if (current.length > 0) blocks.push(current);
  return blocks;
}

function backfillSourcesMd(text, licenseValue) {
  if (/^\s*-\s*License:\s*/m.test(text)) return { changed: false, text };

  const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
  const blocks = splitBlocks(lines);

  const outLines = [];
  let changed = false;

  for (const block of blocks) {
    if (!block.some((l) => /^##\s+\[\d+\]\s*$/.test(l))) {
      outLines.push(...block);
      continue;
    }

    const hasLicense = block.some((l) => /^\s*-\s*License:\s*/.test(l));
    if (hasLicense) {
      outLines.push(...block);
      continue;
    }

    const idxSupports = block.findIndex((l) => /^\s*-\s*Supports:\s*/.test(l));
    const idxSummary = block.findIndex((l) => /^\s*-\s*Summary:\s*/.test(l));
    const insertAt = idxSupports >= 0 ? idxSupports + 1 : idxSummary >= 0 ? idxSummary + 1 : block.length;

    const next = block.slice();
    next.splice(insertAt, 0, `- License: ${licenseValue}`);
    outLines.push(...next);
    changed = true;
  }

  return { changed, text: outLines.join("\n") };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const repoRoot = path.resolve(__dirname, "..");
  const skillsRoot = path.isAbsolute(args.skillsRoot) ? args.skillsRoot : path.resolve(repoRoot, args.skillsRoot);

  if (!exists(skillsRoot)) throw new Error(`Missing skills root: ${skillsRoot}`);

  let updated = 0;
  let skipped = 0;

  for (const dirPath of walkDirs(skillsRoot)) {
    const sourcesPath = path.join(dirPath, "reference", "sources.md");
    if (!exists(sourcesPath)) continue;

    const before = readText(sourcesPath);
    const r = backfillSourcesMd(before, args.licenseValue);
    if (!r.changed) {
      skipped++;
      continue;
    }

    updated++;
    if (!args.dryRun) writeText(sourcesPath, ensureTrailingNewline(r.text));
  }

  console.log(`Done. updated=${updated} skipped=${skipped} dry_run=${args.dryRun}`);
}

main();

