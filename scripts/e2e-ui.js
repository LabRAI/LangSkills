#!/usr/bin/env node
/* eslint-disable no-console */

const childProcess = require("child_process");
const fs = require("fs");
const http = require("http");
const https = require("https");
const os = require("os");
const path = require("path");

function assertOk(condition, message) {
  if (!condition) throw new Error(message);
}

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

function copyTree(srcPath, dstPath) {
  const st = fs.statSync(srcPath);
  if (st.isDirectory()) {
    ensureDir(dstPath);
    const entries = fs.readdirSync(srcPath, { withFileTypes: true });
    for (const entry of entries) {
      const src = path.join(srcPath, entry.name);
      const dst = path.join(dstPath, entry.name);
      if (entry.isDirectory()) copyTree(src, dst);
      else if (entry.isFile()) {
        ensureDir(path.dirname(dst));
        fs.copyFileSync(src, dst);
      }
    }
    return;
  }
  if (st.isFile()) {
    ensureDir(path.dirname(dstPath));
    fs.copyFileSync(srcPath, dstPath);
    return;
  }
  throw new Error(`Unsupported file type: ${srcPath}`);
}

function writeText(filePath, content) {
  ensureDir(path.dirname(filePath));
  fs.writeFileSync(filePath, content, "utf8");
}

