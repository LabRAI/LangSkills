#!/usr/bin/env node
/* eslint-disable no-console */

const crypto = require("crypto");
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

function readText(filePath) {
  return fs.readFileSync(filePath, "utf8");
}

function writeText(filePath, text) {
  ensureDir(path.dirname(filePath));
  fs.writeFileSync(filePath, String(text || "").endsWith("\n") ? String(text) : `${text}\n`, "utf8");
}

function writeJsonAtomic(filePath, obj) {
  ensureDir(path.dirname(filePath));
  const tmp = `${filePath}.${crypto.randomBytes(4).toString("hex")}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 2) + "\n", "utf8");
  fs.renameSync(tmp, filePath);
}

function stripBom(text) {
  if (!text) return text;
  return text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
}

function sanitizeRunId(raw) {
  const v = String(raw || "").trim();
  if (!v) return "";
  const safe = v.replace(/[^A-Za-z0-9._-]/g, "-");
  return safe.replace(/-+/g, "-").replace(/^-+/, "").replace(/-+$/, "");
}

function rel(repoRoot, absPath) {
  try {
    return path.relative(repoRoot, absPath).replace(/\\/g, "/");
  } catch {
    return String(absPath || "");
  }
}

function usage(exitCode = 0) {
  const msg = `
Usage:
  node scripts/audit-skill-quality.js --run-id <id> [--runs-dir runs]
  node scripts/audit-skill-quality.js --skills-root <dir> [--out-dir <dir>]

What it checks (heuristics; NOT a hard gate by default):
  - Steps: count, average length, inline-code presence
  - “Too generic” steps ratio (e.g., 仅“阅读/了解/熟悉/总结”)
  - URLs inside steps (often indicates low-signal writing)
  - For linux: whether library.md contains any bash commands

Outputs:
  - <out-dir>/skill_quality_audit.md
  - <out-dir>/skill_quality_audit.json
  - <out-dir>/skill_quality_audit.tsv
`.trim();
  if (exitCode === 0) console.log(msg);
  else console.error(msg);
  process.exit(exitCode);
}

function parseArgs(argv) {
  const args = {
    runId: null,
    runsDir: "runs",
    skillsRoot: null,
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
    } else if (a === "--skills-root") {
      args.skillsRoot = argv[i + 1] || null;
      i++;
    } else if (a === "--out-dir") {
      args.outDir = argv[i + 1] || null;
      i++;
    } else if (a === "-h" || a === "--help") usage(0);
    else throw new Error(`Unknown arg: ${a}`);
  }

  if (args.runId) args.runId = sanitizeRunId(args.runId);
  if (!args.runId && !args.skillsRoot) usage(2);
  return args;
}

function walkSkillDirs(skillsRoot) {
  const out = [];
  const stack = [skillsRoot];
  while (stack.length > 0) {
    const current = stack.pop();
    let entries = [];
    try {
      entries = fs.readdirSync(current, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const ent of entries) {
      const p = path.join(current, ent.name);
      if (ent.isDirectory()) {
        if (exists(path.join(p, "metadata.yaml"))) out.push(p);
        stack.push(p);
      }
    }
  }
  return out;
}

function parseSimpleYamlScalar(text, key) {
  const re = new RegExp(`^${key}:\\s*(.+?)\\s*$`, "m");
  const m = String(text || "").match(re);
  if (!m) return null;
  let value = m[1].trim();
  if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) value = value.slice(1, -1);
  return value;
}

function sectionBody(markdown, headingPrefixRe) {
  const headingLineRe = new RegExp(`^##\\s+${headingPrefixRe.source}.*$`, "m");
  const m = headingLineRe.exec(markdown);
  if (!m) return null;
  let rest = markdown.slice(m.index + m[0].length);
  if (rest.startsWith("\r\n")) rest = rest.slice(2);
  else if (rest.startsWith("\n")) rest = rest.slice(1);
  const nextHeadingIdx = rest.search(/^##\s+/m);
  return nextHeadingIdx === -1 ? rest : rest.slice(0, nextHeadingIdx);
}

function extractStepLines(stepsBody) {
  const body = String(stepsBody || "").replace(/\r\n/g, "\n");
  const lines = body.split("\n");
  const out = [];
  for (const line of lines) {
    const m = line.match(/^\s*(\d+)\.\s+(.*)\s*$/);
    if (!m) continue;
    out.push(String(m[2] || "").trim());
  }
  return out;
}

function stripCites(stepText) {
  return String(stepText || "").replace(/\[\[(.+?)\]\]\s*$/g, "").trim();
}

function countInlineCode(stepText) {
  const t = String(stepText || "");
  const m = t.match(/`[^`]+`/g);
  return m ? m.length : 0;
}

function looksGenericStep(stepText) {
  const t = stripCites(stepText);
  if (!t) return true;
  const starts = [
    /^阅读/,
    /^查看/,
    /^访问/,
    /^了解/,
    /^熟悉/,
    /^总结/,
    /^确保/,
    /^根据需要/,
    /^参考/,
    /^学习/,
    /^浏览/,
    /^read\b/i,
    /^visit\b/i,
    /^review\b/i,
    /^understand\b/i,
    /^summarize\b/i,
    /^ensure\b/i,
  ];
  return starts.some((re) => re.test(t));
}

function extractBashCommandsFromLibrary(libraryMd) {
  const md = String(libraryMd || "").replace(/\r\n/g, "\n");
  const m = md.match(/```bash\n([\s\S]*?)\n```/);
  if (!m) return [];
  const body = m[1] || "";
  const lines = body
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("#"));
  return lines;
}

function mdHeading(text, level = 2) {
  const hashes = "#".repeat(Math.max(1, Math.min(6, Number(level) || 2)));
  return `${hashes} ${text}`;
}

function mdCode(text) {
  return "`" + String(text || "").replace(/`/g, "\\`") + "`";
}

function formatTsvRow(fields) {
  return fields.map((v) => String(v == null ? "" : v).replace(/\t/g, " ")).join("\t");
}

function titleLooksLikeLegalOrMeta(title) {
  const t = String(title || "").toLowerCase();
  return /(privacy|terms of service|gdpr|cookie|trademark|code of conduct|legal)/i.test(t);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const repoRoot = path.resolve(__dirname, "..");

  let skillsRootAbs = null;
  let outDirAbs = null;
  let runDirAbs = null;

  if (args.runId) {
    const runsRoot = path.isAbsolute(args.runsDir) ? args.runsDir : path.resolve(repoRoot, args.runsDir);
    runDirAbs = path.join(runsRoot, args.runId);
    skillsRootAbs = path.join(runDirAbs, "skills");
    outDirAbs = path.join(runDirAbs, "reports");
  } else {
    skillsRootAbs = path.isAbsolute(args.skillsRoot) ? args.skillsRoot : path.resolve(repoRoot, args.skillsRoot);
    outDirAbs = args.outDir ? (path.isAbsolute(args.outDir) ? args.outDir : path.resolve(repoRoot, args.outDir)) : path.join(repoRoot, "reports");
  }

  if (!exists(skillsRootAbs)) throw new Error(`Missing skills root: ${skillsRootAbs}`);

  const outMd = path.join(outDirAbs, "skill_quality_audit.md");
  const outJson = path.join(outDirAbs, "skill_quality_audit.json");
  const outTsv = path.join(outDirAbs, "skill_quality_audit.tsv");

  const skillDirs = walkSkillDirs(skillsRootAbs);
  const rows = [];
  const summaries = [];

  const totals = {
    skills: 0,
    steps: 0,
    steps_with_code: 0,
    steps_generic: 0,
    skills_linux_no_bash_commands: 0,
    skills_steps_mostly_generic: 0,
    skills_steps_no_inline_code: 0,
    skills_steps_has_url: 0,
    skills_title_looks_legal: 0,
  };

  for (const dir of skillDirs) {
    const metaPath = path.join(dir, "metadata.yaml");
    const skillPath = path.join(dir, "skill.md");
    const libraryPath = path.join(dir, "library.md");
    if (!exists(metaPath) || !exists(skillPath)) continue;

    const meta = stripBom(readText(metaPath));
    const id = parseSimpleYamlScalar(meta, "id") || rel(skillsRootAbs, dir);
    const domain = String(id).split("/")[0] || "";
    const title = parseSimpleYamlScalar(meta, "title") || "";

    const skillMd = readText(skillPath);
    const stepsBody = sectionBody(skillMd, /Steps\b/);
    const stepLines = extractStepLines(stepsBody);
    const stepCount = stepLines.length;

    let stepCode = 0;
    let stepGeneric = 0;
    let stepHasUrl = 0;
    let avgLen = 0;
    for (const s of stepLines) {
      const clean = stripCites(s);
      avgLen += clean.length;
      if (countInlineCode(clean) > 0) stepCode++;
      if (looksGenericStep(clean)) stepGeneric++;
      if (/https?:\/\//i.test(clean)) stepHasUrl++;
    }
    avgLen = stepCount ? avgLen / stepCount : 0;

    const libraryMd = exists(libraryPath) ? readText(libraryPath) : "";
    const bashCmds = extractBashCommandsFromLibrary(libraryMd);
    const linuxNoCmds = domain === "linux" && bashCmds.length === 0;

    const genericRatio = stepCount ? stepGeneric / stepCount : 1;
    const mostlyGeneric = stepCount >= 3 && genericRatio >= 0.5;
    const noInlineCode = stepCount >= 3 && stepCode === 0;
    const titleLegal = titleLooksLikeLegalOrMeta(title);

    const flags = [];
    if (linuxNoCmds) flags.push("linux_no_bash_commands");
    if (mostlyGeneric) flags.push("steps_mostly_generic");
    if (noInlineCode) flags.push("steps_no_inline_code");
    if (stepHasUrl > 0) flags.push("steps_has_url");
    if (titleLegal) flags.push("title_looks_legal");

    totals.skills += 1;
    totals.steps += stepCount;
    totals.steps_with_code += stepCode;
    totals.steps_generic += stepGeneric;
    if (linuxNoCmds) totals.skills_linux_no_bash_commands += 1;
    if (mostlyGeneric) totals.skills_steps_mostly_generic += 1;
    if (noInlineCode) totals.skills_steps_no_inline_code += 1;
    if (stepHasUrl > 0) totals.skills_steps_has_url += 1;
    if (titleLegal) totals.skills_title_looks_legal += 1;

    const relSkillDir = rel(repoRoot, dir);
    rows.push({
      id,
      domain,
      title,
      skill_dir: relSkillDir,
      steps: stepCount,
      steps_code: stepCode,
      steps_generic: stepGeneric,
      steps_url: stepHasUrl,
      avg_step_len: Number(avgLen.toFixed(1)),
      bash_cmds: bashCmds.length,
      flags,
    });

    if (flags.length > 0) {
      summaries.push({
        id,
        title,
        skill_dir: relSkillDir,
        flags,
        sample_steps: stepLines.slice(0, 3).map(stripCites),
      });
    }
  }

  rows.sort((a, b) => {
    const fa = (a.flags || []).length;
    const fb = (b.flags || []).length;
    if (fa !== fb) return fb - fa;
    return String(a.id || "").localeCompare(String(b.id || ""));
  });

  const tsv = [];
  tsv.push(
    formatTsvRow([
      "id",
      "domain",
      "title",
      "skill_dir",
      "steps",
      "steps_code",
      "steps_generic",
      "steps_url",
      "avg_step_len",
      "bash_cmds",
      "flags",
    ]),
  );
  for (const r of rows) {
    tsv.push(
      formatTsvRow([
        r.id,
        r.domain,
        r.title,
        r.skill_dir,
        r.steps,
        r.steps_code,
        r.steps_generic,
        r.steps_url,
        r.avg_step_len,
        r.bash_cmds,
        (r.flags || []).join(","),
      ]),
    );
  }
  writeText(outTsv, tsv.join("\n"));

  const outObj = {
    version: 1,
    generated_at: new Date().toISOString(),
    inputs: {
      run_id: args.runId || null,
      runs_dir: args.runId ? rel(repoRoot, path.resolve(repoRoot, args.runsDir)) : null,
      run_dir: runDirAbs ? rel(repoRoot, runDirAbs) : null,
      skills_root: rel(repoRoot, skillsRootAbs),
    },
    outputs: {
      md: rel(repoRoot, outMd),
      json: rel(repoRoot, outJson),
      tsv: rel(repoRoot, outTsv),
    },
    totals,
    rows,
    flagged: summaries.slice(0, 200),
  };
  writeJsonAtomic(outJson, outObj);

  const md = [];
  md.push(mdHeading("Skill Markdown Quality Audit", 1));
  md.push("");
  if (args.runId) md.push(`- Run: ${mdCode(args.runId)}`);
  md.push(`- Skills root: ${mdCode(rel(repoRoot, skillsRootAbs))}`);
  md.push(`- TSV: ${mdCode(rel(repoRoot, outTsv))}`);
  md.push(`- JSON: ${mdCode(rel(repoRoot, outJson))}`);
  md.push("");

  md.push(mdHeading("Summary", 2));
  md.push(`- skills: ${totals.skills}`);
  md.push(`- steps_total: ${totals.steps}`);
  md.push(`- steps_with_inline_code: ${totals.steps_with_code}`);
  md.push(`- steps_generic: ${totals.steps_generic}`);
  md.push(`- skills_linux_no_bash_commands: ${totals.skills_linux_no_bash_commands}`);
  md.push(`- skills_steps_mostly_generic: ${totals.skills_steps_mostly_generic}`);
  md.push(`- skills_steps_no_inline_code: ${totals.skills_steps_no_inline_code}`);
  md.push(`- skills_steps_has_url: ${totals.skills_steps_has_url}`);
  md.push(`- skills_title_looks_legal: ${totals.skills_title_looks_legal}`);
  md.push("");

  md.push(mdHeading("Flagged Skills (Top 50)", 2));
  md.push("");
  md.push("| # | id | title | flags | path |");
  md.push("|---:|---|---|---|---|");
  let rank = 1;
  for (const r of rows.filter((x) => (x.flags || []).length > 0).slice(0, 50)) {
    md.push(
      `| ${rank} | ${mdCode(r.id)} | ${String(r.title || "").replace(/\|/g, "\\|")} | ${mdCode((r.flags || []).join(","))} | ${mdCode(r.skill_dir)} |`,
    );
    rank++;
  }
  md.push("");

  writeText(outMd, md.join("\n"));

  console.log("[audit-skill-quality] ok");
  if (args.runId) console.log(`- run_id: ${args.runId}`);
  console.log(`- out_md: ${rel(repoRoot, outMd)}`);
  console.log(`- out_tsv: ${rel(repoRoot, outTsv)}`);
  console.log(`- out_json: ${rel(repoRoot, outJson)}`);
  console.log(`- skills: ${totals.skills}`);
}

main().catch((err) => {
  console.error("[audit-skill-quality] failed:", err && err.stack ? err.stack : String(err));
  process.exit(1);
});

