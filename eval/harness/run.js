#!/usr/bin/env node
/* eslint-disable no-console */

const childProcess = require("child_process");
const fs = require("fs");
const path = require("path");

function run(cmd, args, options = {}) {
  const p = childProcess.spawnSync(cmd, args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    ...options,
  });
  return {
    status: typeof p.status === "number" ? p.status : 1,
    stdout: p.stdout || "",
    stderr: p.stderr || "",
  };
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

function sectionBody(md, headingRe) {
  const m = String(md || "").match(new RegExp(`^##\\s+${headingRe}.*$`, "m"));
  if (!m) return "";
  const start = md.indexOf(m[0]) + m[0].length;
  const rest = md.slice(start);
  const nextIdx = rest.search(/^##\s+/m);
  return (nextIdx === -1 ? rest : rest.slice(0, nextIdx)).trim();
}

function countMatches(text, re) {
  const m = String(text || "").match(re);
  return m ? m.length : 0;
}

function median(nums) {
  const list = (nums || []).filter((n) => Number.isFinite(n)).sort((a, b) => a - b);
  if (list.length === 0) return null;
  const mid = Math.floor(list.length / 2);
  if (list.length % 2 === 1) return list[mid];
  return Math.round((list[mid - 1] + list[mid]) / 2);
}

function parseArgs(argv) {
  const out = {
    skillsRoot: "skills",
    outJson: "eval/reports/latest/report.json",
    outMd: "eval/reports/latest/report.md",
    tasksPath: null,
    maxTasks: 50,
    staleDays: 90,
    now: null,
    skipValidator: false,
    failOnStaleGold: false,
  };

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--skills-root") {
      out.skillsRoot = argv[i + 1] || out.skillsRoot;
      i++;
    } else if (a === "--out") {
      out.outJson = argv[i + 1] || out.outJson;
      i++;
    } else if (a === "--out-md") {
      out.outMd = argv[i + 1] || out.outMd;
      i++;
    } else if (a === "--tasks") {
      out.tasksPath = argv[i + 1] || null;
      i++;
    } else if (a === "--max-tasks") {
      out.maxTasks = Number(argv[i + 1] || out.maxTasks);
      i++;
    } else if (a === "--stale-days") {
      out.staleDays = Number(argv[i + 1] || out.staleDays);
      i++;
    } else if (a === "--now") {
      out.now = String(argv[i + 1] || "").trim();
      i++;
    } else if (a === "--skip-validator") {
      out.skipValidator = true;
    } else if (a === "--fail-on-stale-gold") {
      out.failOnStaleGold = true;
    } else if (a === "-h" || a === "--help") {
      console.log(
        [
          "Usage: node eval/harness/run.js [--skills-root skills] [--out <report.json>] [--out-md <report.md>] [--tasks <file-or-dir>] [--max-tasks N] [--stale-days N] [--now YYYY-MM-DD] [--skip-validator] [--fail-on-stale-gold]",
          "",
          "Runs an offline eval that measures coverage/freshness and performs a small regression set (default: all gold skills).",
        ].join("\n"),
      );
      process.exit(0);
    }
  }

  if (!out.now) out.now = new Date().toISOString().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(out.now)) throw new Error(`--now must be YYYY-MM-DD (got: ${out.now})`);
  if (!Number.isFinite(out.maxTasks) || out.maxTasks < 1) throw new Error("--max-tasks must be >= 1");
  if (!Number.isFinite(out.staleDays) || out.staleDays < 1) throw new Error("--stale-days must be >= 1");
  return out;
}

function loadTaskIds(tasksPath, skillsById) {
  if (!tasksPath) return null;
  const p = path.resolve(tasksPath);
  if (!exists(p)) throw new Error(`Missing tasks path: ${p}`);

  const files = [];
  const stat = fs.statSync(p);
  if (stat.isDirectory()) {
    for (const f of fs.readdirSync(p)) {
      if (!f.endsWith(".json")) continue;
      files.push(path.join(p, f));
    }
  } else {
    files.push(p);
  }

  const ids = [];
  for (const file of files) {
    const raw = JSON.parse(readText(file));
    const list = Array.isArray(raw) ? raw : Array.isArray(raw && raw.tasks) ? raw.tasks : [];
    for (const item of list) {
      if (typeof item === "string") ids.push(item);
      else if (item && typeof item.id === "string") ids.push(item.id);
    }
  }

  const dedup = [...new Set(ids.map((x) => x.trim()).filter(Boolean))];
  return dedup.filter((id) => skillsById.has(id));
}

