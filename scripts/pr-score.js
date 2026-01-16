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

function parseArgs(argv) {
  const out = {
    base: null,
    head: null,
    paths: [],
    outJson: null,
    outMd: null,
    validateStrict: true,
  };

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--base") {
      out.base = argv[i + 1] || null;
      i++;
    } else if (a === "--head") {
      out.head = argv[i + 1] || null;
      i++;
    } else if (a === "--paths") {
      const raw = argv[i + 1] || "";
      out.paths = raw
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean);
      i++;
    } else if (a === "--out-json") {
      out.outJson = argv[i + 1] || null;
      i++;
    } else if (a === "--out-md") {
      out.outMd = argv[i + 1] || null;
      i++;
    } else if (a === "--skip-strict") {
      out.validateStrict = false;
    } else if (a === "-h" || a === "--help") {
      console.log(
        [
          "Usage: node scripts/pr-score.js [--base <ref>] [--head <ref>] [--paths a,b,c] [--out-json <path>] [--out-md <path>] [--skip-strict]",
          "",
          "If --base/--head are provided, detects changed files via git diff.",
          "Otherwise, uses --paths (comma-separated).",
        ].join("\n"),
      );
      process.exit(0);
    }
  }

  return out;
}

function collectChangedFiles(args, repoRoot) {
  if (args.base && args.head) {
    const r = run("git", ["diff", "--name-only", `${args.base}...${args.head}`], { cwd: repoRoot });
    if (r.status !== 0) throw new Error(r.stderr || r.stdout || "git diff failed");
    return r.stdout
      .split(/\r?\n/)
      .map((x) => x.trim())
      .filter(Boolean);
  }
  return args.paths;
}

function skillIdFromPath(p) {
  const norm = String(p || "").replace(/\\/g, "/");
  const m = norm.match(/^skills\/([^/]+)\/([^/]+)\/([^/]+)\//);
  if (!m) return null;
  return `${m[1]}/${m[2]}/${m[3]}`;
}

function main() {
  const repoRoot = path.resolve(__dirname, "..");
  const args = parseArgs(process.argv.slice(2));

  const changedFiles = collectChangedFiles(args, repoRoot);
  const skillIds = [...new Set(changedFiles.map(skillIdFromPath).filter(Boolean))].sort();

  let strict = { ran: false, ok: true, stdout: "", stderr: "" };
  if (args.validateStrict) {
    const r = run(process.execPath, [path.join(repoRoot, "scripts", "validate-skills.js"), "--strict"], { cwd: repoRoot });
    strict = { ran: true, ok: r.status === 0, stdout: r.stdout.trim(), stderr: r.stderr.trim() };
  }

  const score = strict.ok ? 100 : 0;
  const labels = strict.ok ? ["bot:pass"] : ["bot:needs-fix"];

  const report = {
    meta: {
      base: args.base,
      head: args.head,
      changed_files: changedFiles.length,
      generated_at: new Date().toISOString(),
    },
    gate: {
      strict_validator: strict,
    },
    changed_skills: skillIds,
    score,
    labels,
  };

  const outJson = args.outJson ? path.resolve(repoRoot, args.outJson) : null;
  if (outJson) {
    fs.mkdirSync(path.dirname(outJson), { recursive: true });
    fs.writeFileSync(outJson, JSON.stringify(report, null, 2), "utf8");
  } else {
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  }

  const outMd = args.outMd ? path.resolve(repoRoot, args.outMd) : null;
  if (outMd) {
    const changedSkillsMd = skillIds.length ? skillIds.map((x) => "`" + x + "`").join(", ") : "(none)";
    const labelsMd = labels.map((x) => "`" + x + "`").join(", ");
    const md = [
      "# PR Score",
      "",
      `- Score: **${score}**`,
      `- Strict validator: **${strict.ok ? "PASS" : "FAIL"}**`,
      `- Changed skills: ${changedSkillsMd}`,
      `- Suggested labels: ${labelsMd}`,
      "",
    ].join("\n");
    fs.mkdirSync(path.dirname(outMd), { recursive: true });
    fs.writeFileSync(outMd, md, "utf8");
  }

  process.exit(strict.ok ? 0 : 2);
}

try {
  main();
} catch (e) {
  console.error(String(e && e.stack ? e.stack : e));
  process.exit(1);
}