function run(cmd, args, options = {}) {
  const p = childProcess.spawnSync(cmd, args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"], ...options });
  return {
    status: typeof p.status === "number" ? p.status : 1,
    stdout: p.stdout || "",
    stderr: p.stderr || "",
  };
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
          "User-Agent": "skill-e2e-ui",
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

async function waitForHttp(url, timeoutMs = 20000) {
  const start = Date.now();
  let lastError = null;
  while (Date.now() - start < timeoutMs) {
    try {
      const r = await request(url, 5000);
      if (r.statusCode >= 200 && r.statusCode < 300) return r;
      lastError = new Error(`HTTP ${r.statusCode}: ${url}`);
    } catch (e) {
      lastError = e;
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw lastError || new Error("Timeout");
}

function tempDir(prefix) {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

function pickPort() {
  return 47000 + Math.floor(Math.random() * 10000);
}

async function startServeSite({ repoRoot, dir, host, port }) {
  const args = [path.join(repoRoot, "scripts", "serve-site.js"), "--dir", dir, "--host", host, "--port", String(port)];
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

function mustLoadPlaywright() {
  try {
    // eslint-disable-next-line global-require
    return require("playwright");
  } catch (e) {
    console.error("Missing dev dependency: playwright");
    console.error("Install:");
    console.error("  npm install");
    console.error("  npx playwright install chromium");
    console.error("");
    console.error(String(e && e.message ? e.message : e));
    process.exit(1);
  }
}

async function runWebsiteE2E({ browser, baseUrl }) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const debug = [];
  page.on("console", (m) => debug.push(`console.${m.type()}: ${m.text()}`));
  page.on("pageerror", (e) => debug.push(`pageerror: ${String(e && e.message ? e.message : e)}`));
  page.on("requestfailed", (r) => debug.push(`requestfailed: ${r.url()} (${(r.failure() && r.failure().errorText) || "unknown"})`));
  page.on("dialog", async (d) => {
    debug.push(`dialog.${d.type()}: ${d.message()}`);
    try {
      await d.dismiss();
    } catch {
      // ignore
    }
  });

  try {
    // Headless Chromium clipboard can be flaky depending on origin/permissions.
    // Stub clipboard write so we can reliably assert the UI state change ("Copied") after user gesture.
    await page.addInitScript(() => {
      try {
        Object.defineProperty(navigator, "clipboard", {
          value: { writeText: async () => {} },
          configurable: true,
        });
      } catch {
        // ignore
      }
    });

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => {
      const c = document.getElementById("count");
      return c && Number(c.textContent || "0") > 0;
    });

    // Atomic skill: fetch library/skill/sources.
    await page.fill("#q", "linux/filesystem/find-files");
    await page.waitForSelector(".row");
    await page.click(".row");
    await page.waitForSelector("#panel:not(.hidden)");
    await page.waitForFunction(() => (document.getElementById("tabLibrary").textContent || "").includes("# Library"));

    await page.click('button.tab[data-tab="skill"]');
    await page.waitForFunction(() => (document.getElementById("tabSkill").textContent || "").includes("## Goal"));

    await page.click('button.tab[data-tab="sources"]');
    await page.waitForFunction(() => (document.getElementById("tabSources").textContent || "").includes("# Sources"));

    // Parameterized: template render.
    await page.fill("#q", "linux/m2-param/p-000001");
    await page.waitForSelector(".row");
    await page.click(".row");
    await page.waitForFunction(() => {
      const t = document.getElementById("tabLibrary").textContent || "";
      return t.includes("linux/m2-param/p-000001") && !t.includes("{{id}}");
    });

    await page.click("#copyBtn");
    await page.waitForFunction(() => (document.getElementById("copyBtn").textContent || "").includes("Copied"));
  } catch (e) {
    const snippet = debug.slice(-60).join("\n");
    throw new Error(`website e2e failed: ${String(e && e.message ? e.message : e)}\n---\n${snippet}`);
  } finally {
    await ctx.close();
  }
}

async function runPluginE2E({ browser, baseUrl }) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const debug = [];
  page.on("console", (m) => debug.push(`console.${m.type()}: ${m.text()}`));
  page.on("pageerror", (e) => debug.push(`pageerror: ${String(e && e.message ? e.message : e)}`));
  page.on("requestfailed", (r) => debug.push(`requestfailed: ${r.url()} (${(r.failure() && r.failure().errorText) || "unknown"})`));
  page.on("dialog", async (d) => {
    debug.push(`dialog.${d.type()}: ${d.message()}`);
    try {
      await d.dismiss();
    } catch {
      // ignore
    }
  });

  await page.addInitScript(
    ({ baseUrlValue }) => {
      window.__e2e = { opened: [], baseUrl: baseUrlValue };

      const storage = { baseUrl: baseUrlValue };
      window.chrome = {
        storage: {
          local: {
            get: async () => ({ baseUrl: storage.baseUrl }),
            set: async (obj) => {
              if (obj && typeof obj.baseUrl === "string") storage.baseUrl = obj.baseUrl;
            },
          },
        },
        tabs: {
          create: async ({ url }) => {
            window.__e2e.opened.push(String(url || ""));
          },
        },
      };

      Object.defineProperty(navigator, "clipboard", {
        value: {
          writeText: async () => {
            // ok
          },
        },
        configurable: true,
      });
    },
    { baseUrlValue: baseUrl },
  );

  try {
    await page.goto(`${baseUrl}plugin/chrome/popup.html`, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => {
      const c = document.getElementById("count");
      return c && Number(c.textContent || "0") > 0;
    });

    await page.fill("#q", "linux/m2-param/p-000001");
    await page.waitForSelector(".item");
    await page.click(".item");
    await page.waitForSelector("#detail:not(.hidden)");
    await page.waitForFunction(() => {
      const t = document.getElementById("library").textContent || "";
      return t.includes("linux/m2-param/p-000001") && !t.includes("{{id}}");
    });

    await page.click("#copy");
    await page.waitForFunction(() => (document.getElementById("copy").textContent || "").includes("Copied"));

    await page.click("#open");
    const expected = `${baseUrl}#${encodeURIComponent("linux/m2-param/p-000001")}`;
    await page.waitForFunction(
      (u) => window.__e2e && Array.isArray(window.__e2e.opened) && window.__e2e.opened.includes(u),
      expected,
    );
  } catch (e) {
    const snippet = debug.slice(-60).join("\n");
    throw new Error(`plugin e2e failed: ${String(e && e.message ? e.message : e)}\n---\n${snippet}`);
  } finally {
    await ctx.close();
  }
}

async function main() {
  const repoRoot = path.resolve(__dirname, "..");
  const outDir = tempDir("skill-e2e-ui-");
  const tmpSkillsRoot = tempDir("skill-e2e-skills-");

  // Build site into an isolated output dir from a tiny skills dataset to keep browser e2e fast/stable.
  // Copy plugin assets into the same output dir so one origin can serve both website + plugin UI.
  const repoSkillsRoot = path.join(repoRoot, "skills");
  assertOk(exists(repoSkillsRoot), `Missing repo skills root: ${repoSkillsRoot}`);

  copyTree(
    path.join(repoSkillsRoot, "linux", "filesystem", "find-files"),
    path.join(tmpSkillsRoot, "linux", "filesystem", "find-files"),
  );
  copyTree(
    path.join(repoSkillsRoot, "linux", "m2-templates", "parameterized-template"),
    path.join(tmpSkillsRoot, "linux", "m2-templates", "parameterized-template"),
  );
  writeText(
    path.join(tmpSkillsRoot, "skillsets.json"),
    JSON.stringify(
      {
        schema_version: 1,
        parameterized: [
          {
            template_id: "linux/m2-templates/parameterized-template",
            output_domain: "linux",
            output_topic: "m2-param",
            count: 20,
            start: 1,
            slug_prefix: "p-",
            slug_pad: 6,
            title_template: "M2 参数化技能实例 {slug}",
            risk_level: "low",
            levels: { default: "bronze", silver_every: 0, gold_every: 0 },
          },
        ],
      },
      null,
      2,
    ),
  );

  const build = run(
    process.execPath,
    [path.join(repoRoot, "scripts", "build-site.js"), "--out", outDir, "--skills-root", tmpSkillsRoot],
    { cwd: repoRoot },
  );
  assertOk(build.status === 0, `build-site failed:\n${build.stderr || build.stdout}`);
  assertOk(exists(path.join(outDir, "index.json")), `build-site did not produce index.json: ${outDir}`);

  copyTree(path.join(repoRoot, "plugin"), path.join(outDir, "plugin"));

  const host = "127.0.0.1";
  const port = pickPort();
  const baseUrl = `http://${host}:${port}/`;

  const server = await startServeSite({ repoRoot, dir: outDir, host, port });
  try {
    await waitForHttp(`${baseUrl}index.json`, 30000);

    const { chromium } = mustLoadPlaywright();
    const browser = await chromium.launch({ headless: true });
    try {
      await runWebsiteE2E({ browser, baseUrl });
      await runPluginE2E({ browser, baseUrl });
      console.log("OK: e2e-ui passed");
      console.log(`- baseUrl: ${baseUrl}`);
      console.log(`- outDir: ${outDir}`);
    } finally {
      await browser.close();
    }
  } catch (e) {
    const out = Buffer.concat(server.stdout).toString("utf8");
    const err = Buffer.concat(server.stderr).toString("utf8");
    if (out.trim()) console.error(`serve-site stdout:\n${out}`);
    if (err.trim()) console.error(`serve-site stderr:\n${err}`);
    throw e;
  } finally {
    await stopProc(server.proc);
  }
}

main().catch((e) => {
  console.error(String(e && e.stack ? e.stack : e));
  process.exit(1);
});
