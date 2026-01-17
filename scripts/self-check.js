#!/usr/bin/env node
/* eslint-disable no-console */

const childProcess = require("child_process");
const fs = require("fs");
const http = require("http");
const https = require("https");
const os = require("os");
const path = require("path");

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

function runAsync(cmd, args, options = {}) {
  const timeoutMs = Number(options.timeoutMs || 30000);
  return new Promise((resolve) => {
    const proc = childProcess.spawn(cmd, args, {
      stdio: ["ignore", "pipe", "pipe"],
      ...options,
    });
    const stdout = [];
    const stderr = [];
    proc.stdout.on("data", (c) => stdout.push(c));
    proc.stderr.on("data", (c) => stderr.push(c));

    let done = false;
    const finish = (status) => {
      if (done) return;
      done = true;
      resolve({
        status: typeof status === "number" ? status : 1,
        stdout: Buffer.concat(stdout).toString("utf8"),
        stderr: Buffer.concat(stderr).toString("utf8"),
      });
    };

    const timer = setTimeout(() => {
      try {
        proc.kill();
      } catch {
        // ignore
      }
      finish(1);
    }, timeoutMs);
    proc.on("close", (code) => {
      clearTimeout(timer);
      finish(code);
    });
  });
}

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
          "User-Agent": "skill-self-check",
          Accept: "*/*",
        },
      },
      (res) => {
        const chunks = [];
        res.on("data", (c) => chunks.push(c));
        res.on("end", () => {
          resolve({
            statusCode: res.statusCode || 0,
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
    await new Promise((r) => setTimeout(r, 250));
  }
  throw lastError || new Error("Timeout");
}

function tempFilePath(prefix, suffix) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  return path.join(dir, suffix);
}

function tempDirPath(prefix) {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

function parseArgs(argv) {
  const args = {
    m0: false,
    m1: false,
    m1Scale: 2000,
    m2: false,
    m2Scale: 100000,
    strictRemote: false,
    skipRemote: false,
    withCapture: false,
    remoteUrl: process.env.SKILL_REMOTE_INDEX_URL || null,
  };

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--m0") args.m0 = true;
    else if (a === "--m1") args.m1 = true;
    else if (a === "--m2") args.m2 = true;
    else if (a === "--m1-scale") {
      const v = argv[i + 1];
      if (!v) throw new Error("--m1-scale requires a value");
      args.m1Scale = Number(v);
      i++;
    } else if (a === "--m2-scale") {
      const v = argv[i + 1];
      if (!v) throw new Error("--m2-scale requires a value");
      args.m2Scale = Number(v);
      i++;
    }
    else if (a === "--strict-remote") args.strictRemote = true;
    else if (a === "--skip-remote") args.skipRemote = true;
    else if (a === "--with-capture") args.withCapture = true;
    else if (a === "--remote-url") {
      const v = argv[i + 1];
      if (!v) throw new Error("--remote-url requires a value");
      args.remoteUrl = v;
      i++;
    }
  }

  return args;
}

function parseGitHubOwnerRepo(remoteUrl) {
  const v = String(remoteUrl || "").trim();
  if (!v) return null;

  // https://github.com/OWNER/REPO(.git)
  let m = v.match(/^https?:\/\/[^/]*github\.com\/([^/]+)\/([^/]+?)(?:\.git)?\/?$/i);
  if (m) return { owner: m[1], repo: m[2] };

  // git@github.com:OWNER/REPO(.git)
  m = v.match(/^git@[^:]*github\.com:([^/]+)\/([^/]+?)(?:\.git)?$/i);
  if (m) return { owner: m[1], repo: m[2] };

  return null;
}

function defaultRemoteIndexUrl(repoRoot) {
  if (process.env.SKILL_REMOTE_INDEX_URL) return String(process.env.SKILL_REMOTE_INDEX_URL).trim();

  const r = run("git", ["remote", "get-url", "origin"], { cwd: repoRoot });
  if (r.status !== 0) return null;
  const parsed = parseGitHubOwnerRepo(r.stdout.trim());
  if (!parsed) return null;
  const ownerHost = parsed.owner.toLowerCase();
  return `https://${ownerHost}.github.io/${parsed.repo}/index.json`;
}

function mustExist(filePath, label) {
  assertOk(fs.existsSync(filePath), `Missing ${label || filePath}`);
}

function countLevelsFromIndex(indexPath) {
  const raw = fs.readFileSync(indexPath, "utf8");
  const parsed = JSON.parse(raw);
  const skills = Array.isArray(parsed.skills) ? parsed.skills : [];
  const counts = { total: skills.length, bronze: 0, silver: 0, gold: 0 };
  for (const s of skills) {
    const level = String((s && s.level) || "").trim().toLowerCase();
    if (level === "gold") counts.gold++;
    else if (level === "silver") counts.silver++;
    else counts.bronze++;
  }
  return { counts, skills_count: Number(parsed.skills_count) || 0 };
}

async function main() {
  const repoRoot = path.resolve(__dirname, "..");
  const args = parseArgs(process.argv.slice(2));
  if (args.m2) args.m1 = true;
  if (args.m1) args.m0 = true;
  // M1 is designed to be fully runnable offline; skip remote checks unless explicitly requested.
  if (args.m1 && !args.strictRemote) args.skipRemote = true;
  args.remoteUrl = args.remoteUrl || defaultRemoteIndexUrl(repoRoot) || "https://labrai.github.io/LangSkills/index.json";

  const results = [];
  const record = (name, ok, details, warn = false) => results.push({ name, ok, details, warn });

  try {
    // M0: repo skeleton checks (files/workflows present)
    if (args.m0) {
      const required = [
        "README.md",
        "LICENSE",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "SECURITY.md",
        "SAFETY.md",
        "docs",
        "docs/assets/demo.gif",
        "skills",
        "agents",
        "scripts",
        "website/src/index.html",
        "cli/skill.js",
        "plugin/chrome/manifest.json",
        ".github/workflows/ci.yml",
        ".github/workflows/lint.yml",
        ".github/workflows/link-check.yml",
        ".github/workflows/build-site.yml",
        ".github/workflows/agent-generate.yml",
        ".github/workflows/audit-capture.yml",
      ];
      if (args.m1) {
        required.push(
          "eval/harness/run.js",
          "eval/tasks/linux/smoke.json",
          "eval/reports/.gitkeep",
          "scripts/lifecycle.js",
          "scripts/pr-score.js",
          "scripts/synth-skills.js",
          ".github/workflows/pr-score.yml",
          ".github/workflows/eval.yml",
          ".github/workflows/lifecycle.yml",
        );
      }
      for (const rel of required) mustExist(path.join(repoRoot, rel), rel);
      record("m0(repo-skeleton)", true, `${required.length} paths OK`);
    }

	    // 0) Agent generator smoke (config -> skills skeleton -> validate -> build index)
	    {
	      const skillsOut = tempDirPath("skill-gen-");
	      const siteOut = tempDirPath("skill-site-");

      const gen = run(process.execPath, [path.join(repoRoot, "agents", "run_local.js"), "--domain", "linux", "--out", skillsOut], {
        cwd: repoRoot,
      });
      assertOk(gen.status === 0, gen.stderr || gen.stdout || "agent generator failed");

      const val = run(process.execPath, [path.join(repoRoot, "scripts", "validate-skills.js"), "--skills-root", skillsOut], {
        cwd: repoRoot,
      });
      assertOk(val.status === 0, val.stderr || val.stdout || "validate generated skills failed");

      const build = run(
        process.execPath,
        [path.join(repoRoot, "scripts", "build-site.js"), "--skills-root", skillsOut, "--out", siteOut],
        { cwd: repoRoot },
      );
      assertOk(build.status === 0, build.stderr || build.stdout || "build site from generated skills failed");

      const indexPath = path.join(siteOut, "index.json");
      const index = JSON.parse(fs.readFileSync(indexPath, "utf8"));
      assertOk(Number(index.skills_count) > 0, "generated index.json skills_count <= 0");

	      record("agent(generator)", true, `skills_count=${index.skills_count}`);
	    }

	    // 0a) Agent overwrite-content safety (refresh markdown without clobbering metadata.yaml)
	    {
	      const skillsOut = tempDirPath("skill-overwrite-content-");
	      const runLocal = path.join(repoRoot, "agents", "run_local.js");
	      const topicId = "filesystem/find-files";

	      const gen = run(
	        process.execPath,
	        [runLocal, "--domain", "linux", "--topic", topicId, "--out", skillsOut],
	        { cwd: repoRoot },
	      );
	      assertOk(gen.status === 0, gen.stderr || gen.stdout || "agent overwrite-content setup failed");

	      const skillDir = path.join(skillsOut, "linux", "filesystem", "find-files");
	      const metaPath = path.join(skillDir, "metadata.yaml");
	      const skillPath = path.join(skillDir, "skill.md");
	      mustExist(metaPath, "metadata.yaml");
	      mustExist(skillPath, "skill.md");

	      const metaBefore = fs.readFileSync(metaPath, "utf8");
	      const metaSentinelLine = 'last_verified: "2099-01-01"';
	      const metaSentinel = /^\s*last_verified:\s*.*$/m.test(metaBefore)
	        ? metaBefore.replace(/^\s*last_verified:\s*.*$/m, metaSentinelLine)
	        : `${metaBefore.trimEnd()}\n${metaSentinelLine}\n`;
	      fs.writeFileSync(metaPath, metaSentinel, "utf8");
	      fs.writeFileSync(skillPath, "# SENTINEL\n", "utf8");

	      const refresh = run(
	        process.execPath,
	        [runLocal, "--domain", "linux", "--topic", topicId, "--out", skillsOut, "--overwrite-content"],
	        { cwd: repoRoot },
	      );
	      assertOk(refresh.status === 0, refresh.stderr || refresh.stdout || "agent overwrite-content refresh failed");

	      const metaAfter = fs.readFileSync(metaPath, "utf8");
	      assertOk(metaAfter.includes(metaSentinelLine), "metadata.yaml was overwritten by --overwrite-content");

	      const skillAfter = fs.readFileSync(skillPath, "utf8");
	      assertOk(!skillAfter.includes("SENTINEL"), "skill.md was not overwritten by --overwrite-content");

	      record("agent(overwrite-content)", true, "metadata preserved");
	    }

	    // 0b) Agent capture smoke (prefer real fetch; fall back to offline fixtures if network is unavailable)
	    if (args.withCapture) {
	      const skillsOut = tempDirPath("skill-capture-");
	      const siteOut = tempDirPath("skill-capture-site-");
	      const fixtureCache = path.join(repoRoot, "docs", "fixtures", "web-cache");
	      const tempCache = tempDirPath("skill-cache-");
	      let cacheOut = tempCache;
	      let cacheMode = "network";

	      const runCapture = (cacheDir) =>
	        run(
	          process.execPath,
	          [
	            path.join(repoRoot, "agents", "run_local.js"),
	            "--domain",
	            "linux",
	            "--topic",
	            "filesystem/find-files",
	            "--out",
	            skillsOut,
	            "--overwrite",
	            "--capture",
	            "--capture-strict",
	            "--llm-provider",
	            "mock",
	            "--llm-fixture",
	            path.join("agents", "llm", "fixtures", "rewrite.json"),
	            "--cache-dir",
	            cacheDir,
	          ],
	          { cwd: repoRoot },
	        );

	      let gen = runCapture(cacheOut);
	      if (gen.status !== 0) {
	        const msg = String(gen.stderr || gen.stdout || "");
	        const looksNetwork =
	          /fetch failed|ENOTFOUND|ECONNRESET|ETIMEDOUT|EAI_AGAIN|ECONNREFUSED|certificate/i.test(msg);
	        if (looksNetwork && fs.existsSync(fixtureCache)) {
	          cacheOut = fixtureCache;
	          cacheMode = "fixture";
	          gen = runCapture(cacheOut);
	        }
	      }
	      assertOk(gen.status === 0, gen.stderr || gen.stdout || "agent capture failed");

	      const val = run(
	        process.execPath,
	        [
	          path.join(repoRoot, "scripts", "validate-skills.js"),
	          "--skills-root",
	          skillsOut,
	          "--strict",
	          "--fail-on-license-review-all",
	        ],
	        { cwd: repoRoot },
	      );
	      assertOk(val.status === 0, val.stderr || val.stdout || "validate captured skill failed");

      const audit = run(
        process.execPath,
        [
          path.join(repoRoot, "scripts", "validate-skills.js"),
          "--skills-root",
          skillsOut,
          "--strict",
          "--require-no-verbatim-copy",
          "--cache-dir",
          cacheOut,
        ],
        { cwd: repoRoot },
      );
      assertOk(audit.status === 0, audit.stderr || audit.stdout || "verbatim copy audit failed");

      const build = run(process.execPath, [path.join(repoRoot, "scripts", "build-site.js"), "--skills-root", skillsOut, "--out", siteOut], {
        cwd: repoRoot,
      });
      assertOk(build.status === 0, build.stderr || build.stdout || "build site from captured skill failed");

      const indexPath = path.join(siteOut, "index.json");
      const index = JSON.parse(fs.readFileSync(indexPath, "utf8"));
      assertOk(Number(index.skills_count) === 1, `captured index.json skills_count != 1 (got ${index.skills_count})`);

	      record("agent(capture)", true, `skills_count=${index.skills_count} cache=${cacheMode}`);
	    }

    // 1) Validate skills
    {
      const r = run(
        process.execPath,
        [path.join(repoRoot, "scripts", "validate-skills.js"), "--strict", "--fail-on-license-review"],
        {
        cwd: repoRoot,
        },
      );
      assertOk(r.status === 0, r.stderr || r.stdout || "validate-skills failed");
      record("validate-skills", true, r.stdout.trim());
    }

    // 2) Build site
    {
      const r = run(process.execPath, [path.join(repoRoot, "scripts", "build-site.js"), "--out", "website/dist"], {
        cwd: repoRoot,
      });
      assertOk(r.status === 0, r.stderr || r.stdout || "build-site failed");
      record("build-site", true, r.stdout.trim());
    }

    // 2b) M0: skills count/levels thresholds
    if (args.m0) {
      const indexPath = path.join(repoRoot, "website", "dist", "index.json");
      mustExist(indexPath, "website/dist/index.json");
      const { counts, skills_count } = countLevelsFromIndex(indexPath);
      assertOk(skills_count === counts.total, `index.json skills_count mismatch: ${skills_count} != ${counts.total}`);
      assertOk(counts.total >= 50, `M0 requires skills>=50 (got ${counts.total})`);
      assertOk(counts.silver + counts.gold >= 20, `M0 requires silver+gold>=20 (got ${counts.silver + counts.gold})`);
      record("m0(skills)", true, `total=${counts.total} (bronze=${counts.bronze}, silver=${counts.silver}, gold=${counts.gold})`);
    }

    // 2c) M2: site index is compact and content files exist
    if (args.m2) {
      const indexPath = path.join(repoRoot, "website", "dist", "index.json");
      mustExist(indexPath, "website/dist/index.json");
      const parsed = JSON.parse(fs.readFileSync(indexPath, "utf8"));
      assertOk(Number(parsed.schema_version || 0) >= 2, `site index schema_version < 2 (got ${parsed.schema_version})`);
      const skills = Array.isArray(parsed.skills) ? parsed.skills : [];
      const minScale = Math.floor(Number(args.m2Scale || 100000));
      assertOk(Number.isFinite(minScale) && minScale >= 1, `--m2-scale must be >= 1 (got ${args.m2Scale})`);
      assertOk(Number(parsed.skills_count || 0) >= minScale, `M2 requires skills_count >= ${minScale} (got ${parsed.skills_count})`);
      const counts = parsed && parsed.counts && typeof parsed.counts === "object" ? parsed.counts : null;
      assertOk(counts, "M2 requires index.json counts (atomic/parameterized/composite/by_level)");
      assertOk(Number(counts.parameterized || 0) >= minScale, `M2 requires parameterized >= ${minScale} (got ${counts.parameterized})`);
      const paramProbe = skills.find((s) => s && s.id === "linux/m2-param/p-000001");
      assertOk(paramProbe, "M2 requires parameterized probe skill linux/m2-param/p-000001 in index.json");
      const probe = skills.find((s) => s && s.id === "linux/filesystem/find-files") || skills[0];
      assertOk(probe && probe.id, "site index is missing skills[] entries");
      assertOk(!("library_md" in probe) && !("skill_md" in probe) && !("sources_md" in probe), "site index should not embed markdown");

      const base = path.join(repoRoot, "website", "dist", "skills", ...String(probe.id).split("/"));
      mustExist(path.join(base, "library.md"), `website/dist/skills/${probe.id}/library.md`);
      mustExist(path.join(base, "skill.md"), `website/dist/skills/${probe.id}/skill.md`);
      mustExist(path.join(base, "reference", "sources.md"), `website/dist/skills/${probe.id}/reference/sources.md`);
      record("m2(site-index)", true, `schema_version=${parsed.schema_version} probe=${probe.id}`);
      record(
        "m2(real-scale)",
        true,
        `total=${parsed.skills_count} parameterized=${counts.parameterized} (min=${minScale})`,
      );
    }

    // 3) Serve site locally and fetch
    {
      const port = 4173 + Math.floor(Math.random() * 500);
      const proc = childProcess.spawn(
        process.execPath,
        [path.join(repoRoot, "scripts", "serve-site.js"), "--dir", "website/dist", "--port", String(port), "--host", "127.0.0.1"],
        { cwd: repoRoot, stdio: ["ignore", "pipe", "pipe"] },
      );

      try {
        const indexUrl = `http://127.0.0.1:${port}/index.json`;
        const rootUrl = `http://127.0.0.1:${port}/`;
        const indexResp = await waitForHttp(indexUrl, 15000);
        assertOk(indexResp.statusCode === 200, `local index.json HTTP ${indexResp.statusCode}`);

        const parsed = JSON.parse(indexResp.body);
        assertOk(Number(parsed.skills_count) > 0, "local index.json skills_count <= 0");

        if (args.m2) {
          const skills = Array.isArray(parsed.skills) ? parsed.skills : [];
          const probe = skills.find((s) => s && s.id === "linux/filesystem/find-files") || skills[0];
          assertOk(probe && probe.id, "local index.json missing skills[] entries");
          const libUrl = `http://127.0.0.1:${port}/skills/${encodeURI(String(probe.id))}/library.md`;
          const libResp = await request(libUrl, 15000);
          assertOk(libResp.statusCode === 200, `local library.md HTTP ${libResp.statusCode}`);
          assertOk(libResp.body.includes("# Library"), "local library.md missing '# Library' header");
        }

        const rootResp = await request(rootUrl, 15000);
        assertOk(rootResp.statusCode === 200, `local / HTTP ${rootResp.statusCode}`);
        assertOk(rootResp.body.includes("<title>Skill Repo</title>"), "local / missing title");

        record("serve-site(local)", true, `${indexUrl} (skills_count=${parsed.skills_count})`);

        // CLI online smoke (HTTP index.json + content fetch)
        {
          const r1 = run(process.execPath, [path.join(repoRoot, "cli", "skill.js"), "search", "find", "--base-url", rootUrl], { cwd: repoRoot });
          assertOk(r1.status === 0, "cli(online) search failed");
          assertOk(r1.stdout.includes("linux/filesystem/find-files"), "cli(online) search missing expected id");

          const r2 = run(
            process.execPath,
            [
              path.join(repoRoot, "cli", "skill.js"),
              "show",
              "linux/filesystem/find-files",
              "--file",
              "library",
              "--base-url",
              rootUrl,
            ],
            { cwd: repoRoot },
          );
          assertOk(r2.status === 0, "cli(online) show failed");
          assertOk(r2.stdout.includes("# Library"), "cli(online) show library missing header");

          record("cli(online)", true, "search/show OK");

          if (args.m2) {
            const r3 = run(
              process.execPath,
              [path.join(repoRoot, "cli", "skill.js"), "show", "linux/m2-param/p-000001", "--file", "library", "--base-url", rootUrl],
              { cwd: repoRoot },
            );
            assertOk(r3.status === 0, "cli(online,m2) show parameterized failed");
            assertOk(r3.stdout.includes("linux/m2-param/p-000001"), "cli(online,m2) did not render {{id}} placeholder");
            assertOk(!r3.stdout.includes("{{id}}"), "cli(online,m2) still contains '{{id}}' placeholder");
            record("cli(online,m2)", true, "parameterized template render OK");
          }
        }
      } finally {
        proc.kill();
      }
    }

    // 4) CLI smoke
    {
      const r1 = run(process.execPath, [path.join(repoRoot, "cli", "skill.js"), "search", "find"], { cwd: repoRoot });
      assertOk(r1.status === 0, "cli search failed");
      assertOk(r1.stdout.includes("linux/filesystem/find-files"), "cli search missing expected id");

      const r2 = run(process.execPath, [path.join(repoRoot, "cli", "skill.js"), "show", "linux/filesystem/find-files", "--file", "library"], {
        cwd: repoRoot,
      });
      assertOk(r2.status === 0, "cli show failed");
      assertOk(r2.stdout.includes("# Library"), "cli show library missing header");

      record("cli", true, "search/show OK");

      if (args.m2) {
        const r3 = run(
          process.execPath,
          [path.join(repoRoot, "cli", "skill.js"), "show", "linux/m2-param/p-000001", "--file", "library"],
          { cwd: repoRoot },
        );
        assertOk(r3.status === 0, "cli(m2) show parameterized failed");
        assertOk(r3.stdout.includes("linux/m2-param/p-000001"), "cli(m2) did not render {{id}} placeholder");
        assertOk(!r3.stdout.includes("{{id}}"), "cli(m2) still contains '{{id}}' placeholder");
        record("cli(m2)", true, "parameterized template render OK");
      }
    }

    // 5) topics_table generator (write file to avoid PowerShell encoding issues)
    {
      const outFile = tempFilePath("skill-topics-", "topics_table.md");
      const r = run(process.execPath, [path.join(repoRoot, "scripts", "render-topics-table.js"), "--domain", "linux", "--with-header", "--out", outFile], {
        cwd: repoRoot,
      });
      assertOk(r.status === 0, "render-topics-table failed");

      const content = fs.readFileSync(outFile, "utf8");
      assertOk(content.includes("| ID | Title | Risk | Level | Action | Notes |"), "topics table header missing");
      assertOk(content.includes("linux/filesystem/find-files"), "topics table missing expected id");

      record("render-topics-table", true, `wrote ${outFile}`);
    }

    // 5b) runner smoke (persistent state + resume)
    {
      const runsOut = tempDirPath("skill-runs-");
      const skillsOut = tempDirPath("skill-runner-skills-");
      const runId = "self-check-runner";
      const runner = path.join(repoRoot, "agents", "runner", "run.js");
      const statePath = path.join(runsOut, runId, "state.json");

      const r1 = run(process.execPath, [runner, "--domain", "linux", "--out", skillsOut, "--runs-dir", runsOut, "--run-id", runId, "--max-topics", "1"], {
        cwd: repoRoot,
      });
      assertOk(r1.status === 0, r1.stderr || r1.stdout || "runner first pass failed");
      assertOk(fs.existsSync(statePath), "runner missing state.json");

      const s1 = JSON.parse(fs.readFileSync(statePath, "utf8"));
      assertOk(Number(s1.cursor) >= 1, "runner cursor did not advance");

      const r2 = run(process.execPath, [runner, "--domain", "linux", "--out", skillsOut, "--runs-dir", runsOut, "--run-id", runId, "--max-topics", "1"], {
        cwd: repoRoot,
      });
      assertOk(r2.status === 0, r2.stderr || r2.stdout || "runner resume failed");

      const s2 = JSON.parse(fs.readFileSync(statePath, "utf8"));
      assertOk(Number(s2.cursor) >= Number(s1.cursor), "runner cursor did not progress after resume");

      record("runner", true, `state=${statePath}`);
    }

    // 5c) crawler smoke (local seed + source_policy enforcement)
    {
      const server = http.createServer((req, res) => {
        const url = String(req.url || "");
        res.setHeader("Content-Type", "text/html; charset=utf-8");
        if (url === "/seed") {
          res.end(
            [
              "<!doctype html><html><body>",
              '<a href="/a">A</a>',
              '<a href="/b">B</a>',
              '<a href="https://example.com/outside">outside</a>',
              "</body></html>",
            ].join(""),
          );
          return;
        }
        if (url === "/a") {
          res.end('<!doctype html><html><body><a href="/b">B</a></body></html>');
          return;
        }
        if (url === "/b") {
          res.end("<!doctype html><html><body>ok</body></html>");
          return;
        }
        res.statusCode = 404;
        res.end("<!doctype html><html><body>404</body></html>");
      });

      await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
      const port = server.address().port;
      const seedUrl = `http://127.0.0.1:${port}/seed`;

      try {
        const runsOut = tempDirPath("skill-crawl-runs-");
        const cacheOut = tempDirPath("skill-crawl-cache-");
        const runId = "self-check-crawl";
        const crawler = path.join(repoRoot, "agents", "crawler", "run.js");
        const statePath = path.join(runsOut, runId, "crawl_state.json");

        const proc = childProcess.spawn(
          process.execPath,
          [
            crawler,
            "--domain",
            "linux",
            "--runs-dir",
            runsOut,
            "--run-id",
            runId,
            "--cache-dir",
            cacheOut,
            "--timeout-ms",
            "5000",
            "--max-pages",
            "20",
            "--max-depth",
            "2",
            "--seeds",
            seedUrl,
            "--allow-domain",
            "127.0.0.1",
          ],
          { cwd: repoRoot, stdio: ["ignore", "pipe", "pipe"] },
        );
        const stdout = [];
        const stderr = [];
        proc.stdout.on("data", (c) => stdout.push(c));
        proc.stderr.on("data", (c) => stderr.push(c));
        const exitCode = await new Promise((resolve) => proc.on("close", (code) => resolve(code)));
        assertOk(exitCode === 0, Buffer.concat(stderr).toString("utf8") || Buffer.concat(stdout).toString("utf8") || "crawler failed");
        assertOk(fs.existsSync(statePath), "crawler missing crawl_state.json");

        const state = JSON.parse(fs.readFileSync(statePath, "utf8"));
        assertOk(Number(state.stats && state.stats.fetched ? state.stats.fetched : 0) >= 3, "crawler fetched < 3 pages");
        assertOk(Number(state.stats && state.stats.blocked ? state.stats.blocked : 0) >= 1, "crawler did not block external URL");

        record("crawler", true, `state=${statePath}`);
      } finally {
        server.close();
      }
    }

	    // 6) plugin static checks
	    {
	      const manifestPath = path.join(repoRoot, "plugin", "chrome", "manifest.json");
	      const raw = fs.readFileSync(manifestPath, "utf8");
	      const json = JSON.parse(raw);
      const hp = Array.isArray(json.host_permissions) ? json.host_permissions : [];
      assertOk(hp.includes("http://127.0.0.1/*"), "plugin missing localhost host_permissions");
      assertOk(hp.includes("https://*.github.io/*"), "plugin missing GitHub Pages host_permissions");
	      record("plugin(manifest)", true, "host_permissions OK");
	    }

	    // 7) git automation (dry-run + branch creation/push in a temp repo)
	    {
	      const tmpRepo = tempDirPath("skill-git-repo-");
	      const tmpRemote = tempDirPath("skill-git-remote-");

	      const initRemote = run("git", ["init", "--bare"], { cwd: tmpRemote });
	      assertOk(initRemote.status === 0, initRemote.stderr || initRemote.stdout || "git init --bare failed");

	      const initRepo = run("git", ["init"], { cwd: tmpRepo });
	      assertOk(initRepo.status === 0, initRepo.stderr || initRepo.stdout || "git init failed");

	      const cfg1 = run("git", ["config", "user.name", "skill-self-check"], { cwd: tmpRepo });
	      assertOk(cfg1.status === 0, "git config user.name failed");
	      const cfg2 = run("git", ["config", "user.email", "skill-self-check@local"], { cwd: tmpRepo });
	      assertOk(cfg2.status === 0, "git config user.email failed");

	      fs.writeFileSync(path.join(tmpRepo, "README.md"), "temp repo\n", "utf8");
	      const addInit = run("git", ["add", "README.md"], { cwd: tmpRepo });
	      assertOk(addInit.status === 0, "git add README.md failed");
	      const commitInit = run("git", ["commit", "-m", "chore: init"], { cwd: tmpRepo });
	      assertOk(commitInit.status === 0, commitInit.stderr || commitInit.stdout || "git commit init failed");

	      const renameMain = run("git", ["branch", "-M", "main"], { cwd: tmpRepo });
	      assertOk(renameMain.status === 0, "git branch -M main failed");

	      const addRemote = run("git", ["remote", "add", "origin", tmpRemote], { cwd: tmpRepo });
	      assertOk(addRemote.status === 0, "git remote add origin failed");
	      const pushMain = run("git", ["push", "-u", "origin", "main"], { cwd: tmpRepo });
	      assertOk(pushMain.status === 0, pushMain.stderr || pushMain.stdout || "git push main failed");

	      fs.writeFileSync(path.join(tmpRepo, "change.txt"), "change\n", "utf8");

	      const scriptPath = path.join(repoRoot, "scripts", "git-automation.js");
	      const branch = "bot/self-check";

	      const dry = run(process.execPath, [
	        scriptPath,
	        "--repo",
	        tmpRepo,
	        "--paths",
	        "change.txt",
	        "--remote",
	        "origin",
	        "--branch",
	        branch,
	        "--message",
	        "chore: self-check update",
	      ]);
	      assertOk(dry.status === 0, dry.stderr || dry.stdout || "git-automation dry-run failed");
	      assertOk(dry.stdout.includes(`[git-automation] branch: ${branch}`), "git-automation missing branch in output");
	      assertOk(dry.stdout.includes("[git-automation] mode: dry-run"), "git-automation did not report dry-run mode");
	      assertOk(dry.stdout.includes("change.txt"), "git-automation dry-run missing change.txt");

	      const exec = run(process.execPath, [
	        scriptPath,
	        "--repo",
	        tmpRepo,
	        "--paths",
	        "change.txt",
	        "--remote",
	        "origin",
	        "--branch",
	        branch,
	        "--message",
	        "chore: self-check update",
	        "--execute",
	      ]);
	      assertOk(exec.status === 0, exec.stderr || exec.stdout || "git-automation execute failed");

	      const remoteHeads = run("git", ["ls-remote", "--heads", "origin", branch], { cwd: tmpRepo });
	      assertOk(remoteHeads.status === 0, "git ls-remote failed");
	      assertOk(remoteHeads.stdout.includes(`refs/heads/${branch}`), "remote is missing expected branch");

	      record("git-automation", true, "dry-run + branch push OK");
	    }

	    // 7b) create-pr smoke (mock GitHub API)
	    {
	      const pulls = [];
	      let nextNumber = 1;

	      const server = http.createServer((req, res) => {
	        const method = String(req.method || "GET").toUpperCase();
	        const host = String(req.headers.host || "");
	        const url = new URL(String(req.url || "/"), `http://${host}`);
	        const pathName = url.pathname || "/";

	        const sendJson = (statusCode, obj) => {
	          res.statusCode = statusCode;
	          res.setHeader("Content-Type", "application/json; charset=utf-8");
	          res.end(JSON.stringify(obj));
	        };

	        const matchPulls = pathName.match(/^\/repos\/([^/]+)\/([^/]+)\/pulls$/);
	        if (matchPulls) {
	          if (method === "GET") {
	            const head = String(url.searchParams.get("head") || "");
	            const base = String(url.searchParams.get("base") || "");
	            const list = pulls.filter((p) => p.state === "open" && p.base === base && p.head === head);
	            sendJson(200, list);
	            return;
	          }

	          if (method === "POST") {
	            const chunks = [];
	            req.on("data", (c) => chunks.push(c));
	            req.on("end", () => {
	              let body = {};
	              try {
	                body = JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
	              } catch {
	                body = {};
	              }
	              const number = nextNumber++;
	              const pr = {
	                number,
	                html_url: `http://local/pr/${number}`,
	                state: "open",
	                base: String(body.base || "main"),
	                head: String(body.head || ""),
	                title: String(body.title || ""),
	              };
	              pulls.push(pr);
	              sendJson(201, pr);
	            });
	            return;
	          }
	        }

	        const matchLabels = pathName.match(/^\/repos\/([^/]+)\/([^/]+)\/issues\/(\d+)\/labels$/);
	        if (matchLabels && method === "POST") {
	          sendJson(200, { ok: true });
	          return;
	        }

	        sendJson(404, { message: "Not Found" });
	      });

	      await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
	      const port = server.address().port;
	      const apiBase = `http://127.0.0.1:${port}`;

	      try {
	        const scriptPath = path.join(repoRoot, "scripts", "create-pr.js");
	        const env = { ...process.env, GITHUB_TOKEN: "dummy", GITHUB_API_BASE_URL: apiBase };

	        const r1 = await runAsync(
	          process.execPath,
	          [
	            scriptPath,
	            "--api-base-url",
	            apiBase,
	            "--repo",
	            "owner/repo",
	            "--head",
	            "bot/test",
	            "--base",
	            "main",
	            "--title",
	            "chore: create-pr smoke",
	            "--body",
	            "test",
	            "--label",
	            "bot",
	          ],
	          { cwd: repoRoot, env, timeoutMs: 15000 },
	        );
	        assertOk(r1.status === 0, r1.stderr || r1.stdout || "create-pr first call failed");
	        assertOk(r1.stdout.includes("[create-pr] created:"), "create-pr did not create PR");

	        const r2 = await runAsync(
	          process.execPath,
	          [
	            scriptPath,
	            "--api-base-url",
	            apiBase,
	            "--repo",
	            "owner/repo",
	            "--head",
	            "bot/test",
	            "--base",
	            "main",
	            "--title",
	            "chore: create-pr smoke",
	            "--body",
	            "test",
	            "--label",
	            "bot",
	          ],
	          { cwd: repoRoot, env, timeoutMs: 15000 },
	        );
	        assertOk(r2.status === 0, r2.stderr || r2.stdout || "create-pr second call failed");
	        assertOk(r2.stdout.includes("[create-pr] exists:"), "create-pr did not detect existing PR");

	        record("create-pr(mock)", true, apiBase);
	      } finally {
	        server.close();
	      }
	    }

	    // 8) remote Pages (optional, may fail if repo is private or Pages not enabled)
	    {
	      if (args.skipRemote) {
	        const reason = args.m1 && !args.strictRemote ? "skipped (--m1 offline default)" : "skipped (--skip-remote)";
	        record("pages(remote)", true, reason);
	      } else {
        const remote = args.remoteUrl;
        const canReachRemoteGit = () => {
          const r = run("git", ["ls-remote", "--heads", "origin", "main"], { cwd: repoRoot });
          if (r.status !== 0) return false;
          return r.stdout.includes("refs/heads/main");
        };
        try {
          const r = await request(remote, 15000);
          if (r.statusCode === 200) {
            const parsed = JSON.parse(r.body);
            record("pages(remote)", true, `${remote} (skills_count=${parsed.skills_count ?? "?"})`);
          } else {
            // For private repos, GitHub Pages may be disabled/unavailable but the git remote can still be reachable.
            // Treat this as OK when git remote is reachable (so local users can still run the repo end-to-end).
            const hint = `HTTP ${r.statusCode} (${remote})`;
            if (canReachRemoteGit()) {
              record("pages(remote)", true, `${hint}; origin reachable via git (repo may be private or Pages not enabled)`);
            } else if (args.strictRemote) {
              record("pages(remote)", true, `${hint}; origin not reachable via git (cannot verify remote)`, true);
            } else {
              record("pages(remote)", true, `${hint}; origin not reachable via git`, true);
            }
          }
        } catch (e) {
          const msg = String(e && e.message ? e.message : e);
          if (canReachRemoteGit()) {
            record("pages(remote)", true, `${msg}; origin reachable via git (repo may be private or Pages not enabled)`);
          } else if (args.strictRemote) {
            record("pages(remote)", true, `${msg}; origin not reachable via git (cannot verify remote)`, true);
          } else {
            record("pages(remote)", true, msg, true);
          }
        }
      }
    }

    // 9) M1: eval + lifecycle + governance + scale (offline)
    if (args.m1) {
      const evalOut = tempFilePath("eval-report-", "report.json");
      const evalMd = tempFilePath("eval-report-", "report.md");
      const evalRun = run(
        process.execPath,
        [
          path.join(repoRoot, "eval", "harness", "run.js"),
          "--skills-root",
          "skills",
          "--tasks",
          path.join("eval", "tasks", "linux", "smoke.json"),
          "--max-tasks",
          "50",
          "--out",
          evalOut,
          "--out-md",
          evalMd,
          "--fail-on-stale-gold",
        ],
        { cwd: repoRoot },
      );
      assertOk(evalRun.status === 0, evalRun.stderr || evalRun.stdout || "eval harness failed");
      const evalReport = JSON.parse(fs.readFileSync(evalOut, "utf8"));
      assertOk(evalReport && evalReport.metrics && evalReport.metrics.skills, "eval report missing metrics");
      record("m1(eval)", true, `out=${evalOut} (skills=${evalReport.metrics.skills.total})`);

      const lifeOut = tempFilePath("lifecycle-report-", "report.json");
      const lifeRun = run(
        process.execPath,
        [path.join(repoRoot, "scripts", "lifecycle.js"), "--out", lifeOut, "--fail-on-stale-gold"],
        { cwd: repoRoot },
      );
      assertOk(lifeRun.status === 0, lifeRun.stderr || lifeRun.stdout || "lifecycle report failed");
      const lifeReport = JSON.parse(fs.readFileSync(lifeOut, "utf8"));
      assertOk(lifeReport && lifeReport.summary, "lifecycle report missing summary");
      record("m1(lifecycle)", true, `stale_gold=${lifeReport.summary.stale_gold}`);

      const scoreOut = tempFilePath("pr-score-", "score.json");
      const scoreRun = run(
        process.execPath,
        [
          path.join(repoRoot, "scripts", "pr-score.js"),
          "--paths",
          "skills/linux/filesystem/find-files/skill.md",
          "--out-json",
          scoreOut,
        ],
        { cwd: repoRoot },
      );
      assertOk(scoreRun.status === 0, scoreRun.stderr || scoreRun.stdout || "pr-score failed");
      const score = JSON.parse(fs.readFileSync(scoreOut, "utf8"));
      assertOk(score && Array.isArray(score.labels) && score.labels.includes("bot:pass"), "pr-score did not pass");
      record("m1(pr-score)", true, `score=${score.score}`);

      const scale = Math.floor(Number(args.m1Scale));
      assertOk(Number.isFinite(scale) && scale >= 1, `--m1-scale must be >= 1 (got ${args.m1Scale})`);
      const gold = Math.min(50, scale);
      const silver = Math.min(200, Math.max(0, scale - gold));

      const synthRoot = tempDirPath("skill-synth-");
      const synthSkillsRoot = path.join(synthRoot, "skills");
      const synthMake = run(
        process.execPath,
        [
          path.join(repoRoot, "scripts", "synth-skills.js"),
          "--out",
          synthSkillsRoot,
          "--count",
          String(scale),
          "--silver",
          String(silver),
          "--gold",
          String(gold),
          "--overwrite",
        ],
        { cwd: repoRoot },
      );
      assertOk(synthMake.status === 0, synthMake.stderr || synthMake.stdout || "synth-skills failed");

      const synthVal = run(
        process.execPath,
        [path.join(repoRoot, "scripts", "validate-skills.js"), "--skills-root", synthSkillsRoot, "--strict"],
        { cwd: repoRoot },
      );
      assertOk(synthVal.status === 0, synthVal.stderr || synthVal.stdout || "validate synthetic skills failed");

      const synthSite = tempDirPath("skill-synth-site-");
      const synthBuild = run(
        process.execPath,
        [path.join(repoRoot, "scripts", "build-site.js"), "--skills-root", synthSkillsRoot, "--out", synthSite],
        { cwd: repoRoot },
      );
      assertOk(synthBuild.status === 0, synthBuild.stderr || synthBuild.stdout || "build site from synthetic skills failed");

      const synthIndexPath = path.join(synthSite, "index.json");
      const synthIndex = JSON.parse(fs.readFileSync(synthIndexPath, "utf8"));
      assertOk(Number(synthIndex.skills_count) === scale, `synthetic index skills_count mismatch: ${synthIndex.skills_count}`);
      record("m1(scale)", true, `skills_count=${synthIndex.skills_count}`);
    }

    // 10) M2: 100k-scale site index generation (metadata only)
    if (args.m2) {
      const scale = Math.floor(Number(args.m2Scale));
      assertOk(Number.isFinite(scale) && scale >= 1, `--m2-scale must be >= 1 (got ${args.m2Scale})`);

      const siteOut = tempDirPath("skill-site-m2-");
      const build = run(
        process.execPath,
        [
          path.join(repoRoot, "scripts", "build-site.js"),
          "--out",
          siteOut,
          "--synthetic-count",
          String(scale),
          "--no-copy-skills",
        ],
        { cwd: repoRoot },
      );
      assertOk(build.status === 0, build.stderr || build.stdout || "build site (synthetic) failed");

      const indexPath = path.join(siteOut, "index.json");
      const st = fs.statSync(indexPath);
      const parsed = JSON.parse(fs.readFileSync(indexPath, "utf8"));
      assertOk(Number(parsed.schema_version || 0) >= 2, `synthetic index schema_version < 2 (got ${parsed.schema_version})`);
      assertOk(Number(parsed.skills_count) === scale, `synthetic index skills_count mismatch: ${parsed.skills_count} != ${scale}`);
      assertOk(Array.isArray(parsed.skills) && parsed.skills.length === scale, `synthetic index skills length mismatch: ${parsed.skills.length} != ${scale}`);
      const first = parsed.skills[0] || {};
      assertOk(!("library_md" in first) && !("skill_md" in first) && !("sources_md" in first), "synthetic index should not embed markdown");
      record("m2(scale-index)", true, `skills_count=${scale} bytes=${st.size}`);
    }

    // Print summary
    const failed = results.filter((r) => !r.ok);
    const warned = results.filter((r) => r.warn);
    for (const r of results) {
      const tag = r.ok ? (r.warn ? "WARN" : "OK  ") : "FAIL";
      console.log(`${tag} ${r.name}${r.details ? ` - ${r.details}` : ""}`);
    }

    if (failed.length > 0) {
      console.error("\nSome checks failed.");
      console.error("If pages(remote) failed: make repo Public, then Settings -> Pages -> Source = GitHub Actions, then rerun workflow build-site.");
      process.exit(2);
    }

    if (warned.length > 0) {
      console.error("\nSome checks warned.");
      console.error("If pages(remote) warned: make repo Public, then Settings -> Pages -> Source = GitHub Actions, then rerun workflow build-site.");
    }
  } catch (e) {
    console.error(String(e && e.stack ? e.stack : e));
    process.exit(1);
  }
}

main();
