#!/usr/bin/env node
/* eslint-disable no-console */

const childProcess = require("child_process");
const path = require("path");

function run(cmd, args, options = {}) {
  const env = { ...process.env, GIT_TERMINAL_PROMPT: "0" };
  const p = childProcess.spawnSync(cmd, args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    env,
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

function sleepMs(ms) {
  const v = Number(ms || 0);
  if (!Number.isFinite(v) || v <= 0) return;
  const arr = new Int32Array(new SharedArrayBuffer(4));
  Atomics.wait(arr, 0, 0, v);
}

function redactRemoteUrl(url) {
  const u = String(url || "").trim();
  const m = u.match(/^(https?:\/\/)([^@]+)@(.+)$/);
  if (m) return `${m[1]}<redacted>@${m[3]}`;
  return u;
}

function utcStampForBranch() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const y = d.getUTCFullYear();
  const m = pad(d.getUTCMonth() + 1);
  const day = pad(d.getUTCDate());
  const hh = pad(d.getUTCHours());
  const mm = pad(d.getUTCMinutes());
  const ss = pad(d.getUTCSeconds());
  return `${y}${m}${day}-${hh}${mm}${ss}`;
}

function parseArgs(argv) {
  const out = {
    repo: process.cwd(),
    remote: "origin",
    base: null,
    branch: null,
    message: "chore: automated update",
    paths: [],
    dryRun: true,
    restoreBranch: true,
    retries: 1,
    retryDelayMs: 1200,
  };

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--repo") {
      const v = argv[i + 1];
      if (!v) throw new Error("--repo requires a value");
      out.repo = v;
      i++;
    } else if (a === "--remote") {
      const v = argv[i + 1];
      if (!v) throw new Error("--remote requires a value");
      out.remote = v;
      i++;
    } else if (a === "--base") {
      const v = argv[i + 1];
      if (!v) throw new Error("--base requires a value");
      out.base = v;
      i++;
    } else if (a === "--branch") {
      const v = argv[i + 1];
      if (!v) throw new Error("--branch requires a value");
      out.branch = v;
      i++;
    } else if (a === "--message") {
      const v = argv[i + 1];
      if (!v) throw new Error("--message requires a value");
      out.message = v;
      i++;
    } else if (a === "--paths" || a === "--path") {
      const v = argv[i + 1];
      if (!v) throw new Error(`${a} requires a value`);
      v.split(",")
        .map((x) => x.trim())
        .filter(Boolean)
        .forEach((x) => out.paths.push(x));
      i++;
    } else if (a === "--execute") {
      out.dryRun = false;
    } else if (a === "--dry-run") {
      out.dryRun = true;
    } else if (a === "--no-restore-branch") {
      out.restoreBranch = false;
    } else if (a === "--restore-branch") {
      out.restoreBranch = true;
    } else if (a === "--retries") {
      const v = argv[i + 1];
      if (!v) throw new Error("--retries requires a value");
      out.retries = Number(v);
      i++;
    } else if (a === "--retry-delay-ms") {
      const v = argv[i + 1];
      if (!v) throw new Error("--retry-delay-ms requires a value");
      out.retryDelayMs = Number(v);
      i++;
    } else if (a === "-h" || a === "--help") {
      console.log(
        [
          "Usage:",
          "  node scripts/git-automation.js [--repo <path>] [--remote origin] [--paths <path[,path...]>] [--branch <name>] [--message <msg>]",
          "                              [--base <ref>] [--execute] [--no-restore-branch] [--retries <n>] [--retry-delay-ms <ms>]",
          "",
          "Defaults:",
          "  - dry-run is ON by default (no checkout/commit/push).",
          "  - paths default to: skills",
        ].join("\n"),
      );
      process.exit(0);
    } else {
      throw new Error(`Unknown arg: ${a}`);
    }
  }

  if (!Array.isArray(out.paths) || out.paths.length === 0) out.paths = ["skills"];
  if (!Number.isFinite(out.retries) || out.retries < 0) out.retries = 0;
  if (!Number.isFinite(out.retryDelayMs) || out.retryDelayMs < 0) out.retryDelayMs = 0;
  return out;
}

function git(repoRoot, args) {
  return run("git", args, { cwd: repoRoot });
}

function repoRootFrom(repo) {
  const r = run("git", ["rev-parse", "--show-toplevel"], { cwd: repo });
  assertOk(r.status === 0, r.stderr || r.stdout || "Not a git repo (git rev-parse failed)");
  return r.stdout.trim();
}

function getHeadSha(repoRoot) {
  const r = git(repoRoot, ["rev-parse", "HEAD"]);
  assertOk(r.status === 0, r.stderr || r.stdout || "Failed to get HEAD sha");
  return r.stdout.trim();
}

function getCurrentBranch(repoRoot) {
  const r = git(repoRoot, ["branch", "--show-current"]);
  assertOk(r.status === 0, r.stderr || r.stdout || "Failed to get current branch");
  const name = r.stdout.trim();
  return name || null;
}

function getRemoteUrl(repoRoot, remote) {
  const r = git(repoRoot, ["remote", "get-url", remote]);
  if (r.status === 0) return r.stdout.trim();

  const list = git(repoRoot, ["remote", "-v"]);
  const hint = list.status === 0 ? `\nKnown remotes:\n${list.stdout.trim()}` : "";
  throw new Error(`Remote not found: ${remote}${hint}`);
}

