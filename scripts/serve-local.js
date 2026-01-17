#!/usr/bin/env node
/* eslint-disable no-console */

const childProcess = require("child_process");
const path = require("path");

function parseArgs(argv) {
  const out = { outDir: "website/dist", skillsRoot: null, port: 4173, host: "127.0.0.1", noBuild: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--out" || a === "--dir") {
      out.outDir = argv[i + 1] || out.outDir;
      i++;
    } else if (a === "--skills-root") {
      out.skillsRoot = argv[i + 1] || null;
      i++;
    } else if (a === "--port") {
      out.port = Number(argv[i + 1] || out.port);
      i++;
    } else if (a === "--host") {
      out.host = argv[i + 1] || out.host;
      i++;
    } else if (a === "--no-build") {
      out.noBuild = true;
    } else if (a === "-h" || a === "--help") {
      console.log(
        [
          "Usage:",
          "  node scripts/serve-local.js [--out website/dist] [--skills-root skills] [--host 127.0.0.1] [--port 4173] [--no-build]",
          "",
          "Notes:",
          "  - Default output dir is website/dist (same as build-site/serve-site).",
          "  - Use --host 0.0.0.0 to access from other devices on LAN.",
        ].join("\n"),
      );
      process.exit(0);
    }
  }
  return out;
}

function run(cmd, args, options = {}) {
  const r = childProcess.spawnSync(cmd, args, { stdio: "inherit", ...options });
  if (typeof r.status === "number") return r.status;
  return 1;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const repoRoot = path.resolve(__dirname, "..");

  if (!args.noBuild) {
    const buildArgs = [path.join(repoRoot, "scripts", "build-site.js"), "--out", args.outDir];
    if (args.skillsRoot) buildArgs.push("--skills-root", args.skillsRoot);
    const code = run(process.execPath, buildArgs, { cwd: repoRoot });
    if (code !== 0) process.exit(code);
  }

  const serveArgs = [
    path.join(repoRoot, "scripts", "serve-site.js"),
    "--dir",
    args.outDir,
    "--port",
    String(args.port),
    "--host",
    String(args.host),
  ];
  const proc = childProcess.spawn(process.execPath, serveArgs, { cwd: repoRoot, stdio: "inherit" });

  const forwardSignal = (sig) => {
    try {
      proc.kill(sig);
    } catch {
      // ignore
    }
  };
  process.on("SIGINT", () => forwardSignal("SIGINT"));
  process.on("SIGTERM", () => forwardSignal("SIGTERM"));

  proc.on("exit", (code) => {
    process.exit(typeof code === "number" ? code : 0);
  });
}

main();

