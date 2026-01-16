#!/usr/bin/env node
/* eslint-disable no-console */

const crypto = require("crypto");
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

function walk(dirPath, onDir) {
  const entries = fs.readdirSync(dirPath, { withFileTypes: true });
  for (const entry of entries) {
    const full = path.join(dirPath, entry.name);
    if (entry.isDirectory()) {
      onDir(full);
      walk(full, onDir);
    }
  }
}

function readText(filePath) {
  return fs.readFileSync(filePath, "utf8");
}

function parseSimpleYamlScalar(text, key) {
  const re = new RegExp(`^${key}:\\s*(.+?)\\s*$`, "m");
  const m = text.match(re);
  if (!m) return null;
  let value = m[1].trim();
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    value = value.slice(1, -1);
  }
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

function countMatches(text, re) {
  if (!text) return 0;
  const m = text.match(re);
  return m ? m.length : 0;
}

function normalizeLicenseToken(raw) {
  let t = String(raw || "").trim();
  if (!t) return "";

  const url = t.match(/^https?:\/\/\S+$/i) ? t : null;
  if (url) {
    if (/^https?:\/\/creativecommons\.org\/licenses\/by\/4\.0\/?/i.test(url)) return "cc-by-4.0";
    if (/^https?:\/\/creativecommons\.org\/licenses\/by-sa\/4\.0\/?/i.test(url)) return "cc-by-sa-4.0";
    if (/^https?:\/\/creativecommons\.org\/publicdomain\/zero\/1\.0\/?/i.test(url)) return "cc0-1.0";
    if (/^https?:\/\/opensource\.org\/licenses\/MIT/i.test(url)) return "mit";
    if (/^https?:\/\/opensource\.org\/licenses\/Apache-2\.0/i.test(url)) return "apache-2.0";
  }

  t = t.replace(/\blicen[cs]e\b/gi, "").trim();
  t = t.replace(/\s+/g, " ").trim();
  t = t.replace(/[–—]/g, "-");
  t = t.replace(/[_\s]+/g, "-");
  t = t.replace(/[^a-zA-Z0-9.+-]/g, "-");
  t = t.replace(/-+/g, "-").replace(/^-+/, "").replace(/-+$/, "");
  return t.toLowerCase();
}

function loadLicensePolicy(policyPath) {
  const p = String(policyPath || "").trim();
  if (!p) throw new Error("Missing license policy path");
  if (!exists(p)) throw new Error(`Missing license policy file: ${p}`);
  let parsed = null;
  try {
    parsed = JSON.parse(readText(p));
  } catch (e) {
    throw new Error(`Invalid license policy JSON: ${p} (${String(e && e.message ? e.message : e)})`);
  }
  const allowed = new Set((parsed.allowed || []).map(normalizeLicenseToken).filter(Boolean));
  const review = new Set((parsed.review || []).map(normalizeLicenseToken).filter(Boolean));
  const denied = new Set((parsed.denied || []).map(normalizeLicenseToken).filter(Boolean));
  return { allowed, review, denied, raw: parsed, path: p };
}

function classifyLicense(rawLicense, policy) {
  const normalized = normalizeLicenseToken(rawLicense);
  if (!normalized) return { classification: "review", normalized };
  if (policy.denied.has(normalized)) return { classification: "denied", normalized };
  if (policy.allowed.has(normalized)) return { classification: "allowed", normalized };
  if (policy.review.has(normalized)) return { classification: "review", normalized };
  return { classification: "review", normalized };
}

