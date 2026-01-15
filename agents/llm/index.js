/* eslint-disable no-console */

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

function readText(filePath) {
  return fs.readFileSync(filePath, "utf8");
}

function normalizeBaseUrl(url) {
  const v = String(url || "").trim();
  if (!v) return "";
  return v.replace(/\/+$/, "");
}

async function fetchJson(url, { method = "POST", headers = {}, body = null } = {}, timeoutMs = 60000) {
  if (typeof fetch !== "function") throw new Error("Global fetch() not available. Use Node.js 18+.");

  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const resp = await fetch(url, {
      method,
      headers: { Accept: "application/json", ...headers },
      body,
      signal: controller.signal,
    });
    const text = await resp.text();
    if (!resp.ok) throw new Error(`HTTP ${resp.status} for ${url}: ${text.slice(0, 2000)}`);
    return JSON.parse(text);
  } finally {
    clearTimeout(t);
  }
}

function loadFixture(fixturePath) {
  if (!fixturePath) return null;
  const full = path.resolve(process.cwd(), fixturePath);
  if (!exists(full)) throw new Error(`Missing --llm-fixture: ${full}`);
  const json = JSON.parse(readText(full));
  return { path: full, json };
}

function createLLM({
  provider,
  model,
  baseUrl,
  apiKey,
  fixturePath,
  timeoutMs = 60000,
} = {}) {
  const p = String(provider || "").trim();
  if (!p) return null;

  if (p === "mock") {
    const fixture = loadFixture(fixturePath);
    return {
      provider: "mock",
      model: "mock",
      baseUrl: "",
      timeoutMs,
      fixture,
      async complete() {
        const mode = fixture && fixture.json && fixture.json.mode;
        if (mode === "identity") return "";
        const response = fixture && fixture.json && fixture.json.response;
        if (typeof response !== "string") {
          throw new Error("mock fixture must include {\"mode\":\"identity\"} or {\"response\":\"...\"}");
        }
        return response;
      },
    };
  }

  if (p === "ollama") {
    const m = String(model || "").trim();
    if (!m) throw new Error("Missing --llm-model for provider=ollama");
    const u = normalizeBaseUrl(baseUrl) || "http://127.0.0.1:11434";
    return {
      provider: "ollama",
      model: m,
      baseUrl: u,
      timeoutMs,
      async complete({ messages }) {
        const url = `${u}/api/chat`;
        const json = await fetchJson(
          url,
          {
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ model: m, messages, stream: false }),
          },
          timeoutMs,
        );
        const content = json && json.message && typeof json.message.content === "string" ? json.message.content : "";
        if (!content) throw new Error("ollama response missing message.content");
        return content;
      },
    };
  }

  if (p === "openai") {
    const m = String(model || "").trim();
    if (!m) throw new Error("Missing --llm-model for provider=openai");
    const key = String(apiKey || process.env.OPENAI_API_KEY || "").trim();
    if (!key) throw new Error("Missing --llm-api-key (or OPENAI_API_KEY) for provider=openai");
    const u = normalizeBaseUrl(baseUrl) || "https://api.openai.com/v1";
    return {
      provider: "openai",
      model: m,
      baseUrl: u,
      timeoutMs,
      async complete({ messages }) {
        const url = `${u}/chat/completions`;
        const json = await fetchJson(
          url,
          {
            headers: { "Content-Type": "application/json", Authorization: `Bearer ${key}` },
            body: JSON.stringify({ model: m, messages }),
          },
          timeoutMs,
        );
        const content =
          json && json.choices && json.choices[0] && json.choices[0].message
            ? json.choices[0].message.content
            : "";
        if (!content) throw new Error("openai response missing choices[0].message.content");
        return content;
      },
    };
  }

  throw new Error(`Unknown --llm-provider: ${p}`);
}

async function rewriteMarkdown({ markdown, llm, kind }) {
  if (!llm) return markdown;

  if (llm.provider === "mock") {
    const mode = llm.fixture && llm.fixture.json && llm.fixture.json.mode;
    if (mode === "identity") return markdown;
    const out = await llm.complete({ messages: [] });
    return String(out || "").trim() ? String(out) : markdown;
  }

  const system = [
    "You are a technical editor.",
    "Task: rewrite the given markdown to be correct and more concise.",
    "Constraints:",
    "- Preserve all required section headings and their order.",
    "- Preserve all code blocks and inline code exactly (do not change commands/flags).",
    "- Preserve citations like [[1]] exactly; do not add/remove citation numbers.",
    "- Do not add TODO placeholders.",
    "- Output ONLY the rewritten markdown, no commentary.",
  ].join("\n");

  const user = `Rewrite this file (${kind}).\n\n---\n${markdown}`;
  const content = await llm.complete({
    messages: [
      { role: "system", content: system },
      { role: "user", content: user },
    ],
  });

  const out = String(content || "").trim();
  return out ? `${out}\n` : markdown;
}

module.exports = { createLLM, rewriteMarkdown };

