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

function parseSimpleYamlScalar(text, key) {
  const re = new RegExp(`^${key}:\\s*(.+?)\\s*$`, "m");
  const m = String(text || "").match(re);
  if (!m) return null;
  let value = String(m[1] || "").trim();
  if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
    value = value.slice(1, -1);
  }
  return value;
}

function parseInlineYamlList(value) {
  const v = String(value || "").trim();
  if (!v) return [];
  if (v === "[]") return [];
  if (v.startsWith("[") && v.endsWith("]")) {
    const inner = v.slice(1, -1).trim();
    if (!inner) return [];
    return inner
      .split(",")
      .map((x) => x.trim())
      .map((x) => {
        if ((x.startsWith('"') && x.endsWith('"')) || (x.startsWith("'") && x.endsWith("'"))) return x.slice(1, -1);
        return x;
      })
      .filter(Boolean);
  }
  return [v];
}

function formatInlineYamlList(values) {
  const list = Array.isArray(values) ? values : [];
  if (list.length === 0) return "[]";
  return `[${list.map((v) => JSON.stringify(String(v))).join(", ")}]`;
}

function walkDirs(rootDir) {
  const out = [];
  const stack = [rootDir];
  while (stack.length > 0) {
    const current = stack.pop();
    let entries = [];
    try {
      entries = fs.readdirSync(current, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const e of entries) {
      if (!e.isDirectory()) continue;
      const full = path.join(current, e.name);
      out.push(full);
      stack.push(full);
    }
  }
  return out;
}

function parseYmd(s) {
  const m = String(s || "").trim().match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  const dt = new Date(Date.UTC(y, mo - 1, d));
  if (!Number.isFinite(dt.getTime())) return null;
  return dt;
}

function daysBetweenUtc(a, b) {
  const ms = a.getTime() - b.getTime();
  return Math.floor(ms / (24 * 60 * 60 * 1000));
}

function updateYamlScalar(text, key, nextValue) {
  const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
  const re = new RegExp(`^${key}:\\s*.*$`);
  const rendered = `${key}: ${nextValue}`;
  let replaced = false;
  const out = lines.map((line) => {
    if (!replaced && re.test(line)) {
      replaced = true;
      return rendered;
    }
    return line;
  });
  if (!replaced) {
    const insertAt = Math.min(out.length, 4);
    out.splice(insertAt, 0, rendered);
  }
  return out.join("\n").replace(/\n+$/, "\n");
}

function parseArgs(argv) {
  const out = {
    skillsRoot: "skills",
    outPath: null,
    staleDays: 90,
    archiveDays: 365,
    now: null,
    apply: false,
    downgrade: false,
    failOnStaleGold: false,
  };

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--skills-root") {
      out.skillsRoot = argv[i + 1] || out.skillsRoot;
      i++;
    } else if (a === "--out") {
      out.outPath = argv[i + 1] || null;
      i++;
    } else if (a === "--stale-days") {
      out.staleDays = Number(argv[i + 1] || out.staleDays);
      i++;
    } else if (a === "--archive-days") {
      out.archiveDays = Number(argv[i + 1] || out.archiveDays);
      i++;
    } else if (a === "--now") {
      out.now = String(argv[i + 1] || "").trim();
      i++;
    } else if (a === "--apply") {
      out.apply = true;
    } else if (a === "--downgrade") {
      out.downgrade = true;
    } else if (a === "--fail-on-stale-gold") {
      out.failOnStaleGold = true;
    } else if (a === "-h" || a === "--help") {
      console.log(
        [
          "Usage: node scripts/lifecycle.js [--skills-root skills] [--out <path>] [--stale-days N] [--archive-days N] [--now YYYY-MM-DD] [--apply] [--downgrade] [--fail-on-stale-gold]",
          "",
          "Outputs a JSON report of stale/archived candidates based on metadata.yaml last_verified.",
        ].join("\n"),
      );
      process.exit(0);
    }
  }

  if (!out.now) out.now = new Date().toISOString().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(out.now)) throw new Error(`--now must be YYYY-MM-DD (got: ${out.now})`);
  if (!Number.isFinite(out.staleDays) || out.staleDays < 1) throw new Error("--stale-days must be a positive number");
  if (!Number.isFinite(out.archiveDays) || out.archiveDays < out.staleDays) {
    throw new Error("--archive-days must be >= --stale-days");
  }
  return out;
}

