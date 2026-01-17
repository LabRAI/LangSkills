/* eslint-disable no-console */

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

function unquoteEnvValue(value) {
  let v = String(value || "").trim();
  if (!v) return "";
  if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
    v = v.slice(1, -1);
  }
  return v;
}

function loadDotEnv(filePath) {
  const full = path.resolve(process.cwd(), filePath);
  let text = "";
  try {
    text = fs.readFileSync(full, "utf8");
  } catch {
    return;
  }

  for (const rawLine of String(text || "").replace(/\r\n/g, "\n").split("\n")) {
    const line = String(rawLine || "").trim();
    if (!line) continue;
    if (line.startsWith("#")) continue;

    const m = line.match(/^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/);
    if (!m) continue;
    const key = m[1];
    const value = unquoteEnvValue(m[2]);
    if (!key) continue;
    if (Object.prototype.hasOwnProperty.call(process.env, key)) continue;
    process.env[key] = value;
  }
}

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

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function writeJsonAtomic(filePath, obj) {
  ensureDir(path.dirname(filePath));
  const tmp = `${filePath}.${crypto.randomBytes(4).toString("hex")}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 2) + "\n", "utf8");
  fs.renameSync(tmp, filePath);
}

function utcNowIso() {
  return new Date().toISOString();
}

function sha256Hex(text) {
  return crypto.createHash("sha256").update(String(text || ""), "utf8").digest("hex");
}

function normalizeBaseUrl(url) {
  const v = String(url || "").trim();
  if (!v) return "";
  return v.replace(/\/+$/, "");
}

function ensureOpenAIV1BaseUrl(url) {
  const u = normalizeBaseUrl(url);
  if (!u) return "";
  return u.endsWith("/v1") ? u : `${u}/v1`;
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

// Best-effort load `.env` from repo root (without requiring any external dependency).
loadDotEnv(path.resolve(__dirname, "..", "..", ".env"));

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
      async completeRaw() {
        const mode = fixture && fixture.json && fixture.json.mode;
        if (mode === "identity") return { content: "", usage: null, raw: { mode: "identity" } };
        const response = fixture && fixture.json && fixture.json.response;
        if (typeof response !== "string") {
          throw new Error("mock fixture must include {\"mode\":\"identity\"} or {\"response\":\"...\"}");
        }
        return { content: response, usage: null, raw: { mode: "fixture", fixture_path: fixture ? fixture.path : null } };
      },
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
      async completeRaw({ messages }) {
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
        const promptTokens = Number.isFinite(Number(json.prompt_eval_count)) ? Number(json.prompt_eval_count) : null;
        const completionTokens = Number.isFinite(Number(json.eval_count)) ? Number(json.eval_count) : null;
        const usage =
          promptTokens != null || completionTokens != null
            ? {
              prompt_tokens: promptTokens || 0,
              completion_tokens: completionTokens || 0,
              total_tokens: (promptTokens || 0) + (completionTokens || 0),
            }
            : null;
        return { content, usage, raw: json };
      },
      async complete({ messages }) {
        const r = await this.completeRaw({ messages });
        return r.content;
      },
    };
  }

  if (p === "openai") {
    const m = String(model || process.env.OPENAI_MODEL || "").trim();
    if (!m) throw new Error("Missing --llm-model (or OPENAI_MODEL) for provider=openai");
    const key = String(apiKey || process.env.OPENAI_API_KEY || "").trim();
    if (!key) throw new Error("Missing --llm-api-key (or OPENAI_API_KEY) for provider=openai");
    const u = ensureOpenAIV1BaseUrl(baseUrl || process.env.OPENAI_BASE_URL) || "https://api.openai.com/v1";
    return {
      provider: "openai",
      model: m,
      baseUrl: u,
      timeoutMs,
      async completeRaw({ messages }) {
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
        const usageRaw = json && json.usage && typeof json.usage === "object" ? json.usage : null;
        const usage =
          usageRaw && (usageRaw.total_tokens != null || usageRaw.prompt_tokens != null || usageRaw.completion_tokens != null)
            ? {
              prompt_tokens: Number(usageRaw.prompt_tokens || 0),
              completion_tokens: Number(usageRaw.completion_tokens || 0),
              total_tokens: Number(usageRaw.total_tokens || 0),
            }
            : null;
        return { content, usage, raw: json };
      },
      async complete({ messages }) {
        const r = await this.completeRaw({ messages });
        return r.content;
      },
    };
  }

  throw new Error(`Unknown --llm-provider: ${p}`);
}

async function rewriteMarkdown({ markdown, llm, kind, capture } = {}) {
  if (!llm) return markdown;

  const capturePath = capture && typeof capture === "object" && capture.path ? String(capture.path) : "";
  const captureMeta = capture && typeof capture === "object" && capture.meta && typeof capture.meta === "object" ? capture.meta : null;
  const captureEnabled = !!capturePath;

  if (llm.provider === "mock") {
    const mode = llm.fixture && llm.fixture.json && llm.fixture.json.mode;
    if (mode === "identity") {
      if (captureEnabled) {
        writeJsonAtomic(capturePath, {
          version: 1,
          ts: utcNowIso(),
          op: "rewrite_markdown",
          kind,
          meta: captureMeta,
          llm: { provider: llm.provider, model: llm.model, base_url: llm.baseUrl || "" },
          usage: null,
          request: { messages: [] },
          response: { content: null },
          input_sha256: sha256Hex(markdown),
          output_sha256: sha256Hex(markdown),
          note: "mock identity mode (no rewrite)",
        });
      }
      return markdown;
    }

    const startedAt = utcNowIso();
    try {
      const raw = typeof llm.completeRaw === "function" ? await llm.completeRaw({ messages: [] }) : null;
      const out = raw ? raw.content : await llm.complete({ messages: [] });
      const outText = String(out || "");
      const outTrim = outText.trim();
      const finalText = outTrim ? outText : markdown;

      if (captureEnabled) {
        writeJsonAtomic(capturePath, {
          version: 1,
          ts: utcNowIso(),
          started_at: startedAt,
          finished_at: utcNowIso(),
          op: "rewrite_markdown",
          kind,
          meta: captureMeta,
          llm: { provider: llm.provider, model: llm.model, base_url: llm.baseUrl || "" },
          usage: raw && raw.usage ? raw.usage : null,
          request: { messages: [] },
          response: { content: outText },
          input_sha256: sha256Hex(markdown),
          output_sha256: sha256Hex(finalText),
          used_llm_output: !!outTrim,
        });
      }

      return outTrim ? `${outTrim}\n` : markdown;
    } catch (e) {
      if (captureEnabled) {
        writeJsonAtomic(capturePath, {
          version: 1,
          ts: utcNowIso(),
          started_at: startedAt,
          finished_at: utcNowIso(),
          op: "rewrite_markdown",
          kind,
          meta: captureMeta,
          llm: { provider: llm.provider, model: llm.model, base_url: llm.baseUrl || "" },
          usage: null,
          request: { messages: [] },
          error: String(e && e.message ? e.message : e),
          input_sha256: sha256Hex(markdown),
        });
      }
      throw e;
    }
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
  const messages = [
    { role: "system", content: system },
    { role: "user", content: user },
  ];

  const startedAt = utcNowIso();
  try {
    const raw = typeof llm.completeRaw === "function" ? await llm.completeRaw({ messages }) : null;
    const content = raw ? raw.content : await llm.complete({ messages });

    const out = String(content || "").trim();
    const finalText = out ? `${out}\n` : markdown;

    if (captureEnabled) {
      writeJsonAtomic(capturePath, {
        version: 1,
        ts: utcNowIso(),
        started_at: startedAt,
        finished_at: utcNowIso(),
        op: "rewrite_markdown",
        kind,
        meta: captureMeta,
        llm: { provider: llm.provider, model: llm.model, base_url: llm.baseUrl || "" },
        usage: raw && raw.usage ? raw.usage : null,
        request: { messages },
        response: { content: out },
        input_sha256: sha256Hex(markdown),
        output_sha256: sha256Hex(finalText),
        used_llm_output: !!out,
      });
    }

    return finalText;
  } catch (e) {
    if (captureEnabled) {
      writeJsonAtomic(capturePath, {
        version: 1,
        ts: utcNowIso(),
        started_at: startedAt,
        finished_at: utcNowIso(),
        op: "rewrite_markdown",
        kind,
        meta: captureMeta,
        llm: { provider: llm.provider, model: llm.model, base_url: llm.baseUrl || "" },
        usage: null,
        request: { messages },
        error: String(e && e.message ? e.message : e),
        input_sha256: sha256Hex(markdown),
      });
    }
    throw e;
  }
}

module.exports = { createLLM, rewriteMarkdown };

