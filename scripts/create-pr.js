#!/usr/bin/env node
/* eslint-disable no-console */

const fs = require("fs");

function assertOk(condition, message) {
  if (!condition) throw new Error(message);
}

function parseArgs(argv) {
  const out = {
    repo: null, // owner/name
    head: null, // branch name or owner:branch
    base: "main",
    title: "chore: automated update",
    body: null,
    bodyFile: null,
    labels: [],
    draft: false,
  };

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--repo") {
      out.repo = argv[i + 1] || null;
      i++;
    } else if (a === "--head") {
      out.head = argv[i + 1] || null;
      i++;
    } else if (a === "--base") {
      out.base = argv[i + 1] || out.base;
      i++;
    } else if (a === "--title") {
      out.title = argv[i + 1] || out.title;
      i++;
    } else if (a === "--body") {
      out.body = argv[i + 1] || "";
      i++;
    } else if (a === "--body-file") {
      out.bodyFile = argv[i + 1] || null;
      i++;
    } else if (a === "--label") {
      const v = argv[i + 1] || "";
      i++;
      const list = v
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean);
      out.labels.push(...list);
    } else if (a === "--draft") {
      out.draft = true;
    } else if (a === "-h" || a === "--help") {
      console.log(
        [
          "Usage:",
          "  node scripts/create-pr.js --repo <owner/name> --head <branch> [--base main]",
          "                            [--title <title>] [--body <text> | --body-file <path>]",
          "                            [--label <a,b,c>] [--draft]",
          "",
          "Auth:",
          "  - Set GITHUB_TOKEN (recommended) or GH_TOKEN in env.",
          "",
          "Notes:",
          "  - Idempotent: if an open PR already exists for the same head+base, prints it and exits 0.",
        ].join("\n"),
      );
      process.exit(0);
    } else {
      throw new Error(`Unknown arg: ${a}`);
    }
  }

  assertOk(out.repo, "--repo is required");
  assertOk(out.head, "--head is required");
  return out;
}

function parseRepo(full) {
  const v = String(full || "").trim();
  const m = v.match(/^([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+)$/);
  assertOk(m, `Invalid --repo '${v}' (expected owner/name)`);
  return { owner: m[1], repo: m[2] };
}

function tokenFromEnv() {
  const t = String(process.env.GITHUB_TOKEN || process.env.GH_TOKEN || "").trim();
  assertOk(t, "Missing token: set GITHUB_TOKEN (or GH_TOKEN)");
  return t;
}

async function ghJson({ method, url, token, body }) {
  const resp = await fetch(url, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(body ? { "Content-Type": "application/json" } : {}),
      "User-Agent": "skill-bot",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await resp.text();
  const parsed = text ? (() => { try { return JSON.parse(text); } catch { return null; } })() : null;
  if (!resp.ok) {
    const msg = parsed && parsed.message ? parsed.message : text || `HTTP ${resp.status}`;
    const details = parsed && parsed.errors ? `\nerrors: ${JSON.stringify(parsed.errors)}` : "";
    throw new Error(`GitHub API ${resp.status} ${resp.statusText}: ${msg}${details}`);
  }
  return parsed;
}

async function findExistingPr({ owner, repo, headFull, base, token }) {
  const url =
    `https://api.github.com/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/pulls` +
    `?state=open&base=${encodeURIComponent(base)}&head=${encodeURIComponent(headFull)}`;
  const list = await ghJson({ method: "GET", url, token });
  if (!Array.isArray(list) || list.length === 0) return null;
  return list[0];
}

async function addLabels({ owner, repo, issueNumber, labels, token }) {
  const list = Array.isArray(labels) ? labels.map((x) => String(x || "").trim()).filter(Boolean) : [];
  if (list.length === 0) return;
  const url = `https://api.github.com/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/issues/${encodeURIComponent(
    String(issueNumber),
  )}/labels`;
  await ghJson({ method: "POST", url, token, body: { labels: list } });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const { owner, repo } = parseRepo(args.repo);
  const token = tokenFromEnv();

  let body = args.body;
  if (args.bodyFile) body = fs.readFileSync(args.bodyFile, "utf8");
  if (body == null) body = "";

  const headFull = args.head.includes(":") ? args.head : `${owner}:${args.head}`;

  const existing = await findExistingPr({ owner, repo, headFull, base: args.base, token });
  if (existing) {
    console.log(`[create-pr] exists: ${existing.html_url}`);
    return;
  }

  const createUrl = `https://api.github.com/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/pulls`;
  const pr = await ghJson({
    method: "POST",
    url: createUrl,
    token,
    body: {
      title: args.title,
      head: headFull,
      base: args.base,
      body,
      draft: Boolean(args.draft),
    },
  });

  if (pr && pr.number) {
    await addLabels({ owner, repo, issueNumber: pr.number, labels: args.labels, token });
  }

  console.log(`[create-pr] created: ${pr && pr.html_url ? pr.html_url : "(unknown url)"}`);
}

main().catch((e) => {
  console.error(String(e && e.stack ? e.stack : e));
  process.exit(1);
});

