#!/usr/bin/env node
/* eslint-disable no-console */

const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");

function sha256Hex(text) {
  return crypto.createHash("sha256").update(String(text), "utf8").digest("hex");
}

function mustFiniteInt(value, name) {
  const n = Number(value);
  if (!Number.isFinite(n) || !Number.isInteger(n)) throw new Error(`${name} must be an integer (got: ${value})`);
  return n;
}

function parseArgs(argv) {
  const out = {
    out: null,
    overwrite: false,
    count: 2000,
    silver: 200,
    gold: 50,
    domain: "linux",
    topic: "synth",
    now: null,
    tag: "synthetic",
  };

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--out") {
      out.out = argv[i + 1] || null;
      i++;
    } else if (a === "--overwrite") {
      out.overwrite = true;
    } else if (a === "--count") {
      out.count = mustFiniteInt(argv[i + 1], "--count");
      i++;
    } else if (a === "--silver") {
      out.silver = mustFiniteInt(argv[i + 1], "--silver");
      i++;
    } else if (a === "--gold") {
      out.gold = mustFiniteInt(argv[i + 1], "--gold");
      i++;
    } else if (a === "--domain") {
      out.domain = String(argv[i + 1] || out.domain).trim();
      i++;
    } else if (a === "--topic") {
      out.topic = String(argv[i + 1] || out.topic).trim();
      i++;
    } else if (a === "--now") {
      out.now = String(argv[i + 1] || "").trim();
      i++;
    } else if (a === "--tag") {
      out.tag = String(argv[i + 1] || out.tag).trim();
      i++;
    } else if (a === "-h" || a === "--help") {
      console.log(
        [
          "Usage: node scripts/synth-skills.js [--out <dir>] [--count N] [--silver N] [--gold N] [--domain <name>] [--topic <name>] [--now YYYY-MM-DD] [--overwrite]",
          "",
          "Outputs the skills root path on stdout.",
        ].join("\n"),
      );
      process.exit(0);
    }
  }

  if (!out.domain) throw new Error("--domain is required");
  if (!out.topic) throw new Error("--topic is required");
  if (out.count <= 0) throw new Error("--count must be > 0");
  if (out.silver < 0 || out.gold < 0) throw new Error("--silver/--gold must be >= 0");
  if (out.silver + out.gold > out.count) throw new Error("--silver + --gold must be <= --count");

  if (!out.now) out.now = new Date().toISOString().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(out.now)) throw new Error(`--now must be YYYY-MM-DD (got: ${out.now})`);

  return out;
}

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function formatInlineYamlList(values) {
  const list = Array.isArray(values) ? values : [];
  if (list.length === 0) return "[]";
  return `[${list.map((v) => JSON.stringify(String(v))).join(", ")}]`;
}

function writeUtf8(filePath, text) {
  ensureDir(path.dirname(filePath));
  fs.writeFileSync(filePath, String(text), "utf8");
}

