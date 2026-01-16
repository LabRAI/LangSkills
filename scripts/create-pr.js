#!/usr/bin/env node
/* eslint-disable no-console */

const fs = require("fs");
const http = require("http");
const https = require("https");

function assertOk(condition, message) {
  if (!condition) throw new Error(message);
}

function parseArgs(argv) {
  const out = {
    apiBaseUrl: process.env.GITHUB_API_BASE_URL || "https://api.github.com",
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
    if (a === "--api-base-url") {
      out.apiBaseUrl = argv[i + 1] || out.apiBaseUrl;
      i++;
    } else if (a === "--repo") {
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

function normalizeApiBaseUrl(raw) {
  const v = String(raw || "").trim().replace(/\/+$/, "");
  assertOk(v, "Missing --api-base-url");
  assertOk(/^https?:\/\//i.test(v), `Invalid --api-base-url '${v}' (expected http/https)`);
  return v;
}

async function ghJson({ method, url, token, body, timeoutMs = 20000 }) {
  const payload = body ? JSON.stringify(body) : null;
  const u = new URL(url);
  const lib = u.protocol === "https:" ? https : http;

  const headers = {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "skill-bot",
    Connection: "close",
  };
  if (payload != null) {
    headers["Content-Type"] = "application/json";
    headers["Content-Length"] = String(Buffer.byteLength(payload));
  }

  return await new Promise((resolve, reject) => {
    const req = lib.request(
      {
        protocol: u.protocol,
        hostname: u.hostname,
        port: u.port || undefined,
        path: `${u.pathname}${u.search}`,
        method,
        headers,
        agent: false,
      },
      (res) => {
        const chunks = [];
        res.on("data", (c) => chunks.push(c));
        res.on("end", () => {
          const text = Buffer.concat(chunks).toString("utf8");
          let parsed = null;
          if (text) {
            try {
              parsed = JSON.parse(text);
            } catch {
              parsed = null;
            }
          }

          const code = res.statusCode || 0;
          if (code < 200 || code >= 300) {
            const msg = parsed && parsed.message ? parsed.message : text || `HTTP ${code}`;
            const details = parsed && parsed.errors ? `\nerrors: ${JSON.stringify(parsed.errors)}` : "";
            reject(new Error(`GitHub API ${code} ${res.statusMessage || ""}: ${msg}${details}`.trim()));
            return;
          }
          resolve(parsed);
        });
      },
    );

    req.on("error", reject);
    req.setTimeout(timeoutMs, () => req.destroy(new Error(`Timeout after ${timeoutMs}ms`)));
    if (payload != null) req.write(payload);
    req.end();
  });
}

async function findExistingPr({ owner, repo, headFull, base, token, apiUrl }) {
  const buildUrl =
    typeof apiUrl === "function"
      ? apiUrl
      : (p) => `https://api.github.com${String(p || "").startsWith("/") ? "" : "/"}${String(p || "")}`;
  const url =
    buildUrl(`/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/pulls`) +
    `?state=open&base=${encodeURIComponent(base)}&head=${encodeURIComponent(headFull)}`;
  const list = await ghJson({ method: "GET", url, token });
  if (!Array.isArray(list) || list.length === 0) return null;
  return list[0];
}

async function addLabels({ owner, repo, issueNumber, labels, token, apiUrl }) {
  const list = Array.isArray(labels) ? labels.map((x) => String(x || "").trim()).filter(Boolean) : [];
  if (list.length === 0) return;
  const buildUrl =
    typeof apiUrl === "function"
      ? apiUrl
      : (p) => `https://api.github.com${String(p || "").startsWith("/") ? "" : "/"}${String(p || "")}`;
  const url = buildUrl(
    `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/issues/${encodeURIComponent(String(issueNumber))}/labels`,
  );
  await ghJson({ method: "POST", url, token, body: { labels: list } });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const { owner, repo } = parseRepo(args.repo);
  const token = tokenFromEnv();
  const apiBaseUrl = normalizeApiBaseUrl(args.apiBaseUrl);
  const apiUrl = (p) => `${apiBaseUrl}${String(p || "").startsWith("/") ? "" : "/"}${String(p || "")}`;

  let body = args.body;
  if (args.bodyFile) body = fs.readFileSync(args.bodyFile, "utf8");
  if (body == null) body = "";

  const headFull = args.head.includes(":") ? args.head : `${owner}:${args.head}`;

  const existing = await findExistingPr({
    owner,
    repo,
    headFull,
    base: args.base,
    token,
    apiUrl,
  });
  if (existing) {
    console.log(`[create-pr] exists: ${existing.html_url}`);
    return;
  }

  const createUrl = apiUrl(`/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/pulls`);
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
    await addLabels({
      owner,
      repo,
      issueNumber: pr.number,
      labels: args.labels,
      token,
      apiUrl,
    });
  }

  console.log(`[create-pr] created: ${pr && pr.html_url ? pr.html_url : "(unknown url)"}`);
}

main()
  .then(() => process.exit(0))
  .catch((e) => {
    console.error(String(e && e.stack ? e.stack : e));
    process.exit(1);
  });

