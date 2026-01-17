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

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function writeJsonAtomic(filePath, obj) {
  ensureDir(path.dirname(filePath));
  const tmp = `${filePath}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 2) + "\n", "utf8");
  fs.renameSync(tmp, filePath);
}

function normalizeUsage(u) {
  const obj = u && typeof u === "object" ? u : null;
  if (!obj) return null;
  const pt = Number(obj.prompt_tokens || 0);
  const ct = Number(obj.completion_tokens || 0);
  const tt = Number(obj.total_tokens || 0);
  if (!Number.isFinite(pt) && !Number.isFinite(ct) && !Number.isFinite(tt)) return null;
  return {
    prompt_tokens: Number.isFinite(pt) ? pt : 0,
    completion_tokens: Number.isFinite(ct) ? ct : 0,
    total_tokens: Number.isFinite(tt) ? tt : 0,
  };
}

function addUsage(a, b) {
  const ua = normalizeUsage(a) || { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 };
  const ub = normalizeUsage(b) || { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 };
  return {
    prompt_tokens: ua.prompt_tokens + ub.prompt_tokens,
    completion_tokens: ua.completion_tokens + ub.completion_tokens,
    total_tokens: ua.total_tokens + ub.total_tokens,
  };
}

function usage(exitCode = 0) {
  const msg = `
Usage:
  node scripts/closed-loop-summary.js --domain <domain> --run-id <id>
    [--runs-dir runs] [--out <skillsRoot>] [--skillgen-report <path>]
`.trim();
  if (exitCode === 0) console.log(msg);
  else console.error(msg);
  process.exit(exitCode);
}

function parseArgs(argv) {
  const args = {
    domain: null,
    runId: null,
    runsDir: "runs",
    out: null,
    skillgenReport: null,
  };

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--domain") {
      args.domain = argv[i + 1] || null;
      i++;
    } else if (a === "--run-id") {
      args.runId = argv[i + 1] || null;
      i++;
    } else if (a === "--runs-dir") {
      args.runsDir = argv[i + 1] || args.runsDir;
      i++;
    } else if (a === "--out") {
      args.out = argv[i + 1] || null;
      i++;
    } else if (a === "--skillgen-report") {
      args.skillgenReport = argv[i + 1] || null;
      i++;
    } else if (a === "-h" || a === "--help") usage(0);
    else throw new Error(`Unknown arg: ${a}`);
  }

  if (!args.domain) usage(2);
  if (!args.runId) usage(2);
  return args;
}

function rel(repoRoot, targetPath) {
  try {
    return path.relative(repoRoot, targetPath);
  } catch {
    return String(targetPath || "");
  }
}

function safeListResults(skillgenReport) {
  const results = skillgenReport && Array.isArray(skillgenReport.results) ? skillgenReport.results : [];
  return results.map((r) => ({
    id: r && r.id ? String(r.id) : "",
    title: r && r.title ? String(r.title) : "",
    status: r && r.status ? String(r.status) : "",
    topic: r && r.id ? String(r.id).split("/")[1] || "" : "",
    llm_usage: normalizeUsage(r && r.llm_usage ? r.llm_usage : null),
    skill_dir: r && r.skill_dir ? String(r.skill_dir) : "",
    skill_md: r && r.skill_md ? String(r.skill_md) : "",
    sources_md: r && r.sources_md ? String(r.sources_md) : "",
    llm_capture: r && r.llm_capture ? String(r.llm_capture) : "",
    materials_dir: r && r.materials_dir ? String(r.materials_dir) : "",
  }));
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const repoRoot = path.resolve(__dirname, "..");

  const runsRoot = path.isAbsolute(args.runsDir) ? args.runsDir : path.resolve(repoRoot, args.runsDir);
  const runDir = path.join(runsRoot, args.runId);

  const outDir = args.out
    ? (path.isAbsolute(args.out) ? args.out : path.resolve(repoRoot, args.out))
    : path.join(runDir, "skills");

  const candidatesPath = path.join(runDir, "candidates.jsonl");
  const curationPath = path.join(runDir, "curation.json");
  const curatorLlmCapturePath = path.join(runDir, "llm", "curate_proposals.json");
  const skillgenReportPath = args.skillgenReport
    ? (path.isAbsolute(args.skillgenReport) ? args.skillgenReport : path.resolve(repoRoot, args.skillgenReport))
    : path.join(runDir, "skillgen_report.json");
  const domainReadmePath = path.join(outDir, args.domain, "README.md");
  const logsDir = path.join(runDir, "logs");

  const curation = exists(curationPath) ? readJson(curationPath) : null;
  const curatorUsage = normalizeUsage(curation && curation.llm && curation.llm.usage ? curation.llm.usage : null);

  const curatorCapture = exists(curatorLlmCapturePath) ? readJson(curatorLlmCapturePath) : null;
  const curatorCaptureUsage = normalizeUsage(curatorCapture && curatorCapture.usage ? curatorCapture.usage : null);

  const skillgenReport = exists(skillgenReportPath) ? readJson(skillgenReportPath) : null;
  const skillgenTotalUsage = normalizeUsage(
    skillgenReport && skillgenReport.stats && skillgenReport.stats.llm_usage_total ? skillgenReport.stats.llm_usage_total : null,
  );

  let totalUsage = { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 };
  totalUsage = addUsage(totalUsage, curatorUsage || curatorCaptureUsage);
  totalUsage = addUsage(totalUsage, skillgenTotalUsage);

  const results = safeListResults(skillgenReport);

  const summary = {
    version: 1,
    domain: args.domain,
    run_id: args.runId,
    paths: {
      run_dir: rel(repoRoot, runDir),
      candidates_jsonl: exists(candidatesPath) ? rel(repoRoot, candidatesPath) : null,
      curation_json: exists(curationPath) ? rel(repoRoot, curationPath) : null,
      curator_llm_capture: exists(curatorLlmCapturePath) ? rel(repoRoot, curatorLlmCapturePath) : null,
      skillgen_report: exists(skillgenReportPath) ? rel(repoRoot, skillgenReportPath) : null,
      out: rel(repoRoot, outDir),
      domain_readme: exists(domainReadmePath) ? rel(repoRoot, domainReadmePath) : null,
      logs_dir: exists(logsDir) ? rel(repoRoot, logsDir) : null,
    },
    llm_usage: {
      curator: curatorUsage || curatorCaptureUsage,
      skillgen: skillgenTotalUsage,
      total: totalUsage,
    },
    skills: results,
  };

  const outPath = path.join(runDir, "closed_loop_report.json");
  writeJsonAtomic(outPath, summary);

  console.log(`[summary] run_id=${args.runId} domain=${args.domain}`);
  console.log(`[summary] run_dir: ${summary.paths.run_dir}`);
  if (summary.paths.candidates_jsonl) console.log(`[summary] candidates: ${summary.paths.candidates_jsonl}`);
  if (summary.paths.curation_json) console.log(`[summary] curation: ${summary.paths.curation_json}`);
  if (summary.paths.curator_llm_capture) console.log(`[summary] curator_llm_capture: ${summary.paths.curator_llm_capture}`);
  if (summary.paths.skillgen_report) console.log(`[summary] skillgen_report: ${summary.paths.skillgen_report}`);
  if (summary.paths.domain_readme) console.log(`[summary] domain_readme: ${summary.paths.domain_readme}`);
  if (summary.paths.logs_dir) console.log(`[summary] logs_dir: ${summary.paths.logs_dir}`);
  console.log(
    `[summary] tokens: curator=${summary.llm_usage.curator ? summary.llm_usage.curator.total_tokens : 0} skillgen=${summary.llm_usage.skillgen ? summary.llm_usage.skillgen.total_tokens : 0} total=${summary.llm_usage.total.total_tokens}`,
  );
  console.log("");

  const generated = results.filter((r) => r.status && r.status.startsWith("generated"));
  if (generated.length === 0) {
    console.log("[summary] no skills generated in this batch.");
  } else {
    console.log("[summary] generated skills (this batch):");
    for (const r of generated) {
      const tok = r.llm_usage && r.llm_usage.total_tokens != null ? ` tokens=${r.llm_usage.total_tokens}` : "";
      console.log(`- ${r.id} — ${r.title}${tok}`);
    }
  }

  console.log("");
  console.log(`[summary] report_json: ${rel(repoRoot, outPath)}`);
}

main();