function ensureValidBranchName(repoRoot, branch) {
  const r = git(repoRoot, ["check-ref-format", "--branch", branch]);
  assertOk(r.status === 0, `Invalid branch name: ${branch}`);
}

function localBranchExists(repoRoot, branch) {
  const r = git(repoRoot, ["show-ref", "--verify", "--quiet", `refs/heads/${branch}`]);
  return r.status === 0;
}

function pushWithRetries(repoRoot, remote, branch, retries, delayMs) {
  const maxAttempts = 1 + Math.max(0, Number(retries || 0));
  let last = null;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const r = git(repoRoot, ["push", "-u", remote, branch]);
    if (r.status === 0) return;
    last = r;
    const suffix = attempt >= maxAttempts ? "" : ` (retry in ${delayMs}ms)`;
    console.error(
      `git push failed (attempt ${attempt}/${maxAttempts})${suffix}:\n${String(r.stderr || r.stdout || "").trim()}`,
    );
    if (attempt < maxAttempts) sleepMs(delayMs);
  }
  throw new Error(String(last && (last.stderr || last.stdout) ? last.stderr || last.stdout : "git push failed").trim());
}

function plannedFiles(repoRoot, paths) {
  const r = git(repoRoot, ["status", "--porcelain", "--", ...paths]);
  assertOk(r.status === 0, r.stderr || r.stdout || "git status failed");
  return r.stdout
    .replace(/\r\n/g, "\n")
    .split("\n")
    .map((l) => l.trimEnd())
    .filter(Boolean);
}

function stagedFiles(repoRoot) {
  const r = git(repoRoot, ["diff", "--cached", "--name-only"]);
  assertOk(r.status === 0, r.stderr || r.stdout || "git diff --cached failed");
  return r.stdout
    .replace(/\r\n/g, "\n")
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const repo = path.resolve(args.repo);
  const repoRoot = repoRootFrom(repo);

  const remoteUrl = redactRemoteUrl(getRemoteUrl(repoRoot, args.remote));
  const startSha = getHeadSha(repoRoot);
  const startBranch = getCurrentBranch(repoRoot);
  const startRef = startBranch || startSha;

  const branch = String(args.branch || `bot/auto/${utcStampForBranch()}`).trim();
  assertOk(branch, "Missing branch name");
  ensureValidBranchName(repoRoot, branch);

  const baseRef = args.base ? String(args.base).trim() : startRef;
  assertOk(baseRef, "Missing base ref");

  console.log(`[git-automation] repo: ${repoRoot}`);
  console.log(`[git-automation] remote: ${args.remote} (${remoteUrl})`);
  console.log(`[git-automation] start: ${startBranch ? startBranch : `detached@${startSha.slice(0, 12)}`}`);
  console.log(`[git-automation] base: ${baseRef}`);
  console.log(`[git-automation] branch: ${branch}`);
  console.log(`[git-automation] paths: ${args.paths.join(", ")}`);
  console.log(`[git-automation] mode: ${args.dryRun ? "dry-run" : "execute"}`);

  const planned = plannedFiles(repoRoot, args.paths);
  if (planned.length === 0) console.log("[git-automation] changes: (none under paths)");
  else {
    console.log("[git-automation] changes:");
    planned.forEach((l) => console.log(`  ${l}`));
  }

  if (args.dryRun) return;
  if (planned.length === 0) {
    console.log("[git-automation] execute: skipped (no changes)");
    return;
  }

  let switched = false;
  try {
    if (localBranchExists(repoRoot, branch)) {
      const r = git(repoRoot, ["checkout", branch]);
      assertOk(r.status === 0, r.stderr || r.stdout || `git checkout ${branch} failed`);
      switched = true;
    } else {
      const r = git(repoRoot, ["checkout", "-b", branch, baseRef]);
      assertOk(r.status === 0, r.stderr || r.stdout || `git checkout -b ${branch} ${baseRef} failed`);
      switched = true;
    }

    const add = git(repoRoot, ["add", "--", ...args.paths]);
    assertOk(add.status === 0, add.stderr || add.stdout || "git add failed");

    const staged = stagedFiles(repoRoot);
    if (staged.length === 0) {
      console.log("[git-automation] commit: skipped (no staged changes)");
      console.log("[git-automation] push: skipped (no staged changes)");
      return;
    } else {
      console.log(`[git-automation] commit: ${args.message}`);
      const c = git(repoRoot, ["commit", "-m", args.message]);
      assertOk(c.status === 0, c.stderr || c.stdout || "git commit failed");
    }

    pushWithRetries(repoRoot, args.remote, branch, args.retries, args.retryDelayMs);
    console.log(`[git-automation] push: OK (${args.remote}/${branch})`);
  } finally {
    if (args.restoreBranch && switched) {
      const r = git(repoRoot, ["checkout", startRef]);
      if (r.status !== 0) {
        console.error(
          `[git-automation] WARN: failed to restore ${startRef}:\n${String(r.stderr || r.stdout || "").trim()}`,
        );
      }
    }
  }
}

main();

