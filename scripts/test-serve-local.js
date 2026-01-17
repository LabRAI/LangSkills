#!/usr/bin/env node
/* eslint-disable no-console */

const childProcess = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const http = require("http");
const https = require("https");

function assertOk(condition, message) {
  if (!condition) throw new Error(message);
}

function request(url, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const lib = u.protocol === "https:" ? https : http;
    const req = lib.request(
      u,
      {
        method: "GET",
        headers: {
          "User-Agent": "skill-test-serve-local",
          Accept: "*/*",
        },
      },
      (res) => {
        const chunks = [];
        res.on("data", (c) => chunks.push(c));
        res.on("end", () => {
          resolve({
            statusCode: res.statusCode || 0,
            headers: res.headers || {},
            body: Buffer.concat(chunks).toString("utf8"),
          });
        });
      },
    );
    req.on("error", reject);
    req.setTimeout(timeoutMs, () => {
      req.destroy(new Error(`Timeout after ${timeoutMs}ms`));
    });
    req.end();
  });
}

async function waitForHttp(url, timeoutMs = 15000) {
  const start = Date.now();
  let lastError = null;
  while (Date.now() - start < timeoutMs) {
    try {
      const r = await request(url, 5000);
      if (r.statusCode >= 200 && r.statusCode < 500) return r;
      lastError = new Error(`HTTP ${r.statusCode}`);
    } catch (e) {
      lastError = e;
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw lastError || new Error("Timeout");
}

function run(cmd, args, options = {}) {
  const p = childProcess.spawnSync(cmd, args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    ...options,
  });
  return {
    status: typeof p.status === "number" ? p.status : 1,
    stdout: p.stdout || "",
    stderr: p.stderr || "",
  };
}

function tempDir(prefix) {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

function pickPort() {
  // Avoid common ports; keep stable-ish range to reduce collisions.
  return 46000 + Math.floor(Math.random() * 10000);
}

async function startServeLocal({ repoRoot, outDir, host, port, noBuild }) {
  const args = [
    path.join(repoRoot, "scripts", "serve-local.js"),
    "--out",
    outDir,
    "--host",
    host,
    "--port",
    String(port),
    ...(noBuild ? ["--no-build"] : []),
  ];
  const proc = childProcess.spawn(process.execPath, args, { cwd: repoRoot, stdio: ["ignore", "pipe", "pipe"] });
  const stdout = [];
  const stderr = [];
  proc.stdout.on("data", (c) => stdout.push(c));
  proc.stderr.on("data", (c) => stderr.push(c));
  return { proc, stdout, stderr };
}

async function stopProc(proc) {
  try {
    proc.kill("SIGINT");
  } catch {
    // ignore
  }
  await new Promise((r) => setTimeout(r, 200));
  if (!proc.killed) {
    try {
      proc.kill("SIGKILL");
    } catch {
      // ignore
    }
  }
}

function assertContentType(headers, expectedPrefix, label) {
  const ct = String(headers["content-type"] || "").toLowerCase();
  assertOk(ct.startsWith(expectedPrefix), `${label} content-type mismatch: '${ct}' (expected '${expectedPrefix}*')`);
}

async function runHttpChecks({ repoRoot, baseUrl }) {
  const healthResp = await waitForHttp(`${baseUrl}api/health`, 30000);
  assertOk(healthResp.statusCode === 200, `api/health HTTP ${healthResp.statusCode}`);
  assertContentType(healthResp.headers, "application/json", "api/health");
  assertOk(String(healthResp.headers["cache-control"] || "").toLowerCase().includes("no-store"), "api/health missing Cache-Control: no-store");
  const healthJson = JSON.parse(healthResp.body);
  assertOk(healthJson && healthJson.ok === true, "api/health missing ok=true");

  const summaryResp = await waitForHttp(`${baseUrl}api/summary`, 30000);
  assertOk(summaryResp.statusCode === 200, `api/summary HTTP ${summaryResp.statusCode}`);
  assertContentType(summaryResp.headers, "application/json", "api/summary");
  assertOk(
    String(summaryResp.headers["cache-control"] || "").toLowerCase().includes("no-store"),
    "api/summary missing Cache-Control: no-store",
  );
  const summaryJson = JSON.parse(summaryResp.body);
  assertOk(summaryJson && summaryJson.ok === true, "api/summary missing ok=true");
  assertOk(Number(summaryJson.skills_count || 0) > 0, "api/summary skills_count <= 0");

  const indexUrl = `${baseUrl}index.json`;
  const indexResp = await waitForHttp(indexUrl, 30000);
  assertOk(indexResp.statusCode === 200, `index.json HTTP ${indexResp.statusCode}`);
  assertContentType(indexResp.headers, "application/json", "index.json");
  assertOk(
    String(indexResp.headers["cache-control"] || "").toLowerCase().includes("no-store"),
    "index.json missing Cache-Control: no-store",
  );

  const parsed = JSON.parse(indexResp.body);
  assertOk(Number(parsed.schema_version || 0) >= 2, `schema_version < 2 (got ${parsed.schema_version})`);
  assertOk(Number(parsed.skills_count || 0) > 0, "skills_count <= 0");
  assertOk(parsed.counts && typeof parsed.counts === "object", "missing counts");
  assertOk(Array.isArray(parsed.skills) && parsed.skills.length === Number(parsed.skills_count), "skills length mismatch");

  const searchResp = await request(`${baseUrl}api/search?q=${encodeURIComponent("find-files")}&limit=20`, 15000);
  assertOk(searchResp.statusCode === 200, `api/search HTTP ${searchResp.statusCode}`);
  assertContentType(searchResp.headers, "application/json", "api/search");
  const searchJson = JSON.parse(searchResp.body);
  assertOk(searchJson && searchJson.ok === true, "api/search missing ok=true");
  assertOk(Number(searchJson.total || 0) > 0, "api/search total <= 0");
  assertOk(Array.isArray(searchJson.results) && searchJson.results.length > 0, "api/search results empty");
  assertOk(
    searchJson.results.some((s) => s && s.id === "linux/filesystem/find-files"),
    "api/search did not include linux/filesystem/find-files",
  );

  const skillResp2 = await request(`${baseUrl}api/skill?id=${encodeURIComponent("linux/filesystem/find-files")}`, 15000);
  assertOk(skillResp2.statusCode === 200, `api/skill HTTP ${skillResp2.statusCode}`);
  assertContentType(skillResp2.headers, "application/json", "api/skill");
  const skillJson2 = JSON.parse(skillResp2.body);
  assertOk(skillJson2 && skillJson2.ok === true, "api/skill missing ok=true");
  assertOk(skillJson2.skill && skillJson2.skill.id === "linux/filesystem/find-files", "api/skill id mismatch");

  const rootResp = await request(baseUrl, 15000);
  assertOk(rootResp.statusCode === 200, `/ HTTP ${rootResp.statusCode}`);
  assertContentType(rootResp.headers, "text/html", "/");
  assertOk(rootResp.body.includes("<title>Skill Repo</title>"), "root HTML missing title");

  const appResp = await request(`${baseUrl}app.js`, 15000);
  assertOk(appResp.statusCode === 200, `app.js HTTP ${appResp.statusCode}`);
  assertContentType(appResp.headers, "application/javascript", "app.js");
  assertOk(
    String(appResp.headers["cache-control"] || "").toLowerCase().includes("no-store"),
    "app.js missing Cache-Control: no-store",
  );

  const cssResp = await request(`${baseUrl}style.css`, 15000);
  assertOk(cssResp.statusCode === 200, `style.css HTTP ${cssResp.statusCode}`);
  assertContentType(cssResp.headers, "text/css", "style.css");
  assertOk(
    String(cssResp.headers["cache-control"] || "").toLowerCase().includes("no-store"),
    "style.css missing Cache-Control: no-store",
  );

  const libUrl = `${baseUrl}skills/linux/filesystem/find-files/library.md`;
  const libResp = await request(libUrl, 15000);
  assertOk(libResp.statusCode === 200, `library.md HTTP ${libResp.statusCode}`);
  assertContentType(libResp.headers, "text/markdown", "library.md");
  assertOk(libResp.body.includes("# Library"), "library.md missing '# Library' header");
  assertOk(
    String(libResp.headers["cache-control"] || "").toLowerCase().includes("no-store"),
    "library.md missing Cache-Control: no-store",
  );

  const skillResp = await request(`${baseUrl}skills/linux/filesystem/find-files/skill.md`, 15000);
  assertOk(skillResp.statusCode === 200, `skill.md HTTP ${skillResp.statusCode}`);
  assertContentType(skillResp.headers, "text/markdown", "skill.md");
  assertOk(skillResp.body.trimStart().startsWith("# "), "skill.md missing top-level title header");
  assertOk(skillResp.body.includes("## Goal"), "skill.md missing '## Goal' section");

  const sourcesResp = await request(`${baseUrl}skills/linux/filesystem/find-files/reference/sources.md`, 15000);
  assertOk(sourcesResp.statusCode === 200, `sources.md HTTP ${sourcesResp.statusCode}`);
  assertContentType(sourcesResp.headers, "text/markdown", "sources.md");
  assertOk(sourcesResp.body.includes("# Sources"), "sources.md missing '# Sources' header");

  const templateResp = await request(`${baseUrl}skills/linux/m2-templates/parameterized-template/library.md`, 15000);
  assertOk(templateResp.statusCode === 200, `template library.md HTTP ${templateResp.statusCode}`);
  assertContentType(templateResp.headers, "text/markdown", "template library.md");
  assertOk(templateResp.body.includes("{{id}}"), "template library.md missing '{{id}}' placeholder");

  const missingResp = await request(`${baseUrl}skills/linux/filesystem/find-files/nope.md`, 15000);
  assertOk(missingResp.statusCode === 404, `missing file should 404 (got ${missingResp.statusCode})`);

  const dirResp = await request(`${baseUrl}skills/`, 15000);
  assertOk(dirResp.statusCode === 404, `/skills/ should 404 (got ${dirResp.statusCode})`);

  // Path traversal attempts should never escape the served root. The WHATWG URL parser
  // normalizes many ".." variants, so accept either 400 (blocked) or 404 (not found),
  // but never 200.
  const traversalResp = await request(`${baseUrl}..%2f..%2fREADME.md`, 15000);
  assertOk(traversalResp.statusCode !== 200, `path traversal should not 200 (got ${traversalResp.statusCode})`);

  // CLI online smoke against serve-local.
  const cliShow = run(
    process.execPath,
    [
      path.join(repoRoot, "cli", "skill.js"),
      "show",
      "linux/m2-param/p-000001",
      "--file",
      "library",
      "--base-url",
      baseUrl,
    ],
    { cwd: repoRoot },
  );
  assertOk(cliShow.status === 0, `cli show failed: ${cliShow.stderr || cliShow.stdout}`);
  assertOk(cliShow.stdout.includes("linux/m2-param/p-000001"), "cli show did not render {{id}} placeholder");
  assertOk(!cliShow.stdout.includes("{{id}}"), "cli show still contains '{{id}}' placeholder");

  const cliShowSkill = run(
    process.execPath,
    [
      path.join(repoRoot, "cli", "skill.js"),
      "show",
      "linux/m2-param/p-000001",
      "--file",
      "skill",
      "--base-url",
      baseUrl,
    ],
    { cwd: repoRoot },
  );
  assertOk(cliShowSkill.status === 0, `cli show skill failed: ${cliShowSkill.stderr || cliShowSkill.stdout}`);
  assertOk(cliShowSkill.stdout.includes("linux/m2-param/p-000001"), "cli show skill did not render {{id}} placeholder");
  assertOk(!cliShowSkill.stdout.includes("{{id}}"), "cli show skill still contains '{{id}}' placeholder");

  return { parsed };
}

async function main() {
  const repoRoot = path.resolve(__dirname, "..");
  const outDir = tempDir("skill-serve-local-");
  const host = "127.0.0.1";

  // 1) Build + serve
  const port1 = pickPort();
  const baseUrl1 = `http://${host}:${port1}/`;
  const s1 = await startServeLocal({ repoRoot, outDir, host, port: port1, noBuild: false });
  try {
    const { parsed } = await runHttpChecks({ repoRoot, baseUrl: baseUrl1 });
    console.log("OK: serve-local(build+serve) passed");
    console.log(`- outDir: ${outDir}`);
    console.log(`- baseUrl: ${baseUrl1}`);
    console.log(`- skills_count: ${parsed.skills_count}`);
  } finally {
    await stopProc(s1.proc);
  }

  // 2) Serve only (no rebuild)
  const port2 = pickPort();
  const baseUrl2 = `http://${host}:${port2}/`;
  const s2 = await startServeLocal({ repoRoot, outDir, host, port: port2, noBuild: true });
  try {
    const { parsed } = await runHttpChecks({ repoRoot, baseUrl: baseUrl2 });
    console.log("OK: serve-local(--no-build) passed");
    console.log(`- baseUrl: ${baseUrl2}`);
    console.log(`- skills_count: ${parsed.skills_count}`);
  } finally {
    await stopProc(s2.proc);
  }
}

main().catch((e) => {
  console.error(String(e && e.stack ? e.stack : e));
  process.exit(1);
});
