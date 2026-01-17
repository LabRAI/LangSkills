#!/usr/bin/env node
/* eslint-disable no-console */

const childProcess = require("child_process");
const path = require("path");

process.stdout.on("error", (err) => {
  if (err && err.code === "EPIPE") process.exit(0);
});

function usage(exitCode = 0) {
  const msg = `
Usage:
  node scripts/run-longrun.js --domain <domain> --run-id <run-id>
    [--days 90] [--pages-per-day 500] [--max-depth 2]
    [--runs-dir runs] [--cache-dir .cache/web]
    [--extract-per-day <n>] [--generate-per-day <n>]
    [--skills-out <dir>]
    [--dry-run]

What it does:
  - Translates (days, pages-per-day) into orchestrator flags:
    - --crawl-max-pages = pages-per-day
    - --extract-max-docs = extract-per-day (default: pages-per-day)
    - --cycle-sleep-ms = 86400000 (1 day)
    - --loop --max-cycles = days
  - Runs: node agents/orchestrator/run.js ...
`.trim();
  if (exitCode === 0) console.log(msg);
  else console.error(msg);
  process.exit(exitCode);
}

function parseArgs(argv) {
  const args = {
    domain: null,
    runId: null,
    days: 90,
    pagesPerDay: 500,
    maxDepth: 2,
    runsDir: "runs",
    cacheDir: ".cache/web",
    extractPerDay: null,
    generatePerDay: 0,
    skillsOut: "skills",
    dryRun: false,
  };

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--domain") {
      args.domain = argv[i + 1] || null;
      i++;
    } else if (a === "--run-id") {
      args.runId = argv[i + 1] || null;
      i++;
    } else if (a === "--days") {
      args.days = Number(argv[i + 1] || "90");
      i++;
    } else if (a === "--pages-per-day") {
      args.pagesPerDay = Number(argv[i + 1] || "500");
      i++;
    } else if (a === "--max-depth") {
      args.maxDepth = Number(argv[i + 1] || "2");
      i++;
    } else if (a === "--runs-dir") {
      args.runsDir = argv[i + 1] || args.runsDir;
      i++;
    } else if (a === "--cache-dir") {
      args.cacheDir = argv[i + 1] || args.cacheDir;
      i++;
    } else if (a === "--extract-per-day") {
      args.extractPerDay = Number(argv[i + 1] || "0");
      i++;
    } else if (a === "--generate-per-day") {
      args.generatePerDay = Number(argv[i + 1] || "0");
      i++;
    } else if (a === "--skills-out") {
      args.skillsOut = argv[i + 1] || args.skillsOut;
      i++;
    } else if (a === "--dry-run") {
      args.dryRun = true;
    } else if (a === "-h" || a === "--help") usage(0);
    else throw new Error(`Unknown arg: ${a}`);
  }

  if (!args.domain) usage(2);
  if (!args.runId) usage(2);
  if (!Number.isFinite(args.days) || args.days <= 0) throw new Error("Invalid --days");
  if (!Number.isFinite(args.pagesPerDay) || args.pagesPerDay <= 0) throw new Error("Invalid --pages-per-day");
  if (!Number.isFinite(args.maxDepth) || args.maxDepth < 0) throw new Error("Invalid --max-depth");
  if (args.extractPerDay == null) args.extractPerDay = args.pagesPerDay;
  if (!Number.isFinite(args.extractPerDay) || args.extractPerDay < 0) throw new Error("Invalid --extract-per-day");
  if (!Number.isFinite(args.generatePerDay) || args.generatePerDay < 0) throw new Error("Invalid --generate-per-day");
  return args;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const repoRoot = path.resolve(__dirname, "..");
  const orchestrator = path.join(repoRoot, "agents", "orchestrator", "run.js");

  const cmdArgs = [
    orchestrator,
    "--domain",
    args.domain,
    "--run-id",
    args.runId,
    "--runs-dir",
    args.runsDir,
    "--cache-dir",
    args.cacheDir,
    "--crawl-max-pages",
    String(args.pagesPerDay),
    "--crawl-max-depth",
    String(args.maxDepth),
    "--extract-max-docs",
    String(args.extractPerDay),
    "--generate-max-topics",
    String(args.generatePerDay),
    "--out",
    args.skillsOut,
    "--loop",
    "--max-cycles",
    String(args.days),
    "--cycle-sleep-ms",
    String(86_400_000),
  ];

  console.log(`[longrun] domain=${args.domain} run_id=${args.runId} days=${args.days} pages_per_day=${args.pagesPerDay}`);
  console.log(`[longrun] cmd: node ${cmdArgs.map((x) => JSON.stringify(x)).join(" ")}`);
  if (args.dryRun) return;

  const env = { ...process.env, GIT_TERMINAL_PROMPT: "0" };
  const r = childProcess.spawnSync(process.execPath, cmdArgs, {
    cwd: repoRoot,
    env,
    encoding: "utf8",
    stdio: "inherit",
    maxBuffer: 1024 * 1024 * 16,
  });
  process.exit(typeof r.status === "number" ? r.status : 1);
}

main();