function parseArgs(argv) {
  const out = {
    skillsRoot: null,
    requireCitations: false,
    requireCommandCitations: false,
    requireSourceEvidence: false,
    requireLicenseFields: false,
    licensePolicy: "scripts/license-policy.json",
    failOnLicenseReview: false,
    failOnLicenseReviewAll: false,
    requireNoDuplicates: false,
    requireRiskScan: false,
    requireSourcePolicy: false,
    requireNoVerbatimCopy: false,
    cacheDir: ".cache/web",
    requireNoTodo: false,
    requireSafetyNotes: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--skills-root") {
      out.skillsRoot = argv[i + 1] || null;
      i++;
    } else if (a === "--require-citations") {
      out.requireCitations = true;
    } else if (a === "--require-command-citations") {
      out.requireCommandCitations = true;
    } else if (a === "--require-source-evidence") {
      out.requireSourceEvidence = true;
    } else if (a === "--require-license-fields") {
      out.requireLicenseFields = true;
    } else if (a === "--license-policy") {
      out.licensePolicy = argv[i + 1] || out.licensePolicy;
      i++;
    } else if (a === "--fail-on-license-review") {
      out.failOnLicenseReview = true;
    } else if (a === "--fail-on-license-review-all") {
      out.failOnLicenseReviewAll = true;
    } else if (a === "--require-no-duplicates") {
      out.requireNoDuplicates = true;
    } else if (a === "--require-risk-scan") {
      out.requireRiskScan = true;
    } else if (a === "--require-source-policy") {
      out.requireSourcePolicy = true;
    } else if (a === "--require-no-verbatim-copy") {
      out.requireNoVerbatimCopy = true;
    } else if (a === "--cache-dir") {
      out.cacheDir = argv[i + 1] || ".cache/web";
      i++;
    } else if (a === "--require-no-todo") {
      out.requireNoTodo = true;
    } else if (a === "--require-safety-notes") {
      out.requireSafetyNotes = true;
    } else if (a === "--strict") {
      out.requireCitations = true;
      out.requireCommandCitations = true;
      out.requireSourceEvidence = true;
      out.requireLicenseFields = true;
      out.requireSourcePolicy = true;
      out.requireNoTodo = true;
      out.requireSafetyNotes = true;
      out.requireNoDuplicates = true;
      out.requireRiskScan = true;
    } else if (a === "-h" || a === "--help") {
      console.log(
        "Usage: node scripts/validate-skills.js [--skills-root <path>] [--cache-dir <path>] [--require-citations] [--require-command-citations] [--require-source-evidence] [--require-license-fields] [--license-policy <path>] [--fail-on-license-review] [--fail-on-license-review-all] [--require-no-duplicates] [--require-risk-scan] [--require-source-policy] [--require-no-verbatim-copy] [--require-no-todo] [--require-safety-notes] [--strict]",
      );
      process.exit(0);
    }
  }
  return out;
}

function unquoteScalar(value) {
  let v = String(value || "").trim();
  if (!v) return "";
  if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
    v = v.slice(1, -1);
  }
  return v;
}

function parseInlineYamlList(value) {
  const v = String(value || "").trim();
  if (!v) return null;
  if (v === "[]") return [];
  if (v.startsWith("[") && v.endsWith("]")) {
    const inner = v.slice(1, -1).trim();
    if (!inner) return [];
    return inner
      .split(",")
      .map((x) => unquoteScalar(x))
      .map((x) => x.trim())
      .filter(Boolean);
  }
  return [unquoteScalar(v)];
}

