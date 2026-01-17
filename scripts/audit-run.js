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

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function writeText(filePath, text) {
  ensureDir(path.dirname(filePath));
  fs.writeFileSync(filePath, String(text || "").endsWith("\n") ? String(text) : `${text}\n`, "utf8");
}

function writeJsonAtomic(filePath, obj) {
  ensureDir(path.dirname(filePath));
  const tmp = `${filePath}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 2) + "\n", "utf8");
  fs.renameSync(tmp, filePath);
}

function usage(exitCode = 0) {
  const msg = `
Usage:
  node scripts/audit-run.js --run-id <id>
    [--runs-dir runs]
    [--skillgen-report <path>]
    [--out-dir <dir>]

What it does:
  - Reads a SkillGen batch report (default: runs/<run-id>/reports/skillgen.json)
  - Writes:
    - runs/<run-id>/reports/skill_locations.tsv   (every skill path + tokens + capture)
    - runs/<run-id>/reports/audit_run.json        (machine-readable audit)
    - runs/<run-id>/reports/audit_run.md          (human-readable audit)

Notes:
  - This script does NOT modify any skills; it only audits and summarizes.
`.trim();
  if (exitCode === 0) console.log(msg);
  else console.error(msg);
  process.exit(exitCode);
}

function sanitizeRunId(raw) {
  const v = String(raw || "").trim();
  if (!v) return "";
  const safe = v.replace(/[^A-Za-z0-9._-]/g, "-");
  return safe.replace(/-+/g, "-").replace(/^-+/, "").replace(/-+$/, "");
}

function parseArgs(argv) {
  const args = {
    runId: null,
    runsDir: "runs",
    skillgenReport: null,
    outDir: null,
  };

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--run-id") {
      args.runId = argv[i + 1] || null;
      i++;
    } else if (a === "--runs-dir") {
      args.runsDir = argv[i + 1] || args.runsDir;
      i++;
    } else if (a === "--skillgen-report") {
      args.skillgenReport = argv[i + 1] || null;
      i++;
    } else if (a === "--out-dir") {
      args.outDir = argv[i + 1] || null;
      i++;
    } else if (a === "-h" || a === "--help") usage(0);
    else throw new Error(`Unknown arg: ${a}`);
  }

  args.runId = args.runId ? sanitizeRunId(args.runId) : null;
  if (!args.runId) usage(2);
  return args;
}

function rel(repoRoot, absPath) {
  try {
    return path.relative(repoRoot, absPath).replace(/\\/g, "/");
  } catch {
    return String(absPath || "");
  }
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

function deriveSkillDirFromId({ runId, id, skillDir }) {
  if (skillDir) return skillDir;
  const parts = String(id || "").trim().replace(/\\/g, "/").split("/").filter(Boolean);
  if (parts.length < 3) return "";
  const domain = parts[0];
  const topic = parts.slice(1, -1).join("/");
  const slug = parts[parts.length - 1];
  return path.join("runs", runId, "skills", domain, topic, slug).replace(/\\/g, "/");
}

function findSkillgenReportPath({ repoRoot, runDir, explicitPath }) {
  if (explicitPath) {
    const abs = path.isAbsolute(explicitPath) ? explicitPath : path.resolve(repoRoot, explicitPath);
    if (!exists(abs)) throw new Error(`Missing --skillgen-report: ${abs}`);
    return abs;
  }

  const candidates = [
    path.join(runDir, "reports", "skillgen.json"), // closed-loop default
    path.join(runDir, "skillgen_report.json"), // direct skillgen default
    path.join(runDir, "reports", "skillgen_report.json"),
  ];
  for (const p of candidates) {
    if (exists(p)) return p;
  }

  throw new Error(`Could not find skillgen report under: ${runDir}`);
}

function inferOutRoot({ repoRoot, runDir, report, explicitOutDir }) {
  if (explicitOutDir) return path.isAbsolute(explicitOutDir) ? explicitOutDir : path.resolve(repoRoot, explicitOutDir);
  const defaultOut = path.join(runDir, "skills");
  if (exists(defaultOut)) return defaultOut;

  const results = Array.isArray(report && report.results) ? report.results : [];
  const domain = report && report.domain ? String(report.domain) : "";
  const sample = results.find((r) => r && r.skill_dir) || null;
  const sampleRel = sample && sample.skill_dir ? String(sample.skill_dir).replace(/\\/g, "/") : "";
  if (sampleRel && domain) {
    const idx = sampleRel.indexOf(`/skills/${domain}/`);
    if (idx >= 0) {
      const outRel = sampleRel.slice(0, idx + "/skills".length);
      return path.resolve(repoRoot, outRel);
    }
  }

  return defaultOut;
}

function safeReadCaptureError({ repoRoot, captureRelPath }) {
  const p = String(captureRelPath || "").trim().replace(/\\/g, "/");
  if (!p) return "";
  const abs = path.resolve(repoRoot, p);
  if (!exists(abs)) return "missing llm capture";
  try {
    const cap = readJson(abs);
    const err = cap && typeof cap.error === "string" ? cap.error.trim() : "";
    return err || "";
  } catch {
    return "failed to read llm capture json";
  }
}

function checkRequiredSkillArtifacts({ repoRoot, skillDirRel, status }) {
  if (!skillDirRel) return [];
  if (status === "skipped_exists") return [];
  const base = String(skillDirRel || "").replace(/\\/g, "/");
  const required = [
    path.join(base, "metadata.yaml"),
    path.join(base, "skill.md"),
    path.join(base, "library.md"),
    path.join(base, "reference", "sources.md"),
    path.join(base, "reference", "troubleshooting.md"),
    path.join(base, "reference", "edge-cases.md"),
    path.join(base, "reference", "examples.md"),
    path.join(base, "reference", "changelog.md"),
  ].map((p) => p.replace(/\\/g, "/"));

  const missing = [];
  for (const relPath of required) {
    if (!exists(path.resolve(repoRoot, relPath))) missing.push(relPath);
  }
  return missing;
}

function formatTsvRow(fields) {
  return fields.map((v) => String(v == null ? "" : v).replace(/\t/g, " ")).join("\t");
}

function mdCode(text) {
  return "`" + String(text || "").replace(/`/g, "\\`") + "`";
}