function main() {
  const args = parseArgs(process.argv.slice(2));

  const skillsRoot = args.out
    ? path.resolve(process.cwd(), args.out)
    : fs.mkdtempSync(path.join(os.tmpdir(), "skill-synth-"));

  if (fs.existsSync(skillsRoot) && !args.overwrite) {
    const entries = fs.readdirSync(skillsRoot);
    if (entries.length > 0) throw new Error(`Refusing to write into non-empty dir without --overwrite: ${skillsRoot}`);
  }

  const sources = [
    {
      title: "echo(1) - man7.org",
      url: "https://man7.org/linux/man-pages/man1/echo.1.html",
      license: "MIT",
      supports: "1",
      summary: "POSIX/Unix echo command reference and options.",
    },
    {
      title: "GNU Coreutils: echo",
      url: "https://www.gnu.org/software/coreutils/manual/html_node/echo-invocation.html",
      license: "GPL-3.0-or-later",
      supports: "1, 2",
      summary: "GNU echo behavior and flags in coreutils.",
    },
    {
      title: "POSIX echo utility",
      url: "https://pubs.opengroup.org/onlinepubs/9699919799/utilities/echo.html",
      license: "MIT",
      supports: "1, 2",
      summary: "POSIX specification of echo for portable usage.",
    },
  ];

  const bronze = args.count - args.silver - args.gold;
  const levels = [];
  for (let i = 0; i < args.gold; i++) levels.push("gold");
  for (let i = 0; i < args.silver; i++) levels.push("silver");
  for (let i = 0; i < bronze; i++) levels.push("bronze");

  for (let i = 0; i < args.count; i++) {
    const n = i + 1;
    const slug = `s-${String(n).padStart(4, "0")}`;
    const topic = args.topic;
    const domain = args.domain;
    const id = `${domain}/${topic}/${slug}`;

    const skillDir = path.join(skillsRoot, domain, topic, slug);
    const refDir = path.join(skillDir, "reference");
    ensureDir(refDir);

    const level = levels[i] || "bronze";
    const tags = [args.tag, "scale-test"];

    const metadata = [
      `id: ${id}`,
      `title: ${JSON.stringify(`Synthetic Skill ${slug}`)}`,
      `domain: ${domain}`,
      `level: ${level}`,
      `risk_level: low`,
      `platforms: [linux]`,
      `tools: []`,
      `tags: ${formatInlineYamlList(tags)}`,
      `aliases: []`,
      `owners: ["LabRAI"]`,
      `last_verified: ${JSON.stringify(args.now)}`,
      "",
    ].join("\n");
    writeUtf8(path.join(skillDir, "metadata.yaml"), metadata);

    const skillMd = [
      `# Synthetic Skill ${slug}`,
      "",
      "## Goal",
      "- Provide a deterministic, validator-clean skill for scale testing.",
      "",
      "## When to use",
      "- When you need to test indexing, validation, and reporting at large N without network access.",
      "",
      "## When NOT to use",
      "- When you need real operational guidance.",
      "",
      "## Prerequisites",
      "- Environment: Linux",
      "- Permissions: None",
      "- Tools: bash",
      "- Inputs needed: None",
      "",
      "## Steps (<= 12)",
      `1. Print a marker with \`echo "${slug}"\` [[1]]`,
      "2. Confirm the output contains the same marker string [[2]]",
      "",
      "## Verification",
      `- Expected output contains: ${slug}`,
      "",
      "## Safety & Risk",
      "- Risk level: **low**",
      "- Irreversible actions: None.",
      "- Privacy/credential handling: No secrets; do not paste credentials into terminals or logs.",
      "- Confirmation requirement: None.",
      "",
      "## Troubleshooting",
      "- See: reference/troubleshooting.md",
      "",
      "## Sources",
      `- [1] ${sources[0].url}`,
      `- [2] ${sources[1].url}`,
      `- [3] ${sources[2].url}`,
      "",
    ].join("\n");
    writeUtf8(path.join(skillDir, "skill.md"), skillMd);

    const libraryMd = [`# Library (Copy/Paste)`, "", "```bash", `echo "${slug}"`, "```", ""].join("\n");
    writeUtf8(path.join(skillDir, "library.md"), libraryMd);

    const sourcesMdLines = ["# Sources", ""];
    for (let si = 0; si < sources.length; si++) {
      const s = sources[si];
      const idx = si + 1;
      const sha = sha256Hex(`${slug}|${s.url}|${args.now}`);
      const bytes = Buffer.byteLength(s.url, "utf8") + 100 + idx;
      sourcesMdLines.push(
        `## [${idx}]`,
        `- Title: ${s.title}`,
        `- URL: ${s.url}`,
        `- Accessed: ${args.now}`,
        `- License: ${s.license}`,
        `- Summary: ${s.summary}`,
        `- Supports steps: ${s.supports}`,
        `- Fetch cache: miss`,
        `- Fetch bytes: ${bytes}`,
        `- Fetch sha256: ${sha}`,
        "",
      );
    }
    writeUtf8(path.join(refDir, "sources.md"), sourcesMdLines.join("\n"));

    writeUtf8(
      path.join(refDir, "troubleshooting.md"),
      ["# Troubleshooting", "", "- If `echo` behaves differently, prefer a POSIX shell and avoid non-portable flags.", ""].join("\n"),
    );
    writeUtf8(
      path.join(refDir, "edge-cases.md"),
      ["# Edge Cases", "", "- Some shells treat `echo -n` differently; this synthetic skill avoids flags.", ""].join("\n"),
    );
    writeUtf8(path.join(refDir, "examples.md"), ["# Examples", "", "```bash", `echo "${slug}"`, "```", ""].join("\n"));
    writeUtf8(path.join(refDir, "changelog.md"), ["# Changelog", "", `- ${args.now}: created (${level}).`, ""].join("\n"));
  }

  process.stdout.write(`${skillsRoot}\n`);
}

try {
  main();
} catch (e) {
  console.error(String(e && e.stack ? e.stack : e));
  process.exit(1);
}