function main() {
  const repoRoot = path.resolve(__dirname, "../..");
  const args = parseArgs(process.argv.slice(2));
  const skillsRoot = path.resolve(repoRoot, args.skillsRoot);
  if (!exists(skillsRoot)) throw new Error(`Missing skills root: ${skillsRoot}`);

  const nowDt = parseYmd(args.now);
  if (!nowDt) throw new Error(`Invalid --now: ${args.now}`);

  let validator = { ran: false, ok: true, stdout: "", stderr: "" };
  if (!args.skipValidator) {
    const r = run(
      process.execPath,
      [path.join(repoRoot, "scripts", "validate-skills.js"), "--skills-root", skillsRoot, "--strict"],
      { cwd: repoRoot },
    );
    validator = { ran: true, ok: r.status === 0, stdout: r.stdout.trim(), stderr: r.stderr.trim() };
  }

  const skillDirs = walkDirs(skillsRoot).filter((d) => exists(path.join(d, "metadata.yaml")));
  const skills = [];
  const skillsById = new Map();

  for (const dirPath of skillDirs) {
    const rel = path.relative(skillsRoot, dirPath).split(path.sep).join("/");
    const meta = readText(path.join(dirPath, "metadata.yaml"));
    const id = parseSimpleYamlScalar(meta, "id") || rel;
    const level = String(parseSimpleYamlScalar(meta, "level") || "bronze").trim().toLowerCase();
    const domain = String(parseSimpleYamlScalar(meta, "domain") || "").trim() || rel.split("/")[0];
    const risk = String(parseSimpleYamlScalar(meta, "risk_level") || "low").trim().toLowerCase();
    const lastVerifiedRaw = parseSimpleYamlScalar(meta, "last_verified") || null;
    const lastDt = lastVerifiedRaw ? parseYmd(lastVerifiedRaw) : null;
    const daysSince = lastDt ? daysBetweenUtc(nowDt, lastDt) : null;

    const skillPath = path.join(dirPath, "skill.md");
    const md = exists(skillPath) ? readText(skillPath) : "";
    const stepsBody = sectionBody(md, "Steps\\b");
    const stepsCount = countMatches(stepsBody, /^\s*\d+\.\s+/gm);

    const sourcesBody = sectionBody(md, "Sources\\b");
    const sourcesCount = countMatches(sourcesBody, /^\s*-\s*\[\d+\]\s+/gm);

    const s = {
      id,
      rel_dir: rel,
      domain,
      level,
      risk_level: risk,
      last_verified: lastVerifiedRaw,
      days_since_verified: daysSince,
      steps_count: stepsCount,
      sources_count: sourcesCount,
    };
    skills.push(s);
    skillsById.set(id, s);
  }

  const byLevel = { bronze: 0, silver: 0, gold: 0 };
  const byRisk = { low: 0, medium: 0, high: 0 };
  const byDomain = {};
  for (const s of skills) {
    if (byLevel[s.level] !== undefined) byLevel[s.level]++;
    else byLevel.bronze++;

    if (byRisk[s.risk_level] !== undefined) byRisk[s.risk_level]++;
    else byRisk.low++;

    byDomain[s.domain] = (byDomain[s.domain] || 0) + 1;
  }

  const stale = skills.filter(
    (s) => (s.level === "silver" || s.level === "gold") && (s.days_since_verified === null || s.days_since_verified > args.staleDays),
  );
  const staleGold = stale.filter((s) => s.level === "gold");

  let taskIds = loadTaskIds(args.tasksPath, skillsById);
  if (!taskIds) {
    taskIds = skills.filter((s) => s.level === "gold").map((s) => s.id);
    if (taskIds.length === 0) taskIds = skills.slice(0, Math.min(10, skills.length)).map((s) => s.id);
  }
  taskIds = taskIds.slice(0, Math.min(args.maxTasks, taskIds.length));

  const tasks = [];
  for (const id of taskIds) {
    const s = skillsById.get(id);
    if (!s) {
      tasks.push({ id, ok: false, reason: "missing-skill" });
      continue;
    }
    const ok = s.steps_count > 0 && s.steps_count <= 12 && s.sources_count >= 3;
    const reason = ok ? "" : `bad-structure(steps=${s.steps_count},sources=${s.sources_count})`;
    tasks.push({ id, ok, reason });
  }

  const passed = tasks.filter((t) => t.ok).length;
  const stepsMedian = median(tasks.map((t) => (skillsById.get(t.id) ? skillsById.get(t.id).steps_count : null)));

  const report = {
    meta: {
      generated_at: new Date().toISOString(),
      now: args.now,
      skills_root: skillsRoot,
      version: 1,
    },
    gate: {
      validator,
    },
    tasks: {
      total: tasks.length,
      passed,
      success_rate: tasks.length ? passed / tasks.length : 0,
      failures: tasks.filter((t) => !t.ok),
    },
    metrics: {
      skills: {
        total: skills.length,
        by_level: byLevel,
        by_risk: byRisk,
        by_domain: byDomain,
      },
      freshness: {
        stale_days: args.staleDays,
        stale_total: stale.length,
        stale_gold: staleGold.length,
      },
      steps: {
        median: stepsMedian,
      },
    },
  };

  const outJson = path.resolve(repoRoot, args.outJson);
  fs.mkdirSync(path.dirname(outJson), { recursive: true });
  fs.writeFileSync(outJson, JSON.stringify(report, null, 2), "utf8");

  const outMd = path.resolve(repoRoot, args.outMd);
  fs.mkdirSync(path.dirname(outMd), { recursive: true });
  const md = [
    "# Eval Report",
    "",
    `- Now: \`${args.now}\``,
    `- Skills total: **${skills.length}** (bronze=${byLevel.bronze}, silver=${byLevel.silver}, gold=${byLevel.gold})`,
    `- Freshness: stale(silver/gold, >${args.staleDays}d) = **${stale.length}** (gold=${staleGold.length})`,
    `- Tasks: **${passed}/${tasks.length}** passed (success_rate=${(report.tasks.success_rate * 100).toFixed(1)}%)`,
    `- Median steps (tasks): **${stepsMedian === null ? "n/a" : stepsMedian}**`,
    `- Strict validator: **${validator.ran ? (validator.ok ? "PASS" : "FAIL") : "SKIPPED"}**`,
    "",
  ].join("\n");
  fs.writeFileSync(outMd, md, "utf8");

  process.stdout.write(`Wrote ${outJson}\n`);

  if (args.failOnStaleGold && staleGold.length > 0) {
    console.error(`FAIL: stale gold skills detected (count=${staleGold.length}).`);
    process.exit(2);
  }
  if (validator.ran && !validator.ok) process.exit(2);
  if (tasks.some((t) => !t.ok)) process.exit(2);
}

try {
  main();
} catch (e) {
  console.error(String(e && e.stack ? e.stack : e));
  process.exit(1);
}