function main() {
  const repoRoot = path.resolve(__dirname, "..");
  const args = parseArgs(process.argv.slice(2));
  const skillsRoot = path.resolve(repoRoot, args.skillsRoot);
  if (!exists(skillsRoot)) throw new Error(`Missing skills root: ${skillsRoot}`);

  const nowDt = parseYmd(args.now);
  if (!nowDt) throw new Error(`Invalid --now: ${args.now}`);

  const items = [];
  const skillDirs = walkDirs(skillsRoot).filter((d) => exists(path.join(d, "metadata.yaml")));
  for (const skillDir of skillDirs) {
    const metadataPath = path.join(skillDir, "metadata.yaml");
    const meta = readText(metadataPath);
    const rel = path.relative(skillsRoot, skillDir).split(path.sep).join("/");
    const id = parseSimpleYamlScalar(meta, "id") || rel;
    const level = String(parseSimpleYamlScalar(meta, "level") || "bronze").trim().toLowerCase();
    const lastVerifiedRaw = parseSimpleYamlScalar(meta, "last_verified") || "";
    const tags = parseInlineYamlList(parseSimpleYamlScalar(meta, "tags"));

    const lastDt = lastVerifiedRaw ? parseYmd(lastVerifiedRaw) : null;
    const daysSince = lastDt ? daysBetweenUtc(nowDt, lastDt) : null;

    const archived = tags.includes("archived");
    const staleEligible = level === "silver" || level === "gold";
    const stale = staleEligible && !archived && (daysSince === null || daysSince > args.staleDays);
    const toArchive = staleEligible && !archived && (daysSince === null || daysSince > args.archiveDays);

    let suggestedLevel = level;
    if (args.downgrade && stale && !toArchive) {
      if (level === "gold") suggestedLevel = "silver";
      else if (level === "silver") suggestedLevel = "bronze";
    }

    const nextTags = [...new Set(tags)];
    const actions = [];
    if (toArchive) {
      if (!nextTags.includes("archived")) nextTags.push("archived");
      actions.push("tag:archived");
    } else if (stale) {
      if (!nextTags.includes("stale")) nextTags.push("stale");
      actions.push("tag:stale");
    }
    if (suggestedLevel !== level) actions.push(`level:${level}->${suggestedLevel}`);

    if (args.apply && actions.length > 0) {
      let next = meta;
      if (nextTags.join(",") !== tags.join(",")) next = updateYamlScalar(next, "tags", formatInlineYamlList(nextTags));
      if (suggestedLevel !== level) next = updateYamlScalar(next, "level", suggestedLevel);
      fs.writeFileSync(metadataPath, next, "utf8");
    }

    items.push({
      id,
      rel_dir: rel,
      level,
      last_verified: lastVerifiedRaw || null,
      days_since_verified: daysSince,
      tags,
      status: archived ? "archived" : stale ? "stale" : "fresh",
      suggested: actions,
    });
  }

  const staleGold = items.filter((x) => x.status === "stale" && x.level === "gold").length;
  const staleSilver = items.filter((x) => x.status === "stale" && x.level === "silver").length;
  const archivedCount = items.filter((x) => x.status === "archived").length;
  const summary = {
    skills_total: items.length,
    stale_total: items.filter((x) => x.status === "stale").length,
    stale_gold: staleGold,
    stale_silver: staleSilver,
    archived_total: archivedCount,
    applied: Boolean(args.apply),
  };

  const report = {
    now: args.now,
    stale_days: args.staleDays,
    archive_days: args.archiveDays,
    summary,
    items: items.sort((a, b) => a.id.localeCompare(b.id)),
  };

  if (args.outPath) {
    const outPath = path.resolve(process.cwd(), args.outPath);
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    fs.writeFileSync(outPath, JSON.stringify(report, null, 2), "utf8");
  } else {
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  }

  if (args.failOnStaleGold && staleGold > 0) {
    console.error(`FAIL: stale gold skills detected (count=${staleGold}).`);
    process.exit(2);
  }
}

try {
  main();
} catch (e) {
  console.error(String(e && e.stack ? e.stack : e));
  process.exit(1);
}

