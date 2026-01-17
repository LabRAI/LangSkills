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

function readJson(filePath) {
  return JSON.parse(readText(filePath));
}

function safeJsonParse(text) {
  try {
    return JSON.parse(String(text || ""));
  } catch {
    return null;
  }
}

function readJsonl(filePath) {
  const out = [];
  const text = readText(filePath).replace(/\r\n/g, "\n");
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const obj = safeJsonParse(trimmed);
    if (obj) out.push(obj);
  }
  return out;
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

function mdCode(text) {
  return "`" + String(text || "").replace(/`/g, "\\`") + "`";
}

function mdHeading(text, level = 2) {
  const hashes = "#".repeat(Math.max(1, Math.min(6, Number(level) || 2)));
  return `${hashes} ${text}`;
}

function sanitizeRunId(raw) {
  const v = String(raw || "").trim();
  if (!v) return "";
  const safe = v.replace(/[^A-Za-z0-9._-]/g, "-");
  return safe.replace(/-+/g, "-").replace(/^-+/, "").replace(/-+$/, "");
}

function formatTsvRow(fields) {
  return fields.map((v) => String(v == null ? "" : v).replace(/\t/g, " ")).join("\t");
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
  node scripts/audit-source-pages.js --run-id <id>
    [--runs-dir runs]
    [--out-dir <dir>]

What it does:
  - Aggregates ALL unique source pages (URLs) seen in a run from:
    - crawl_log.jsonl (fetch attempts)
    - candidates.jsonl (extractor output)
    - curation.json (proposal grouping)
    - skills/*/reference/materials/{proposal.json,sources.json} (skill primary+references)
  - Writes:
    - runs/<run-id>/reports/source_pages_audit.tsv
    - runs/<run-id>/reports/source_pages_audit.json
    - runs/<run-id>/reports/source_pages_audit.md

Notes:
  - This script does NOT modify any skills; it only audits and summarizes.
`.trim();
  if (exitCode === 0) console.log(msg);
  else console.error(msg);
  process.exit(exitCode);
}

function parseArgs(argv) {
  const args = {
    runId: null,
    runsDir: "runs",
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
    } else if (a === "--out-dir") {
      args.outDir = argv[i + 1] || null;
      i++;
    } else if (a === "-h" || a === "--help") usage(0);
    else throw new Error(`Unknown arg: ${a}`);
  }

  args.runId = args.runId ? sanitizeRunId(args.runId) : "";
  if (!args.runId) usage(2);
  return args;
}