function mdHeading(text, level = 2) {
  const hashes = "#".repeat(Math.max(1, Math.min(6, Number(level) || 2)));
  return `${hashes} ${text}`;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const repoRoot = path.resolve(__dirname, "..");
  const runsRoot = path.isAbsolute(args.runsDir) ? args.runsDir : path.resolve(repoRoot, args.runsDir);
  const runDir = path.join(runsRoot, args.runId);

  const skillgenReportPath = findSkillgenReportPath({ repoRoot, runDir, explicitPath: args.skillgenReport });
  const report = readJson(skillgenReportPath);
  const outRoot = inferOutRoot({ repoRoot, runDir, report, explicitOutDir: args.outDir });

  const domain = report && report.domain ? String(report.domain) : "";
  const results = Array.isArray(report && report.results) ? report.results.slice() : [];
  results.sort((a, b) => String(a && a.id ? a.id : "").localeCompare(String(b && b.id ? b.id : "")));

  const logsDir = path.join(runDir, "logs");
  const expectedLogs = ["01_orchestrator.log", "02_curator.log", "03_skillgen.log", "04_validate.log", "05_summary.log"];
  const missingLogs = expectedLogs.filter((f) => !exists(path.join(logsDir, f)));

  const runDirRel = rel(repoRoot, runDir);
  const expectedRunArtifacts = [
    path.join(runDirRel, "crawl_state.json"),
    path.join(runDirRel, "candidates.jsonl"),
    path.join(runDirRel, "curation.json"),
    rel(repoRoot, skillgenReportPath),
    path.join(rel(repoRoot, outRoot), domain ? path.join(domain, "README.md") : ""),
    path.join(runDirRel, "closed_loop_report.json"),
  ]
    .filter(Boolean)
    .map((p) => String(p).replace(/\\/g, "/"));
  const missingRunArtifacts = expectedRunArtifacts.filter((p) => !exists(path.resolve(repoRoot, p)));

  const statusCounts = {};
  const llmErrors = [];
  const missingSkillArtifacts = [];

  const tsvLines = [];
  tsvLines.push(
    [
      "id",
      "status",
      "tokens_total",
      "skill_dir_rel",
      "skill_dir_abs",
      "skill_md_rel",
      "sources_md_rel",
      "llm_capture_rel",
      "materials_dir_rel",
      "llm_error",
    ].join("\t"),
  );

  for (const r of results) {
    const id = String(r && r.id ? r.id : "").trim();
    const status = String(r && r.status ? r.status : "").trim();
    statusCounts[status] = (statusCounts[status] || 0) + 1;

    const usage = normalizeUsage(r && r.llm_usage ? r.llm_usage : null);
    const tokensTotal = usage && usage.total_tokens != null ? String(usage.total_tokens) : "0";

    const skillDirRel = deriveSkillDirFromId({ runId: args.runId, id, skillDir: r && r.skill_dir ? String(r.skill_dir) : "" });
    const skillDirAbs = skillDirRel ? path.resolve(repoRoot, skillDirRel) : "";
    const skillMdRel = String(r && r.skill_md ? r.skill_md : skillDirRel ? path.join(skillDirRel, "skill.md") : "").replace(/\\/g, "/");
    const sourcesMdRel = String(r && r.sources_md ? r.sources_md : skillDirRel ? path.join(skillDirRel, "reference", "sources.md") : "").replace(
      /\\/g,
      "/",
    );
    const llmCaptureRel = String(
      r && r.llm_capture ? r.llm_capture : skillDirRel ? path.join(skillDirRel, "reference", "llm", "generate_skill.json") : "",
    ).replace(/\\/g, "/");
    const materialsDirRel = String(
      r && r.materials_dir ? r.materials_dir : skillDirRel ? path.join(skillDirRel, "reference", "materials") : "",
    ).replace(/\\/g, "/");

    const llmError = status === "generated_with_llm_error" || status === "error" ? safeReadCaptureError({ repoRoot, captureRelPath: llmCaptureRel }) : "";
    if (llmError) llmErrors.push({ id, status, error: llmError, llm_capture: llmCaptureRel || null });

    const missing = checkRequiredSkillArtifacts({ repoRoot, skillDirRel, status });
    if (missing.length > 0) missingSkillArtifacts.push({ id, status, skill_dir: skillDirRel || null, missing });

    tsvLines.push(
      formatTsvRow([
        id,
        status,
        tokensTotal,
        skillDirRel,
        skillDirAbs,
        skillMdRel,
        sourcesMdRel,
        llmCaptureRel,
        materialsDirRel,
        llmError,
      ]),
    );
  }

  const outReportsDir = path.join(runDir, "reports");
  ensureDir(outReportsDir);

  const skillLocationsPath = path.join(outReportsDir, "skill_locations.tsv");
  writeText(skillLocationsPath, tsvLines.join("\n"));

  const audit = {
    version: 1,
    run_id: args.runId,
    generated_at: new Date().toISOString(),
    paths: {
      run_dir: rel(repoRoot, runDir),
      skillgen_report: rel(repoRoot, skillgenReportPath),
      out: rel(repoRoot, outRoot),
      logs_dir: rel(repoRoot, logsDir),
      skill_locations_tsv: rel(repoRoot, skillLocationsPath),
    },
    stats: {
      total_results: results.length,
      status_counts: statusCounts,
      llm_errors_total: llmErrors.length,
      missing_skill_artifacts_total: missingSkillArtifacts.length,
      missing_run_artifacts_total: missingRunArtifacts.length,
      missing_logs_total: missingLogs.length,
    },
    missing_run_artifacts: missingRunArtifacts,
    missing_logs: missingLogs,
    llm_errors: llmErrors,
    missing_skill_artifacts: missingSkillArtifacts,
  };

  const auditJsonPath = path.join(outReportsDir, "audit_run.json");
  writeJsonAtomic(auditJsonPath, audit);

  const md = [];
  md.push(mdHeading(`Run Audit: ${args.runId}`, 1));
  md.push("");
  md.push(`- skillgen_report: ${mdCode(audit.paths.skillgen_report)}`);
  md.push(`- out: ${mdCode(audit.paths.out)}`);
  md.push(`- skill_locations: ${mdCode(audit.paths.skill_locations_tsv)}`);
  md.push(`- logs_dir: ${mdCode(audit.paths.logs_dir)}`);
  md.push("");
  md.push(mdHeading("Status Counts", 2));
  md.push("");
  for (const [k, v] of Object.entries(statusCounts).sort((a, b) => a[0].localeCompare(b[0]))) {
    md.push(`- ${k}: ${v}`);
  }
  md.push("");
  md.push(mdHeading("Errors", 2));
  md.push("");
  if (llmErrors.length === 0 && missingRunArtifacts.length === 0 && missingLogs.length === 0 && missingSkillArtifacts.length === 0) {
    md.push("- None");
  } else {
    if (missingRunArtifacts.length > 0) {
      md.push(mdHeading("Missing Run Artifacts", 3));
      for (const p of missingRunArtifacts) md.push(`- ${mdCode(p)}`);
      md.push("");
    }
    if (missingLogs.length > 0) {
      md.push(mdHeading("Missing Logs", 3));
      for (const p of missingLogs) md.push(`- ${mdCode(p)}`);
      md.push("");
    }
    if (missingSkillArtifacts.length > 0) {
      md.push(mdHeading("Missing Skill Artifacts", 3));
      for (const e of missingSkillArtifacts.slice(0, 50)) {
        md.push(`- ${mdCode(e.id)} (${e.status}): missing ${e.missing.map(mdCode).join(", ")}`);
      }
      if (missingSkillArtifacts.length > 50) md.push(`- ... plus ${missingSkillArtifacts.length - 50} more`);
      md.push("");
    }
    if (llmErrors.length > 0) {
      md.push(mdHeading("LLM Errors", 3));
      for (const e of llmErrors) {
        md.push(`- ${mdCode(e.id)}: ${e.error || "(no error message)"} (capture: ${mdCode(e.llm_capture || "null")})`);
      }
      md.push("");
    }
  }

  const auditMdPath = path.join(outReportsDir, "audit_run.md");
  writeText(auditMdPath, md.join("\n"));

  console.log("[audit] ok");
  console.log(`- run_id: ${args.runId}`);
  console.log(`- report: ${rel(repoRoot, skillgenReportPath)}`);
  console.log(`- out: ${rel(repoRoot, outRoot)}`);
  console.log(`- skill_locations: ${rel(repoRoot, skillLocationsPath)}`);
  console.log(`- audit_md: ${rel(repoRoot, auditMdPath)}`);
  console.log(`- audit_json: ${rel(repoRoot, auditJsonPath)}`);
  console.log(`- status_counts: ${JSON.stringify(statusCounts)}`);
  if (llmErrors.length > 0) console.log(`- llm_errors: ${llmErrors.length}`);
  if (missingRunArtifacts.length > 0) console.log(`- missing_run_artifacts: ${missingRunArtifacts.length}`);
  if (missingLogs.length > 0) console.log(`- missing_logs: ${missingLogs.length}`);
  if (missingSkillArtifacts.length > 0) console.log(`- missing_skill_artifacts: ${missingSkillArtifacts.length}`);
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
