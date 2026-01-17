#!/usr/bin/env node
/* eslint-disable no-console */

const http = require("http");
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

function parseArgs(argv) {
  const out = { dir: "website/dist", port: 4173, host: "127.0.0.1" };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--dir") {
      out.dir = argv[i + 1] || out.dir;
      i++;
    } else if (a === "--port") {
      out.port = Number(argv[i + 1] || out.port);
      i++;
    } else if (a === "--host") {
      out.host = argv[i + 1] || out.host;
      i++;
    }
  }
  return out;
}

function contentType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".html") return "text/html; charset=utf-8";
  if (ext === ".css") return "text/css; charset=utf-8";
  if (ext === ".js") return "application/javascript; charset=utf-8";
  if (ext === ".json") return "application/json; charset=utf-8";
  if (ext === ".md") return "text/markdown; charset=utf-8";
  if (ext === ".svg") return "image/svg+xml";
  if (ext === ".png") return "image/png";
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg";
  return "application/octet-stream";
}

function safeJoin(rootDir, reqPath) {
  const cleaned = reqPath.replace(/\\/g, "/").replace(/\0/g, "");
  const rel = cleaned.startsWith("/") ? cleaned.slice(1) : cleaned;
  const full = path.resolve(rootDir, rel);
  const root = path.resolve(rootDir);
  const prefix = root.endsWith(path.sep) ? root : `${root}${path.sep}`;
  if (full !== root && !full.startsWith(prefix)) return null;
  return full;
}

function normalize(text) {
  return String(text || "").toLowerCase();
}

function json(res, statusCode, obj) {
  const body = JSON.stringify(obj, null, 2);
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
  res.end(body);
}

function parseBoolParam(value) {
  const v = String(value || "").trim().toLowerCase();
  if (v === "1" || v === "true" || v === "yes") return true;
  if (v === "0" || v === "false" || v === "no") return false;
  return null;
}

