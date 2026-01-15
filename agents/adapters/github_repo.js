/* eslint-disable no-console */

const fs = require("fs");
const path = require("path");

function normalizePosix(p) {
  return String(p || "").replace(/\\/g, "/");
}

function globToRegExp(glob) {
  const g = normalizePosix(String(glob || "").trim());
  if (!g) return null;

  let re = "^";
  for (let i = 0; i < g.length; i++) {
    const ch = g[i];
    const next = g[i + 1];
    if (ch === "*" && next === "*") {
      re += ".*";
      i++;
      continue;
    }
    if (ch === "*") {
      re += "[^/]*";
      continue;
    }
    if (ch === "?") {
      re += "[^/]";
      continue;
    }
    re += ch.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }
  re += "$";
  return new RegExp(re);
}

function matchAnyGlob(relPosixPath, globs) {
  const p = normalizePosix(relPosixPath);
  const list = Array.isArray(globs) ? globs : [];
  for (const g of list) {
    const r = globToRegExp(g);
    if (r && r.test(p)) return true;
  }
  return false;
}

function walkFiles(rootDir, onFile) {
  const entries = fs.readdirSync(rootDir, { withFileTypes: true });
  for (const entry of entries) {
    const full = path.join(rootDir, entry.name);
    if (entry.isDirectory()) walkFiles(full, onFile);
    else if (entry.isFile()) onFile(full);
  }
}

function discoverLocalRepoFiles({ repoDir, include_globs }) {
  const root = path.resolve(String(repoDir || ""));
  if (!root) throw new Error("discoverLocalRepoFiles: missing repoDir");
  if (!fs.existsSync(root)) throw new Error(`discoverLocalRepoFiles: repoDir not found: ${root}`);

  const matches = [];
  walkFiles(root, (full) => {
    const rel = normalizePosix(path.relative(root, full));
    if (matchAnyGlob(rel, include_globs)) matches.push(rel);
  });
  matches.sort();
  return matches;
}

function readLocalRepoFile({ repoDir, relPath }) {
  const root = path.resolve(String(repoDir || ""));
  const rel = normalizePosix(String(relPath || ""));
  if (!rel) throw new Error("readLocalRepoFile: missing relPath");
  const full = path.join(root, rel);
  return fs.readFileSync(full, "utf8");
}

module.exports = { discoverLocalRepoFiles, readLocalRepoFile };