function parseDomainSourcePolicy(configText) {
  const policy = { allow_domains: [], deny_domains: [] };
  const lines = String(configText || "").replace(/\r\n/g, "\n").split("\n");

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].replace(/\s+$/, "");
    if (!line.trim()) continue;
    if (/^\s*#/.test(line)) continue;

    const allowMatch = line.match(/^\s*allow_domains:\s*(.*?)\s*$/);
    if (allowMatch) {
      const parsed = parseInlineYamlList(allowMatch[1]);
      if (parsed !== null) {
        policy.allow_domains = parsed;
        continue;
      }
      const items = [];
      for (let j = i + 1; j < lines.length; j++) {
        const ln = lines[j].replace(/\s+$/, "");
        if (!ln.trim()) continue;
        if (/^\s*#/.test(ln)) continue;
        const m = ln.match(/^\s*-\s*(.+?)\s*$/);
        if (!m) break;
        items.push(unquoteScalar(m[1]));
        i = j;
      }
      policy.allow_domains = items;
      continue;
    }

    const denyMatch = line.match(/^\s*deny_domains:\s*(.*?)\s*$/);
    if (denyMatch) {
      const parsed = parseInlineYamlList(denyMatch[1]);
      if (parsed !== null) {
        policy.deny_domains = parsed;
        continue;
      }
      const items = [];
      for (let j = i + 1; j < lines.length; j++) {
        const ln = lines[j].replace(/\s+$/, "");
        if (!ln.trim()) continue;
        if (/^\s*#/.test(ln)) continue;
        const m = ln.match(/^\s*-\s*(.+?)\s*$/);
        if (!m) break;
        items.push(unquoteScalar(m[1]));
        i = j;
      }
      policy.deny_domains = items;
      continue;
    }
  }

  return policy;
}

function normalizeDomainPattern(pattern) {
  const p = String(pattern || "").trim().toLowerCase();
  if (!p) return "";
  return p.replace(/^\.+/, "").replace(/\.+$/, "");
}

function hostMatchesPattern(hostname, pattern) {
  const host = String(hostname || "").trim().toLowerCase();
  const raw = String(pattern || "").trim().toLowerCase();
  const p = normalizeDomainPattern(raw);
  if (!host || !p) return false;
  if (host === p) return true;
  return host.endsWith(`.${p}`);
}

function isUrlAllowed(url, { allow_domains: allowDomains = [], deny_domains: denyDomains = [] } = {}) {
  const u = new URL(String(url || ""));
  const host = u.hostname;

  for (const d of Array.isArray(denyDomains) ? denyDomains : []) {
    if (hostMatchesPattern(host, d)) return false;
  }

  const allow = Array.isArray(allowDomains) ? allowDomains.filter(Boolean) : [];
  if (allow.length === 0) return true;
  return allow.some((d) => hostMatchesPattern(host, d));
}

function sha256Hex(text) {
  return crypto.createHash("sha256").update(String(text || ""), "utf8").digest("hex");
}

function cachePathForUrl(cacheDir, url) {
  const hash = sha256Hex(url).slice(0, 16);
  return path.join(cacheDir, `${hash}.txt`);
}

function stripHtmlToText(html) {
  let t = String(html || "");
  t = t.replace(/<script[\s\S]*?<\/script>/gi, " ");
  t = t.replace(/<style[\s\S]*?<\/style>/gi, " ");
  t = t.replace(/<[^>]+>/g, " ");
  t = t.replace(/&nbsp;/gi, " ");
  t = t.replace(/&amp;/gi, "&");
  t = t.replace(/&lt;/gi, "<");
  t = t.replace(/&gt;/gi, ">");
  t = t.replace(/&quot;/gi, '"');
  t = t.replace(/&#39;/gi, "'");
  t = t.replace(/\s+/g, " ").trim();
  return t;
}

function stripMarkdownToText(markdown) {
  let t = String(markdown || "");
  t = t.replace(/```[\s\S]*?```/g, " ");
  t = t.replace(/`[^`]*`/g, " ");
  t = t.replace(/<!--[\s\S]*?-->/g, " ");
  t = t.replace(/!\[[^\]]*]\([^)]*\)/g, " ");
  t = t.replace(/\[([^\]]*)]\([^)]*\)/g, "$1");
  t = t.replace(/[>#*_\\-]/g, " ");
  t = t.replace(/\s+/g, " ").trim();
  return t;
}

function normalizeForCompare(text) {
  return String(text || "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function findVerbatimWindow({ haystack, needleTokens, windowTokens = 80, strideTokens = 20 }) {
  const tokens = Array.isArray(needleTokens) ? needleTokens : [];
  if (tokens.length < windowTokens) return null;
  for (let i = 0; i + windowTokens <= tokens.length; i += strideTokens) {
    const window = tokens.slice(i, i + windowTokens).join(" ");
    if (haystack.includes(window)) return window;
  }
  return null;
}

function findVerbatimCharWindow({ haystack, needle, windowChars = 400, strideChars = 80 }) {
  const t = String(needle || "");
  if (t.length < windowChars) return null;
  for (let i = 0; i + windowChars <= t.length; i += strideChars) {
    const window = t.slice(i, i + windowChars);
    if (haystack.includes(window)) return window;
  }
  return null;
}

function blockBody(markdown, headingLineRe) {
  const m = headingLineRe.exec(markdown);
  if (!m) return null;

  let rest = markdown.slice(m.index + m[0].length);
  if (rest.startsWith("\r\n")) rest = rest.slice(2);
  else if (rest.startsWith("\n")) rest = rest.slice(1);

  const nextHeadingIdx = rest.search(/^##\s+/m);
  return nextHeadingIdx === -1 ? rest : rest.slice(0, nextHeadingIdx);
}

const repoRoot = path.resolve(__dirname, "..");
const args = parseArgs(process.argv.slice(2));
const skillsRoot = args.skillsRoot ? path.resolve(repoRoot, args.skillsRoot) : path.join(repoRoot, "skills");

if (!exists(skillsRoot)) {
  console.error(`Missing skills root: ${skillsRoot}`);
  process.exit(1);
}

const skillDirs = [];
walk(skillsRoot, (dirPath) => {
  if (exists(path.join(dirPath, "metadata.yaml"))) {
    skillDirs.push(dirPath);
  }
});

if (skillDirs.length === 0) {
  console.error("No skills found under skills/ (expected metadata.yaml).");
  process.exit(1);
}

const errors = [];
const warnings = [];
const licensePolicyPath = args.licensePolicy ? path.resolve(repoRoot, args.licensePolicy) : path.join(repoRoot, "scripts", "license-policy.json");
const licensePolicy = args.requireLicenseFields ? loadLicensePolicy(licensePolicyPath) : null;
const libraryHashes = new Map(); // sha256 -> first skill id

function riskRank(level) {
  const v = String(level || "").trim().toLowerCase();
  if (v === "low") return 0;
  if (v === "medium") return 1;
  if (v === "high") return 2;
  return -1;
}

const RISK_PATTERNS = [
  { min: "high", re: /\brm\s+-rf\b/i, hint: "rm -rf" },
  { min: "high", re: /\bdd\s+if=/i, hint: "dd if=" },
  { min: "high", re: /\bmkfs(?:\.[a-z0-9]+)?\b/i, hint: "mkfs" },
  { min: "high", re: /\b(?:userdel|groupdel|deluser)\b/i, hint: "userdel/groupdel" },
  { min: "high", re: /\b(?:kill|pkill)\s+-(?:9|KILL)\b/i, hint: "kill -9/-KILL" },
  { min: "high", re: /\bvisudo\b/i, hint: "visudo" },
  { min: "high", re: /\bmount\b/i, hint: "mount" },
  { min: "medium", re: /\bpatch\b/i, hint: "patch" },
  { min: "medium", re: /\bxargs\b/i, hint: "xargs" },
  { min: "medium", re: /\bchmod\b/i, hint: "chmod" },
  { min: "medium", re: /\bchown\b/i, hint: "chown" },
];

for (const skillDir of skillDirs) {
  const rel = path.relative(skillsRoot, skillDir);
  const relPosix = rel.split(path.sep).join("/");
  const parts = relPosix.split("/");
  if (parts.length !== 3) {
    errors.push(`[${relPosix}] invalid path depth (expected domain/topic/slug)`);
    continue;
  }

  const [domain, topic, slug] = parts;
  const expectedId = `${domain}/${topic}/${slug}`;

  const expectedFiles = [
    "skill.md",
    "library.md",
    "metadata.yaml",
    path.join("reference", "sources.md"),
    path.join("reference", "troubleshooting.md"),
    path.join("reference", "edge-cases.md"),
    path.join("reference", "examples.md"),
    path.join("reference", "changelog.md"),
  ];

  for (const fileRel of expectedFiles) {
    const full = path.join(skillDir, fileRel);
    if (!exists(full)) {
      errors.push(`[${relPosix}] missing ${fileRel}`);
    }
  }

  const metadataPath = path.join(skillDir, "metadata.yaml");
  const skillPath = path.join(skillDir, "skill.md");
  const libraryPath = path.join(skillDir, "library.md");
  const sourcesPath = path.join(skillDir, "reference", "sources.md");
  const troubleshootingPath = path.join(skillDir, "reference", "troubleshooting.md");
  const edgeCasesPath = path.join(skillDir, "reference", "edge-cases.md");
  const examplesPath = path.join(skillDir, "reference", "examples.md");

  let metaRiskLevel = null;
  let metaLevel = null;
  if (exists(metadataPath)) {
    const meta = readText(metadataPath);
    const id = parseSimpleYamlScalar(meta, "id");
    const title = parseSimpleYamlScalar(meta, "title");
    const metaDomain = parseSimpleYamlScalar(meta, "domain");
    const level = parseSimpleYamlScalar(meta, "level");
    const riskLevel = parseSimpleYamlScalar(meta, "risk_level");
    metaRiskLevel = riskLevel;
    metaLevel = level;

    if (!id) errors.push(`[${relPosix}] metadata.yaml missing id`);
    if (id && id !== expectedId) {
      errors.push(`[${relPosix}] metadata id mismatch: '${id}' != '${expectedId}'`);
    }

    if (!title) errors.push(`[${relPosix}] metadata.yaml missing title`);

    if (!metaDomain) errors.push(`[${relPosix}] metadata.yaml missing domain`);
    if (metaDomain && metaDomain !== domain) {
      errors.push(`[${relPosix}] metadata domain mismatch: '${metaDomain}' != '${domain}'`);
    }

    const allowedLevels = new Set(["bronze", "silver", "gold"]);
    if (!level) errors.push(`[${relPosix}] metadata.yaml missing level`);
    if (level && !allowedLevels.has(level)) {
      errors.push(`[${relPosix}] invalid level: '${level}'`);
    }

    const allowedRisk = new Set(["low", "medium", "high"]);
    if (!riskLevel) errors.push(`[${relPosix}] metadata.yaml missing risk_level`);
    if (riskLevel && !allowedRisk.has(riskLevel)) {
      errors.push(`[${relPosix}] invalid risk_level: '${riskLevel}'`);
    }

    if (level === "silver" || level === "gold") {
      const owners = parseInlineYamlList(parseSimpleYamlScalar(meta, "owners")) || [];
      const lastVerified = parseSimpleYamlScalar(meta, "last_verified") || "";
      if (owners.length === 0) errors.push(`[${relPosix}] ${level} skill missing owners`);
      if (!lastVerified) errors.push(`[${relPosix}] ${level} skill missing last_verified`);
      else if (!/^\d{4}-\d{2}-\d{2}$/.test(lastVerified)) {
        errors.push(`[${relPosix}] invalid last_verified (expected YYYY-MM-DD): '${lastVerified}'`);
      }
    }
  }

  if (exists(skillPath)) {
    const md = readText(skillPath);
    const libraryMd = exists(libraryPath) ? readText(libraryPath) : "";

    const requiredHeadings = [
      { name: "Goal", re: /Goal\b/ },
      { name: "When to use", re: /When to use\b/ },
      { name: "When NOT to use", re: /When NOT to use\b/ },
      { name: "Prerequisites", re: /Prerequisites\b/ },
      { name: "Steps", re: /Steps\b/ },
      { name: "Verification", re: /Verification\b/ },
      { name: "Safety & Risk", re: /Safety\s*&\s*Risk\b/ },
      { name: "Troubleshooting", re: /Troubleshooting\b/ },
      { name: "Sources", re: /Sources\b/ },
    ];

    for (const h of requiredHeadings) {
      const ok = new RegExp(`^##\\s+${h.re.source}.*$`, "m").test(md);
      if (!ok) errors.push(`[${relPosix}] skill.md missing heading: ## ${h.name}`);
    }

    const stepsBody = sectionBody(md, /Steps\b/);
    const stepsCount = countMatches(stepsBody, /^\s*\d+\.\s+/gm);
    if (stepsCount > 12) errors.push(`[${relPosix}] Steps too many: ${stepsCount} > 12`);
    if (stepsCount === 0) errors.push(`[${relPosix}] Steps missing numbered list`);

    const sourcesBody = sectionBody(md, /Sources\b/);
    const sourcesCount = countMatches(sourcesBody, /^\s*-\s*\[\d+\]\s+/gm);
    if (sourcesCount < 3) errors.push(`[${relPosix}] Sources too few: ${sourcesCount} < 3`);

    if (args.requireCitations) {
      const body = stepsBody || "";
      const citeMatches = [...body.matchAll(/\[\[(.+?)\]\]/g)];
      if (citeMatches.length === 0) {
        errors.push(`[${relPosix}] missing step citations ([[n]])`);
      } else if (sourcesCount > 0) {
        for (const m of citeMatches) {
          const nums = String(m[1] || "").match(/\d+/g) || [];
          for (const raw of nums) {
            const n = Number(raw);
            if (!Number.isFinite(n) || n < 1 || n > sourcesCount) {
              errors.push(`[${relPosix}] invalid citation [[${raw}]] (sources=${sourcesCount})`);
            }
          }
        }
      }
    }

    if (args.requireCommandCitations) {
      const body = stepsBody || "";
      const lines = body.split(/\r?\n/);
      for (const line of lines) {
        const isStep = /^\s*\d+\.\s+/.test(line);
        if (!isStep) continue;
        const hasCode = /`[^`]+`/.test(line);
        if (!hasCode) continue;
        const hasCite = /\[\[(?:\d+)(?:\]\[\d+)*\]\]\s*$/.test(line);
        if (!hasCite) errors.push(`[${relPosix}] step with command missing citation: '${line.trim()}'`);
      }
    }

	    const needSourcesMd =
	      args.requireSourceEvidence || args.requireLicenseFields || args.requireSourcePolicy || args.requireNoVerbatimCopy;
	    if (needSourcesMd && exists(sourcesPath)) {
	      const sourcesMd = readText(sourcesPath);
	      const urls = [];

      let sourcePolicy = null;
      if (args.requireSourcePolicy) {
        const configPath = path.join(repoRoot, "agents", "configs", `${domain}.yaml`);
        if (!exists(configPath)) {
          errors.push(`[${relPosix}] missing domain config: agents/configs/${domain}.yaml`);
        } else {
          sourcePolicy = parseDomainSourcePolicy(readText(configPath));
        }
      }

      for (let i = 1; i <= Math.max(3, sourcesCount || 0); i++) {
        const body = blockBody(sourcesMd, new RegExp(`^##\\s+\\[${i}\\]\\s*$`, "m"));
        if (!body) {
          errors.push(`[${relPosix}] sources.md missing block: ## [${i}]`);
          continue;
        }

        const mUrl = body.match(/-\s*URL:\s*(.+?)\s*$/m);
        const url = mUrl ? String(mUrl[1] || "").trim() : "";
        if (!url) errors.push(`[${relPosix}] sources.md missing URL for [${i}]`);
        else urls.push(url);

        if (args.requireLicenseFields) {
          const mLic = body.match(/-\s*License:\s*(.+?)\s*$/m);
          const lic = mLic ? String(mLic[1] || "").trim() : "";
          if (!lic) errors.push(`[${relPosix}] sources.md missing License for [${i}]`);
          else if (/^TODO\b/i.test(lic)) errors.push(`[${relPosix}] sources.md License is TODO for [${i}]`);
          else if (licensePolicy) {
            const c = classifyLicense(lic, licensePolicy);
            if (c.classification === "denied") {
              errors.push(`[${relPosix}] sources.md denied License for [${i}]: '${lic}'`);
            } else if (c.classification === "review") {
              const msg = `[${relPosix}] sources.md License needs review for [${i}]: '${lic}'`;
              const isNonBronze = metaLevel === "silver" || metaLevel === "gold";
              if (args.failOnLicenseReviewAll || (args.failOnLicenseReview && isNonBronze)) errors.push(msg);
              else warnings.push(msg);
            }
          }
        }

	        if (sourcePolicy && url) {
	          if (!/^https?:\/\//i.test(url)) {
	            errors.push(`[${relPosix}] sources.md invalid URL for [${i}] (expected http/https): ${url}`);
	          } else {
	            try {
	              if (!isUrlAllowed(url, sourcePolicy)) {
	                errors.push(`[${relPosix}] sources.md URL blocked by source_policy for [${i}]: ${url}`);
	              }
	            } catch (e) {
	              errors.push(`[${relPosix}] sources.md invalid URL for [${i}]: ${url}`);
	            }
	          }
	        }

	        if (args.requireSourceEvidence) {
	          const okCache = /-\s*Fetch cache:\s*(hit|miss)\s*$/m.test(body);
	          const okBytes = /-\s*Fetch bytes:\s*\d+\s*$/m.test(body);
	          const okSha = /-\s*Fetch sha256:\s*[0-9a-f]{64}\s*$/m.test(body);
	          if (!okCache) errors.push(`[${relPosix}] sources.md missing fetch cache for [${i}]`);
	          if (!okBytes) errors.push(`[${relPosix}] sources.md missing fetch bytes for [${i}]`);
	          if (!okSha) errors.push(`[${relPosix}] sources.md missing fetch sha256 for [${i}]`);
	        }
	      }

	      if (args.requireNoVerbatimCopy) {
	        const cacheDir = path.resolve(repoRoot, args.cacheDir || ".cache/web");
	        const sourcesNorm = [];
	        for (const url of urls) {
	          const cachePath = cachePathForUrl(cacheDir, url);
          if (!exists(cachePath)) {
            errors.push(`[${relPosix}] missing cache for URL (need --cache-dir): ${url}`);
            continue;
          }
          const raw = readText(cachePath);
          sourcesNorm.push(normalizeForCompare(stripHtmlToText(raw)));
        }
	
	        const haystack = sourcesNorm.join(" ");
	        const checkFiles = [skillPath, libraryPath, sourcesPath, troubleshootingPath, edgeCasesPath, examplesPath];
	        for (const p of checkFiles) {
	          if (!exists(p)) continue;
	          const mdText = readText(p);
	          const norm = normalizeForCompare(stripMarkdownToText(mdText));
	          const tokens = norm ? norm.split(/\s+/).filter(Boolean) : [];
	          let match = findVerbatimWindow({ haystack, needleTokens: tokens, windowTokens: 80, strideTokens: 20 });
	          let matchKind = "window>=80 tokens";
	          if (!match) {
	            match = findVerbatimCharWindow({ haystack, needle: norm, windowChars: 400, strideChars: 80 });
	            matchKind = "window>=400 chars";
	          }
	          if (match) {
	            errors.push(
	              `[${relPosix}] possible verbatim copy in ${path.relative(skillDir, p)} (${matchKind}): '${match.slice(0, 160)}...'`,
	            );
	          }
	        }
	      }
	    }

    if (args.requireSafetyNotes) {
      const safetyBody = sectionBody(md, /Safety\s*&\s*Risk\b/) || "";
      const mRisk = safetyBody.match(/^\s*-\s*Risk level:\s*\*\*([a-z]+)\*\*\s*$/im);
      if (!mRisk) errors.push(`[${relPosix}] Safety & Risk missing 'Risk level: **...**'`);
      else if (metaRiskLevel && mRisk[1] !== metaRiskLevel) {
        errors.push(`[${relPosix}] risk level mismatch: skill.md '${mRisk[1]}' != metadata.yaml '${metaRiskLevel}'`);
      }

      const fields = [
        { key: "Irreversible actions", re: /^\s*-\s*Irreversible actions:\s*(.+?)\s*$/im },
        { key: "Privacy/credential handling", re: /^\s*-\s*Privacy\/credential handling:\s*(.+?)\s*$/im },
        { key: "Confirmation requirement", re: /^\s*-\s*Confirmation requirement:\s*(.+?)\s*$/im },
      ];

      for (const f of fields) {
        const m = safetyBody.match(f.re);
        if (!m) errors.push(`[${relPosix}] Safety & Risk missing '${f.key}:'`);
        else if (!String(m[1] || "").trim()) errors.push(`[${relPosix}] Safety & Risk empty '${f.key}:'`);
      }
    }

    if (args.requireNoTodo) {
      const files = [skillPath, libraryPath, sourcesPath, troubleshootingPath, edgeCasesPath, examplesPath];
      for (const p of files) {
        if (!exists(p)) continue;
        const t = readText(p);
        const placeholderRe =
          /^\s*(?:[-*]\s*TODO\b|\d+\.\s*TODO\b|#\s*TODO\b|TODO:\b|[-*]\s*[A-Za-z0-9_ /-]+:\s*TODO\b)/mi;
        if (placeholderRe.test(t)) errors.push(`[${relPosix}] contains TODO placeholder: ${path.relative(skillDir, p)}`);
      }
    }

    if (args.requireNoDuplicates && exists(libraryPath)) {
      const norm = String(libraryMd || "").replace(/\r\n/g, "\n").trim();
      if (norm.length >= 200) {
        const h = sha256Hex(norm);
        const prev = libraryHashes.get(h);
        if (prev && prev !== relPosix) {
          errors.push(`[${relPosix}] library.md duplicates ${prev} (exact match)`);
        } else if (!prev) {
          libraryHashes.set(h, relPosix);
        }
      }
    }

    if (args.requireRiskScan && metaRiskLevel) {
      const text = `${md}\n\n${libraryMd}`;
      const have = riskRank(metaRiskLevel);
      for (const p of RISK_PATTERNS) {
        const need = riskRank(p.min);
        if (need < 0 || have < 0) continue;
        if (have >= need) continue;
        if (p.re.test(text)) {
          errors.push(`[${relPosix}] risk_level too low: '${metaRiskLevel}' < '${p.min}' (matched: ${p.hint})`);
        }
      }
    }
  }
}

if (errors.length > 0) {
  console.error(`Skill validation failed (${errors.length} issues):`);
  for (const e of errors) console.error(`- ${e}`);
  process.exit(1);
}

if (warnings.length > 0) {
  console.error(`Skill validation warnings (${warnings.length}):`);
  for (const w of warnings) console.error(`- ${w}`);
}

console.log(`OK: ${skillDirs.length} skills validated.`);