function parseIntParam(value, fallback) {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.floor(n);
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const repoRoot = path.resolve(__dirname, "..");
  const dir = path.resolve(repoRoot, args.dir);
  if (!exists(dir)) {
    console.error(`Missing directory: ${dir}`);
    console.error(`Tip: build first: node scripts/build-site.js --out ${args.dir}`);
    process.exit(1);
  }

  const indexPath = path.join(dir, "index.json");
  let cachedIndex = null;
  let cachedIndexMtimeMs = null;
  let cachedSkills = null; // [{...skill, _haystack}]
  let cachedById = null; // Map(id -> skillWithHaystack)

  function loadIndexCache() {
    if (!exists(indexPath)) {
      const err = new Error(`Missing index.json: ${indexPath}`);
      err.code = "INDEX_MISSING";
      throw err;
    }
    const st = fs.statSync(indexPath);
    const mtimeMs = Number(st.mtimeMs || 0);
    if (cachedIndex && cachedIndexMtimeMs === mtimeMs && cachedSkills && cachedById) {
      return { index: cachedIndex, skills: cachedSkills, byId: cachedById };
    }

    const raw = fs.readFileSync(indexPath, "utf8");
    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch (e) {
      const err = new Error(`Invalid JSON: ${indexPath} (${String(e && e.message ? e.message : e)})`);
      err.code = "INDEX_INVALID";
      throw err;
    }

    const list = Array.isArray(parsed.skills) ? parsed.skills : [];
    const skills = list.map((s) => {
      const id = s && s.id ? String(s.id) : "";
      const title = s && s.title ? String(s.title) : "";
      const domain = s && s.domain ? String(s.domain) : "";
      const level = s && s.level ? String(s.level) : "bronze";
      const risk_level = s && s.risk_level ? String(s.risk_level) : "low";
      const template = s && s.template ? String(s.template) : "";
      const kind = s && s.kind ? String(s.kind) : "";
      const out = { id, title, domain, level, risk_level, ...(template ? { template } : null), ...(kind ? { kind } : null) };
      out._haystack = normalize(`${out.id} ${out.title} ${out.domain}`);
      return out;
    });

    const byId = new Map();
    for (const s of skills) {
      if (s && s.id) byId.set(s.id, s);
    }

    cachedIndex = parsed;
    cachedIndexMtimeMs = mtimeMs;
    cachedSkills = skills;
    cachedById = byId;
    return { index: cachedIndex, skills: cachedSkills, byId: cachedById };
  }

  function publicSkill(s) {
    if (!s) return null;
    const { _haystack, ...rest } = s;
    return rest;
  }

  const server = http.createServer((req, res) => {
    const url = new URL(req.url || "/", `http://${req.headers.host || "localhost"}`);
    if (url.pathname === "/api/health") {
      json(res, 200, { ok: true, service: "serve-site", ts: new Date().toISOString() });
      return;
    }

    if (url.pathname === "/api/summary") {
      try {
        const { index } = loadIndexCache();
        json(res, 200, {
          ok: true,
          schema_version: Number(index && index.schema_version ? index.schema_version : 0),
          generated_at: String(index && index.generated_at ? index.generated_at : ""),
          skills_count: Number(index && index.skills_count ? index.skills_count : 0),
          counts: index && typeof index.counts === "object" ? index.counts : null,
        });
      } catch (e) {
        json(res, 500, { ok: false, error: String(e && e.message ? e.message : e) });
      }
      return;
    }

    if (url.pathname === "/api/skill") {
      const id = String(url.searchParams.get("id") || "").trim();
      if (!id) {
        json(res, 400, { ok: false, error: "Missing 'id' query param" });
        return;
      }
      try {
        const { byId } = loadIndexCache();
        const s = byId.get(id);
        if (!s) {
          json(res, 404, { ok: false, error: "Not found" });
          return;
        }
        json(res, 200, { ok: true, skill: publicSkill(s) });
      } catch (e) {
        json(res, 500, { ok: false, error: String(e && e.message ? e.message : e) });
      }
      return;
    }

    if (url.pathname === "/api/search") {
      const qRaw = String(url.searchParams.get("q") || "");
      const q = normalize(qRaw.trim());
      const limitRaw = url.searchParams.get("limit");
      const offsetRaw = url.searchParams.get("offset");
      const atomicOnly = parseBoolParam(url.searchParams.get("atomic_only"));

      const limit = Math.max(1, Math.min(500, parseIntParam(limitRaw, 250)));
      const offset = Math.max(0, parseIntParam(offsetRaw, 0));

      try {
        const { skills } = loadIndexCache();
        const pool = atomicOnly ? skills.filter((s) => !(s && s.template)) : skills;
        const filtered = q ? pool.filter((s) => String(s && s._haystack ? s._haystack : "").includes(q)) : pool;
        const total = filtered.length;
        const results = filtered.slice(offset, offset + limit).map(publicSkill);
        json(res, 200, { ok: true, q: qRaw, total, limit, offset, results });
      } catch (e) {
        json(res, 500, { ok: false, error: String(e && e.message ? e.message : e) });
      }
      return;
    }

    let reqPath = url.pathname;
    if (reqPath === "/") reqPath = "/index.html";

    const filePath = safeJoin(dir, reqPath);
    if (!filePath) {
      res.writeHead(400, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("Bad request");
      return;
    }

    if (!exists(filePath) || fs.statSync(filePath).isDirectory()) {
      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("Not found");
      return;
    }

    const stream = fs.createReadStream(filePath);
    stream.on("error", () => {
      res.writeHead(500, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("Internal error");
    });

    res.writeHead(200, {
      "Content-Type": contentType(filePath),
      "Cache-Control": "no-store",
    });
    stream.pipe(res);
  });

  server.listen(args.port, args.host, () => {
    console.log(`Serving: ${dir}`);
    console.log(`URL: http://${args.host}:${args.port}/`);
  });
}

main();

