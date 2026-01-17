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

function normalizeUrlKey(raw) {
  const v = String(raw || "").trim();
  if (!v) return "";
  if (!/^https?:\/\//i.test(v)) return v;
  try {
    const u = new URL(v);
    u.hash = "";
    if ((u.protocol === "http:" && u.port === "80") || (u.protocol === "https:" && u.port === "443")) u.port = "";
    if (u.pathname && u.pathname.length > 1) u.pathname = u.pathname.replace(/\/+$/g, "");
    return u.toString();
  } catch {
    return v;
  }
}

function collectReferenceSourcesMdFiles(skillsRoot) {
  const out = [];
  const root = String(skillsRoot || "").trim();
  if (!root || !exists(root)) return out;

  const stack = [root];
  while (stack.length > 0) {
    const dir = stack.pop();
    let entries = [];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      continue;
    }

    for (const e of entries) {
      const name = e.name;
      if (!name) continue;
      if (name === ".git" || name === "node_modules" || name === ".cache" || name === "runs") continue;
      const full = path.join(dir, name);
      if (e.isDirectory()) {
        stack.push(full);
        continue;
      }
      if (!e.isFile()) continue;
      if (name !== "sources.md") continue;
      if (path.basename(path.dirname(full)) !== "reference") continue;
      out.push(full);
    }
  }
  return out;
}

function extractUrlLicensePairs(markdown) {
  const lines = String(markdown || "")
    .replace(/\r\n/g, "\n")
    .split("\n")
    .map((l) => l.trimEnd());

  const pairs = [];
  let currentUrl = null;
  let currentLicense = null;

  const flush = () => {
    if (!currentUrl || !currentLicense) return;
    pairs.push({ url: currentUrl, license: currentLicense });
    currentUrl = null;
    currentLicense = null;
  };

  for (const line of lines) {
    const mUrl = line.match(/^\-\s*URL:\s*(.+?)\s*$/);
    if (mUrl) {
      flush();
      currentUrl = String(mUrl[1] || "").trim();
      continue;
    }
    const mLic = line.match(/^\-\s*License:\s*(.+?)\s*$/);
    if (mLic) {
      currentLicense = String(mLic[1] || "").trim();
      flush();
    }
  }
  return pairs;
}

function loadUrlLicensePairsFromSourcesMd(filePath) {
  const p = String(filePath || "").trim();
  if (!p || !exists(p)) return [];
  try {
    return extractUrlLicensePairs(readText(p));
  } catch {
    return [];
  }
}

function buildUrlLicenseMapFromSkills(skillsRoot) {
  const map = new Map();
  for (const p of collectReferenceSourcesMdFiles(skillsRoot)) {
    let text = "";
    try {
      text = readText(p);
    } catch {
      continue;
    }
    const pairs = extractUrlLicensePairs(text);
    for (const pair of pairs) {
      const url = String(pair.url || "").trim();
      const license = String(pair.license || "").trim();
      if (!url || !license) continue;
      if (/^TODO\b/i.test(license)) continue;
      if (/^unknown\b/i.test(license)) continue;
      const key = normalizeUrlKey(url);
      if (!key) continue;
      if (!map.has(key)) map.set(key, license);
    }
  }
  return map;
}

let cached = null;

function getRepoUrlLicenseMap(repoRoot) {
  const root = path.resolve(String(repoRoot || "."));
  if (cached && cached.root === root) return cached.map;
  const skillsRoot = path.join(root, "skills");
  const map = buildUrlLicenseMapFromSkills(skillsRoot);
  cached = { root, map };
  return map;
}

function lookupLicenseForUrl(url, licenseMap) {
  const key = normalizeUrlKey(url);
  if (!key) return null;
  const map = licenseMap instanceof Map ? licenseMap : null;
  return map ? map.get(key) || null : null;
}

module.exports = {
  getRepoUrlLicenseMap,
  lookupLicenseForUrl,
  loadUrlLicensePairsFromSourcesMd,
  normalizeUrlKey,
};
