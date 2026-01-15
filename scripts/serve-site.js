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
  if (ext === ".svg") return "image/svg+xml";
  if (ext === ".png") return "image/png";
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg";
  return "application/octet-stream";
}

function safeJoin(rootDir, reqPath) {
  const cleaned = reqPath.replace(/\\/g, "/").replace(/\0/g, "");
  const rel = cleaned.startsWith("/") ? cleaned.slice(1) : cleaned;
  const full = path.resolve(rootDir, rel);
  if (!full.startsWith(path.resolve(rootDir))) return null;
  return full;
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

  const server = http.createServer((req, res) => {
    const url = new URL(req.url || "/", `http://${req.headers.host || "localhost"}`);
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

