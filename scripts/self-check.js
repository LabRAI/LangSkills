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
    strictRemote: false,
    skipRemote: false,
    withCapture: false,
    remoteUrl: process.env.SKILL_REMOTE_INDEX_URL || "https://shatianming5.github.io/skill_lain/index.json",
  };

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--strict-remote") args.strictRemote = true;
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

async function main() {
  const repoRoot = path.resolve(__dirname, "..");
  const args = parseArgs(process.argv.slice(2));

  const results = [];
  const record = (name, ok, details, warn = false) => results.push({ name, ok, details, warn });

  try {
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

    // 0b) Agent capture smoke (real fetch -> non-TODO skill -> strict validation)
    if (args.withCapture) {
      const skillsOut = tempDirPath("skill-capture-");
      const siteOut = tempDirPath("skill-capture-site-");
      const cacheOut = tempDirPath("skill-cache-");

      const gen = run(
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
          cacheOut,
        ],
        { cwd: repoRoot },
      );
      assertOk(gen.status === 0, gen.stderr || gen.stdout || "agent capture failed");

      const val = run(
        process.execPath,
        [
          path.join(repoRoot, "scripts", "validate-skills.js"),
          "--skills-root",
          skillsOut,
          "--strict",
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

      record("agent(capture)", true, `skills_count=${index.skills_count}`);
    }

    // 1) Validate skills
    {
      const r = run(process.execPath, [path.join(repoRoot, "scripts", "validate-skills.js"), "--strict"], {
        cwd: repoRoot,
      });
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

        const rootResp = await request(rootUrl, 15000);
        assertOk(rootResp.statusCode === 200, `local / HTTP ${rootResp.statusCode}`);
        assertOk(rootResp.body.includes("<title>Skill Repo</title>"), "local / missing title");

        record("serve-site(local)", true, `${indexUrl} (skills_count=${parsed.skills_count})`);
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
      assertOk(hp.some((x) => x.startsWith("https://shatianming5.github.io/")), "plugin missing GitHub Pages host_permissions");
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

	    // 8) remote Pages (optional, may fail if repo is private or Pages not enabled)
	    {
	      if (args.skipRemote) {
	        record("pages(remote)", true, "skipped (--skip-remote)");
	      } else {
        const remote = args.remoteUrl;
        try {
          const r = await request(remote, 15000);
          if (r.statusCode === 200) {
            const parsed = JSON.parse(r.body);
            record("pages(remote)", true, `${remote} (skills_count=${parsed.skills_count ?? "?"})`);
          } else if (args.strictRemote) {
            record("pages(remote)", false, `HTTP ${r.statusCode} (make repo Public + enable Pages)`);
          } else {
            record("pages(remote)", true, `HTTP ${r.statusCode} (make repo Public + enable Pages)`, true);
          }
        } catch (e) {
          if (args.strictRemote) {
            record("pages(remote)", false, String(e && e.message ? e.message : e));
          } else {
            record("pages(remote)", true, String(e && e.message ? e.message : e), true);
          }
        }
      }
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