function walkFiles(rootDir) {
  const out = [];
  const stack = [rootDir];
  while (stack.length) {
    const current = stack.pop();
    let entries;
    try {
      entries = fs.readdirSync(current, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const ent of entries) {
      const p = path.join(current, ent.name);
      if (ent.isDirectory()) stack.push(p);
      else out.push(p);
    }
  }
  return out;
}

function extractProposalSourceUrls(proposalJson) {
  const raw = proposalJson && proposalJson.proposal && proposalJson.proposal.samples && proposalJson.proposal.samples.sources;
  const arr = Array.isArray(raw) ? raw : [];
  const out = new Set();
  for (const item of arr) {
    const parsed = safeJsonParse(item);
    const u = parsed && typeof parsed.url === "string" ? parsed.url.trim() : "";
    if (u) out.add(u);
  }
  return [...out];
}

function extractProposalSkillId(proposalJson) {
  const id1 = proposalJson && proposalJson.suggested && proposalJson.suggested.id;
  if (typeof id1 === "string" && id1.trim()) return id1.trim();
  const id2 = proposalJson && proposalJson.proposal && proposalJson.proposal.suggested && proposalJson.proposal.suggested.id;
  if (typeof id2 === "string" && id2.trim()) return id2.trim();
  return "";
}

function isOkFetchStatus(status, bytes) {
  const s = Number(status || 0);
  const b = Number(bytes || 0);
  return s >= 200 && s < 300 && b > 0;
}

function classifyPage(p) {
  const crawlSeen = !!(p.crawl && p.crawl.seen);
  const crawlOk = crawlSeen ? !!p.crawl.ok : null;
  const candidates = Number(p.counts && p.counts.candidates ? p.counts.candidates : 0);
  const proposals = Number(p.counts && p.counts.proposals ? p.counts.proposals : 0);
  const skills = Number(p.counts && p.counts.skills_using_url ? p.counts.skills_using_url : 0);
  const skillErr = Number(p.counts && p.counts.skills_using_url_llm_error ? p.counts.skills_using_url_llm_error : 0);
  const refMentions = Number(p.counts && p.counts.ref_mentions ? p.counts.ref_mentions : 0);
  const refOk = Number(p.counts && p.counts.ref_fetch_ok ? p.counts.ref_fetch_ok : 0);
  const refErr = Number(p.counts && p.counts.ref_fetch_error ? p.counts.ref_fetch_error : 0);

  if (crawlSeen && crawlOk === false) return "crawl_error";
  if (skills > 0 && skillErr > 0) return "skills_llm_error";
  if (skills > 0) return "skills_ok";
  if (crawlSeen && crawlOk === true && candidates === 0 && proposals === 0) return "no_candidates";
  if (candidates > 0 || proposals > 0) return "unverified_no_skills";

  if (refMentions > 0) {
    if (refOk > 0 && refErr === 0) return "reference_ok";
    if (refOk > 0 && refErr > 0) return "reference_partial";
    if (refOk === 0 && refErr > 0) return "reference_fetch_error";
    return "reference_unknown";
  }

  return "unknown";
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const repoRoot = path.resolve(__dirname, "..");
  const runsRoot = path.isAbsolute(args.runsDir) ? args.runsDir : path.resolve(repoRoot, args.runsDir);
  const runDir = path.join(runsRoot, args.runId);

  if (!exists(runDir)) throw new Error(`Missing run dir: ${runDir}`);

  const crawlLogPath = path.join(runDir, "crawl_log.jsonl");
  const candidatesPath = path.join(runDir, "candidates.jsonl");
  const curationPath = path.join(runDir, "curation.json");
  const skillgenReportPath = path.join(runDir, "reports", "skillgen.json");
  const skillsRoot = path.join(runDir, "skills");

  const outDir = args.outDir
    ? path.isAbsolute(args.outDir)
      ? args.outDir
      : path.resolve(repoRoot, args.outDir)
    : path.join(runDir, "reports");

  const outTsv = path.join(outDir, "source_pages_audit.tsv");
  const outJson = path.join(outDir, "source_pages_audit.json");
  const outMd = path.join(outDir, "source_pages_audit.md");

  let domain = "";
  if (exists(curationPath)) {
    const c = readJson(curationPath);
    domain = c && c.domain ? String(c.domain) : domain;
  }
  if (!domain && exists(skillgenReportPath)) {
    const r = readJson(skillgenReportPath);
    domain = r && r.domain ? String(r.domain) : domain;
  }

  const pages = new Map();

  function getOrCreate(url) {
    const u = String(url || "").trim();
    if (!u) return null;
    if (!pages.has(u)) {
      pages.set(u, {
        url: u,
        crawl: { seen: false },
        counts: {
          candidates: 0,
          proposals: 0,
          skills_using_url: 0,
          skills_using_url_llm_error: 0,
          ref_mentions: 0,
          ref_fetch_ok: 0,
          ref_fetch_error: 0,
          license_unknown: 0,
        },
        samples: { skills_using_url: [], ref_skills: [] },
        status: "unknown",
      });
    }
    return pages.get(u);
  }

  // 1) Crawl (fetch attempts)
  if (exists(crawlLogPath)) {
    const lines = readJsonl(crawlLogPath);
    for (const row of lines) {
      const url = row && typeof row.url === "string" ? row.url.trim() : "";
      if (!url) continue;
      const p = getOrCreate(url);
      if (!p) continue;
      p.crawl = {
        seen: true,
        ok: !!row.ok,
        status: Number.isFinite(Number(row.status)) ? Number(row.status) : 0,
        bytes: Number.isFinite(Number(row.bytes)) ? Number(row.bytes) : 0,
        cache: typeof row.cache === "string" ? row.cache : "",
        cache_file: typeof row.cache_file === "string" ? row.cache_file : "",
        content_type: typeof row.content_type === "string" ? row.content_type : "",
        is_html: !!row.is_html,
        depth: Number.isFinite(Number(row.depth)) ? Number(row.depth) : null,
        error: typeof row.error === "string" ? row.error : "",
        ts: typeof row.ts === "string" ? row.ts : "",
      };
    }
  }

  // 2) Candidates (extractor output)
  if (exists(candidatesPath)) {
    const lines = readJsonl(candidatesPath);
    for (const row of lines) {
      const url = row && row.source && typeof row.source.url === "string" ? row.source.url.trim() : "";
      if (!url) continue;
      const p = getOrCreate(url);
      if (!p) continue;
      p.counts.candidates += 1;
    }
  }

  // 3) Curation (proposal grouping)
  if (exists(curationPath)) {
    const c = readJson(curationPath);
    const proposals = Array.isArray(c && c.proposals) ? c.proposals : [];
    for (const prop of proposals) {
      const srcs = prop && prop.samples && Array.isArray(prop.samples.sources) ? prop.samples.sources : [];
      for (const s of srcs) {
        const parsed = safeJsonParse(s);
        const url = parsed && typeof parsed.url === "string" ? parsed.url.trim() : "";
        if (!url) continue;
        const p = getOrCreate(url);
        if (!p) continue;
        p.counts.proposals += 1;
      }
    }
  }

  // 4) Skills (primary + references + LLM errors)
  if (exists(skillsRoot)) {
    const files = walkFiles(skillsRoot);
    const proposalFiles = files.filter((p) => p.replace(/\\/g, "/").endsWith("/reference/materials/proposal.json"));

    for (const proposalPath of proposalFiles) {
      const proposal = safeJsonParse(readText(proposalPath));
      if (!proposal) continue;

      const skillId = extractProposalSkillId(proposal);
      const skillDir = path.resolve(proposalPath, "..", "..", "..");
      const genCapturePath = path.join(skillDir, "reference", "llm", "generate_skill.json");
      const sourcesJsonPath = path.join(skillDir, "reference", "materials", "sources.json");

      let llmError = "";
      if (exists(genCapturePath)) {
        const cap = safeJsonParse(readText(genCapturePath));
        llmError = cap && typeof cap.error === "string" ? cap.error.trim() : "";
      }

      const proposalUrls = extractProposalSourceUrls(proposal);
      for (const u of proposalUrls) {
        const p = getOrCreate(u);
        if (!p) continue;
        p.counts.skills_using_url += 1;
        if (llmError) p.counts.skills_using_url_llm_error += 1;
        if (skillId && p.samples.skills_using_url.length < 5) p.samples.skills_using_url.push(skillId);
      }

      if (exists(sourcesJsonPath)) {
        const sources = safeJsonParse(readText(sourcesJsonPath));
        const arr = Array.isArray(sources) ? sources : [];
        for (const s of arr) {
          const url = s && typeof s.url === "string" ? s.url.trim() : "";
          if (!url) continue;
          const p = getOrCreate(url);
          if (!p) continue;

          p.counts.ref_mentions += 1;
          if (skillId && p.samples.ref_skills.length < 5) p.samples.ref_skills.push(skillId);

          const fetched = s && typeof s.fetched === "object" ? s.fetched : null;
          const st = fetched && Number.isFinite(Number(fetched.status)) ? Number(fetched.status) : 0;
          const bytes = fetched && Number.isFinite(Number(fetched.bytes)) ? Number(fetched.bytes) : 0;
          if (isOkFetchStatus(st, bytes)) p.counts.ref_fetch_ok += 1;
          else if (st || bytes) p.counts.ref_fetch_error += 1;
          else p.counts.ref_fetch_error += 1;

          const lic = s && typeof s.license === "string" ? s.license.trim() : "";
          if (!lic || lic === "unknown") p.counts.license_unknown += 1;
        }
      }
    }
  }

  const pageList = [...pages.values()];
  for (const p of pageList) p.status = classifyPage(p);

  const summary = {
    total_unique_urls: pageList.length,
    crawl_seen: pageList.filter((p) => p.crawl && p.crawl.seen).length,
    crawl_ok: pageList.filter((p) => p.crawl && p.crawl.seen && p.crawl.ok === true).length,
    crawl_error: pageList.filter((p) => p.crawl && p.crawl.seen && p.crawl.ok === false).length,
    with_candidates: pageList.filter((p) => Number(p.counts.candidates || 0) > 0).length,
    with_proposals: pageList.filter((p) => Number(p.counts.proposals || 0) > 0).length,
    with_skills_using_url: pageList.filter((p) => Number(p.counts.skills_using_url || 0) > 0).length,
    with_skill_using_url_llm_error: pageList.filter((p) => Number(p.counts.skills_using_url_llm_error || 0) > 0).length,
    referenced_in_skills: pageList.filter((p) => Number(p.counts.ref_mentions || 0) > 0).length,
    reference_fetch_error_urls: pageList.filter((p) => Number(p.counts.ref_fetch_error || 0) > 0).length,
    status_counts: {},
  };
  for (const p of pageList) {
    summary.status_counts[p.status] = (summary.status_counts[p.status] || 0) + 1;
  }

  pageList.sort((a, b) => {
    const sa = String(a.status || "");
    const sb = String(b.status || "");
    if (sa !== sb) return sa.localeCompare(sb);
    return String(a.url || "").localeCompare(String(b.url || ""));
  });

  const tsv = [];
  tsv.push(
    formatTsvRow([
      "url",
      "crawl_seen",
      "crawl_ok",
      "crawl_status",
      "crawl_bytes",
      "crawl_is_html",
      "crawl_depth",
      "candidates",
      "proposals",
      "skills_using_url",
      "skills_using_url_llm_error",
      "ref_mentions",
      "ref_fetch_ok",
      "ref_fetch_error",
      "license_unknown",
      "status",
    ]),
  );
  for (const p of pageList) {
    tsv.push(
      formatTsvRow([
        p.url,
        p.crawl && p.crawl.seen ? 1 : 0,
        p.crawl && p.crawl.seen ? (p.crawl.ok ? 1 : 0) : "",
        p.crawl && p.crawl.seen ? Number(p.crawl.status || 0) : "",
        p.crawl && p.crawl.seen ? Number(p.crawl.bytes || 0) : "",
        p.crawl && p.crawl.seen ? (p.crawl.is_html ? 1 : 0) : "",
        p.crawl && p.crawl.seen ? (p.crawl.depth == null ? "" : p.crawl.depth) : "",
        Number(p.counts.candidates || 0),
        Number(p.counts.proposals || 0),
        Number(p.counts.skills_using_url || 0),
        Number(p.counts.skills_using_url_llm_error || 0),
        Number(p.counts.ref_mentions || 0),
        Number(p.counts.ref_fetch_ok || 0),
        Number(p.counts.ref_fetch_error || 0),
        Number(p.counts.license_unknown || 0),
        p.status,
      ]),
    );
  }
  writeText(outTsv, tsv.join("\n"));

  const outObj = {
    version: 1,
    generated_at: new Date().toISOString(),
    run_id: args.runId,
    domain,
    inputs: {
      run_dir: rel(repoRoot, runDir),
      crawl_log_jsonl: exists(crawlLogPath) ? rel(repoRoot, crawlLogPath) : null,
      candidates_jsonl: exists(candidatesPath) ? rel(repoRoot, candidatesPath) : null,
      curation_json: exists(curationPath) ? rel(repoRoot, curationPath) : null,
      skillgen_report_json: exists(skillgenReportPath) ? rel(repoRoot, skillgenReportPath) : null,
      skills_root: exists(skillsRoot) ? rel(repoRoot, skillsRoot) : null,
    },
    outputs: {
      tsv: rel(repoRoot, outTsv),
      json: rel(repoRoot, outJson),
      md: rel(repoRoot, outMd),
    },
    summary,
    pages: pageList,
  };
  writeJsonAtomic(outJson, outObj);

  const md = [];
  md.push(mdHeading("Source Pages Audit", 1));
  md.push("");
  md.push(`- Run: ${mdCode(args.runId)}${domain ? ` (domain=${mdCode(domain)})` : ""}`);
  md.push(`- TSV: ${mdCode(rel(repoRoot, outTsv))}`);
  md.push(`- JSON: ${mdCode(rel(repoRoot, outJson))}`);
  md.push("");

  md.push(mdHeading("Summary", 2));
  md.push(`- total_unique_urls: ${summary.total_unique_urls}`);
  md.push(`- crawl_ok/crawl_error: ${summary.crawl_ok}/${summary.crawl_error} (crawl_seen=${summary.crawl_seen})`);
  md.push(`- with_candidates/with_skills_using_url: ${summary.with_candidates}/${summary.with_skills_using_url}`);
  md.push(`- pages_with_skill_using_url_llm_error: ${summary.with_skill_using_url_llm_error}`);
  md.push(`- referenced_in_skills: ${summary.referenced_in_skills}`);
  md.push("");

  md.push(mdHeading("Status Counts", 2));
  for (const k of Object.keys(summary.status_counts).sort()) {
    md.push(`- ${mdCode(k)}: ${summary.status_counts[k]}`);
  }
  md.push("");

  md.push(mdHeading("Per-Page List", 2));
  md.push("");
  md.push("| status | url | crawl | candidates | proposals | skills_using_url | skill_llm_err | ref_ok/ref_err |");
  md.push("|---|---|---:|---:|---:|---:|---:|---:|");
  for (const p of pageList) {
    const crawlCell = p.crawl && p.crawl.seen ? (p.crawl.ok ? `${p.crawl.status || 0}/${p.crawl.bytes || 0}` : `err`) : "";
    const refCell = `${Number(p.counts.ref_fetch_ok || 0)}/${Number(p.counts.ref_fetch_error || 0)}`;
    md.push(
      `| ${mdCode(p.status)} | ${mdCode(p.url)} | ${crawlCell} | ${Number(p.counts.candidates || 0)} | ${Number(p.counts.proposals || 0)} | ${Number(p.counts.skills_using_url || 0)} | ${Number(p.counts.skills_using_url_llm_error || 0)} | ${refCell} |`,
    );
  }
  writeText(outMd, md.join("\n"));

  console.log("[audit-source-pages] ok");
  console.log(`- run_id: ${args.runId}`);
  if (domain) console.log(`- domain: ${domain}`);
  console.log(`- out_tsv: ${rel(repoRoot, outTsv)}`);
  console.log(`- out_md: ${rel(repoRoot, outMd)}`);
  console.log(`- out_json: ${rel(repoRoot, outJson)}`);
  console.log(`- total_unique_urls: ${summary.total_unique_urls}`);
}

main().catch((err) => {
  console.error("[audit-source-pages] failed:", err && err.stack ? err.stack : String(err));
  process.exit(1);
});
