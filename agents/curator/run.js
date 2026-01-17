#!/usr/bin/env node
/* eslint-disable no-console */

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const { createLLM } = require("../llm");

process.stdout.on("error", (err) => {
  if (err && err.code === "EPIPE") process.exit(0);
});

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

function readText(filePath) {
  return fs.readFileSync(filePath, "utf8");
}

function utcNowIso() {
  return new Date().toISOString();
}

function sha256Hex(text) {
  return crypto.createHash("sha256").update(String(text || ""), "utf8").digest("hex");
}

function writeJsonAtomic(filePath, obj) {
  ensureDir(path.dirname(filePath));
  const tmp = `${filePath}.${crypto.randomBytes(4).toString("hex")}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 2) + "\n", "utf8");
  fs.renameSync(tmp, filePath);
}

function appendJsonl(filePath, obj) {
  ensureDir(path.dirname(filePath));
  fs.appendFileSync(filePath, JSON.stringify(obj) + "\n", "utf8");
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function sanitizeRunId(raw) {
  const v = String(raw || "").trim();
  if (!v) return "";
  const safe = v.replace(/[^A-Za-z0-9._-]/g, "-");
  return safe.replace(/-+/g, "-").replace(/^-+/, "").replace(/-+$/, "");
}

function makeDefaultRunId(domain) {
  const stamp = utcNowIso().replace(/[:.]/g, "").replace("T", "-").replace("Z", "");
  const rand = crypto.randomBytes(3).toString("hex");
  return sanitizeRunId(`${domain}-${stamp}-${rand}`);
}

function usage(exitCode = 0) {
  const msg = `
Usage:
  node agents/curator/run.js --domain <domain>
    [--runs-dir runs] [--run-id <id>] [--max-candidates <n>] [--reset]
    [--llm-provider mock|ollama|openai] [--llm-model <model>] [--llm-base-url <url>] [--llm-api-key <key>]
    [--llm-fixture <path>] [--llm-timeout-ms <n>] [--llm-strict]
    [--llm-prompt-system <path>] [--llm-prompt-user <path>]
    [--llm-target-actions manual|auto|ignore|all] [--llm-max-proposals <n>] [--llm-overwrite]
    [--llm-capture] [--llm-capture-path <path>]
    [--loop] [--sleep-ms <n>] [--cycle-sleep-ms <n>]

Notes:
  - Reads: runs/<run-id>/candidates.jsonl
  - Writes: runs/<run-id>/curator_state.json (resume cursor + aggregated groups)
  - Writes: runs/<run-id>/curation.json (human + machine readable summary)
  - Writes: runs/<run-id>/curation_log.jsonl (append-only per run)
`.trim();
  if (exitCode === 0) console.log(msg);
  else console.error(msg);
  process.exit(exitCode);
}

function parseArgs(argv) {
  const args = {
    domain: null,
    runsDir: "runs",
    runId: null,
    maxCandidates: 0,
    reset: false,

    llmProvider: null,
    llmModel: null,
    llmBaseUrl: null,
    llmApiKey: null,
    llmFixture: null,
    llmTimeoutMs: 60000,
    llmStrict: false,
    llmPromptSystem: "agents/curator/prompts/curate_proposals_v1.system.md",
    llmPromptUser: "agents/curator/prompts/curate_proposals_v1.user.md",
    llmTargetActions: "manual",
    llmMaxProposals: 50,
    llmOverwrite: false,
    llmCapture: false,
    llmCapturePath: null,

    loop: false,
    sleepMs: 0,
    cycleSleepMs: 0,
  };

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--domain") {
      args.domain = argv[i + 1] || null;
      i++;
    } else if (a === "--runs-dir") {
      args.runsDir = argv[i + 1] || args.runsDir;
      i++;
    } else if (a === "--run-id") {
      args.runId = argv[i + 1] || null;
      i++;
	    } else if (a === "--max-candidates") {
	      args.maxCandidates = Number(argv[i + 1] || "0");
	      i++;
	    } else if (a === "--reset") args.reset = true;
    else if (a === "--llm-provider") {
      args.llmProvider = argv[i + 1] || null;
      i++;
    } else if (a === "--llm-model") {
      args.llmModel = argv[i + 1] || null;
      i++;
    } else if (a === "--llm-base-url") {
      args.llmBaseUrl = argv[i + 1] || null;
      i++;
    } else if (a === "--llm-api-key") {
      args.llmApiKey = argv[i + 1] || null;
      i++;
    } else if (a === "--llm-fixture") {
      args.llmFixture = argv[i + 1] || null;
      i++;
    } else if (a === "--llm-timeout-ms") {
      args.llmTimeoutMs = Number(argv[i + 1] || "60000");
      i++;
    } else if (a === "--llm-strict") args.llmStrict = true;
    else if (a === "--llm-prompt-system") {
      args.llmPromptSystem = argv[i + 1] || args.llmPromptSystem;
      i++;
    } else if (a === "--llm-prompt-user") {
      args.llmPromptUser = argv[i + 1] || args.llmPromptUser;
      i++;
    } else if (a === "--llm-target-actions") {
      args.llmTargetActions = argv[i + 1] || args.llmTargetActions;
      i++;
    } else if (a === "--llm-max-proposals") {
      args.llmMaxProposals = Number(argv[i + 1] || "0");
      i++;
    } else if (a === "--llm-overwrite") args.llmOverwrite = true;
    else if (a === "--llm-capture") args.llmCapture = true;
    else if (a === "--llm-capture-path") {
      args.llmCapturePath = argv[i + 1] || null;
      i++;
    }
	    else if (a === "--loop") args.loop = true;
	    else if (a === "--sleep-ms") {
	      args.sleepMs = Number(argv[i + 1] || "0");
	      i++;
    } else if (a === "--cycle-sleep-ms") {
      args.cycleSleepMs = Number(argv[i + 1] || "0");
      i++;
    } else if (a === "-h" || a === "--help") usage(0);
    else throw new Error(`Unknown arg: ${a}`);
  }

  if (!args.domain) usage(2);
  args.runId = args.runId ? sanitizeRunId(args.runId) : makeDefaultRunId(args.domain);
  if (!args.runId) throw new Error("Invalid --run-id");

  if (!Number.isFinite(args.maxCandidates) || args.maxCandidates < 0) args.maxCandidates = 0;
  if (!Number.isFinite(args.sleepMs) || args.sleepMs < 0) args.sleepMs = 0;
  if (!Number.isFinite(args.cycleSleepMs) || args.cycleSleepMs < 0) args.cycleSleepMs = 0;
  if (!Number.isFinite(args.llmTimeoutMs) || args.llmTimeoutMs <= 0) args.llmTimeoutMs = 60000;
  if (!Number.isFinite(args.llmMaxProposals) || args.llmMaxProposals < 0) args.llmMaxProposals = 0;

  return args;
}

function normalizeTitle(text) {
  return String(text || "").replace(/\s+/g, " ").trim();
}

function slugify(text, maxLen = 64) {
  const v = String(text || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-+/, "")
    .replace(/-+$/, "");
  if (v) return v.slice(0, maxLen);
  return `t-${sha256Hex(text).slice(0, 10)}`;
}

function normalizeAction(action) {
  const a = String(action || "").trim().toLowerCase();
  if (a === "auto" || a === "manual" || a === "ignore") return a;
  return null;
}

function parseActionSet(raw) {
  const v = String(raw || "").trim().toLowerCase();
  if (!v) return new Set(["manual"]);
  if (v === "all") return new Set(["auto", "manual", "ignore"]);
  const parts = v.split(",").map((s) => s.trim()).filter(Boolean);
  const out = new Set();
  for (const p of parts) {
    const a = normalizeAction(p);
    if (!a) throw new Error(`Invalid --llm-target-actions: ${raw}`);
    out.add(a);
  }
  return out.size > 0 ? out : new Set(["manual"]);
}

function sanitizeTopicId(topic) {
  const raw = String(topic || "").trim();
  if (!raw) return "";
  const parts = raw.replace(/\\/g, "/").split("/").filter(Boolean);
  const safe = parts.map((p) => slugify(p, 48)).filter(Boolean);
  return safe.join("/").slice(0, 80);
}

function sanitizeSlugId(slug) {
  return slugify(slug, 64);
}

function parseSuggestedId(id, domain) {
  const raw = String(id || "").trim().replace(/\\/g, "/");
  if (!raw) return null;
  const parts = raw.split("/").filter(Boolean);
  if (parts.length < 2) return null;
  if (parts[0] === domain) {
    if (parts.length < 3) return null;
    const topic = parts.slice(1, -1).join("/");
    const slug = parts[parts.length - 1];
    return { topic, slug };
  }
  const topic = parts.slice(0, -1).join("/");
  const slug = parts[parts.length - 1];
  return { topic, slug };
}

function fillTemplate(template, vars) {
  let out = String(template || "");
  for (const [k, v] of Object.entries(vars || {})) {
    out = out.replaceAll(`{{${k}}}`, String(v));
  }
  return out;
}

function extractJsonFromText(text) {
  const t = String(text || "").trim();
  if (!t) return "";

  const fencedJson = t.match(/```json\\s*([\\s\\S]*?)\\s*```/i);
  if (fencedJson) return String(fencedJson[1] || "").trim();

  const fencedAny = t.match(/```\\s*([\\s\\S]*?)\\s*```/);
  if (fencedAny) return String(fencedAny[1] || "").trim();

  const first = t.indexOf("{");
  const last = t.lastIndexOf("}");
  if (first >= 0 && last > first) return t.slice(first, last + 1);
  return t;
}

function looksLikeManSectionHeading(title) {
  const t = String(title || "").trim();
  if (!t) return true;
  if (t.length <= 2) return true;
  if (/^(NAME|SYNOPSIS|DESCRIPTION|OPTIONS|OPERANDS|EXAMPLES|EXIT STATUS|RETURN VALUE|ENVIRONMENT|FILES|NOTES|BUGS|SEE ALSO|AUTHOR|AUTHORS)$/i.test(t)) {
    return true;
  }
  return false;
}

function repoShortName(repo) {
  const v = String(repo || "").trim();
  if (!v) return "repo";
  if (/^[^/]+\/[^/]+$/.test(v)) return v.replace("/", "-");
  return slugify(v, 32);
}

function inferUpstreamSkillSlugFromPath(relPath) {
  const p = String(relPath || "").replace(/\\/g, "/");
  const parts = p.split("/").filter(Boolean);
  const markers = ["skills", "scientific-skills", "skills-ref"];
  for (const marker of markers) {
    const idx = parts.indexOf(marker);
    if (idx >= 0 && idx + 1 < parts.length) {
      return String(parts[idx + 1] || "").trim();
    }
  }
  const parent = parts.length >= 2 ? parts[parts.length - 2] : "";
  return parent || "";
}

function summarizeSource(candidate) {
  const src = candidate && candidate.source && typeof candidate.source === "object" ? candidate.source : null;
  if (!src) return null;
  if (src.repo && src.path) {
    return {
      type: "repo_file",
      repo: String(src.repo),
      commit: src.commit ? String(src.commit) : null,
      path: String(src.path),
      url: src.url ? String(src.url) : null,
      sha256: src.sha256 ? String(src.sha256) : null,
    };
  }
  if (src.url) return { type: "url", url: String(src.url) };
  return { type: "unknown", raw: src };
}

function decideProposal({ domain, candidate }) {
  const kind = String(candidate && candidate.kind ? candidate.kind : "").trim() || "unknown";
  const title = normalizeTitle(candidate && candidate.title ? candidate.title : "");
  const source = summarizeSource(candidate);

  if (kind === "repo_file") {
    const relPath = source && source.type === "repo_file" ? String(source.path || "") : "";
    const isSkill = /\/SKILL\.md$/i.test(relPath);
    if (!isSkill) {
      return {
        action: "ignore",
        reason: "repo_file is not a SKILL.md",
        suggested: null,
        proposalKey: `${kind}|ignore|${relPath || title || "unknown"}`,
      };
    }

    const upstreamSlug = inferUpstreamSkillSlugFromPath(relPath);
    const topic = "tier0";
    const slug = slugify(`${repoShortName(source && source.repo ? source.repo : "")}-${upstreamSlug || title || relPath}`);
    const id = `${domain}/${topic}/${slug}`;
    return {
      action: "auto",
      reason: "upstream SKILL.md can be auto-import candidate",
      suggested: {
        id,
        domain,
        topic,
        slug,
        title: title || upstreamSlug || relPath,
      },
      proposalKey: `${kind}|${id}`,
    };
  }

  if (kind === "doc_heading") {
    if (looksLikeManSectionHeading(title)) {
      const url = source && source.type === "url" ? String(source.url || "") : "";
      return {
        action: "ignore",
        reason: "generic doc heading (not a skill topic)",
        suggested: null,
        proposalKey: `${kind}|ignore|${title}|${url}`,
      };
    }
    const topic = "web-candidates";
    const slug = slugify(title);
    const id = `${domain}/${topic}/${slug}`;
    return {
      action: "manual",
      reason: "doc heading requires human mapping to taxonomy and sources",
      suggested: { id, domain, topic, slug, title },
      proposalKey: `${kind}|${id}`,
    };
  }

  const fallbackKey = `${kind}|${title || sha256Hex(JSON.stringify(candidate)).slice(0, 12)}`;
  return {
    action: "manual",
    reason: "unknown candidate kind",
    suggested: null,
    proposalKey: fallbackKey,
  };
}

function stableProposalId(proposalKey) {
  return `prop_${sha256Hex(proposalKey).slice(0, 12)}`;
}

function addToSample(list, value, maxLen) {
  if (!value) return list;
  const v = typeof value === "string" ? value : JSON.stringify(value);
  if (!v) return list;
  if (list.includes(v)) return list;
  if (list.length >= maxLen) return list;
  list.push(v);
  return list;
}

async function readCandidatesIncremental({ candidatesPath, startByte, maxCandidates }) {
  const stream = fs.createReadStream(candidatesPath, { start: startByte, encoding: "utf8" });

  let bytesRead = 0;
  let buffer = "";
  let parsed = 0;
  let errors = 0;
  const items = [];

  const stop = () => {
    try {
      stream.destroy();
    } catch {
      // ignore
    }
  };

  for await (const chunk of stream) {
    bytesRead += Buffer.byteLength(chunk, "utf8");
    buffer += chunk;

    while (true) {
      const idx = buffer.indexOf("\n");
      if (idx < 0) break;
      const line = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 1);

      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        const obj = JSON.parse(trimmed);
        items.push(obj);
        parsed += 1;
      } catch (e) {
        errors += 1;
      }

      if (maxCandidates > 0 && parsed >= maxCandidates) {
        stop();
        break;
      }
    }

    if (maxCandidates > 0 && parsed >= maxCandidates) break;
  }

  const remainderBytes = Buffer.byteLength(buffer, "utf8");
  const effectiveBytes = bytesRead - remainderBytes;

  return {
    items,
    parsed,
    errors,
    nextCursor: startByte + effectiveBytes,
    remainder: buffer,
  };
}

function initState({ runId, domain, candidatesPath }) {
  return {
    version: 1,
    run_id: runId,
    domain,
    created_at: utcNowIso(),
    updated_at: utcNowIso(),
    candidates_path: candidatesPath,
    cursor_bytes: 0,
    stats: {
      candidates_parsed: 0,
      parse_errors: 0,
    },
    groups: {},
  };
}

function groupToOutput(group) {
  const g = group || {};
  const baseline = {
    action: g.action,
    reason: g.reason,
    suggested: g.suggested || null,
  };

  const llm = g.llm && typeof g.llm === "object" ? g.llm : null;
  const finalAction = llm && llm.action ? llm.action : baseline.action;
  const finalReason = llm && llm.reason ? llm.reason : baseline.reason;
  const finalSuggested = llm && "suggested" in llm ? llm.suggested : baseline.suggested;
  return {
    proposal_id: g.proposal_id,
    kind: g.kind,
    action: finalAction,
    reason: finalReason,
    suggested: finalSuggested,
    counts: {
      candidates: Number(g.count_candidates || 0),
      sources: Number(g.count_sources || 0),
    },
    samples: {
      candidate_ids: Array.isArray(g.sample_candidate_ids) ? g.sample_candidate_ids : [],
      sources: Array.isArray(g.sample_sources) ? g.sample_sources : [],
    },
    evidence: {
      first_seen_at: g.first_seen_at || null,
      last_seen_at: g.last_seen_at || null,
    },
    baseline,
    llm,
  };
}

async function mainOnce({ repoRoot, args }) {
  const runsRoot = path.isAbsolute(args.runsDir) ? args.runsDir : path.resolve(repoRoot, args.runsDir);
  const runDir = path.join(runsRoot, args.runId);
  ensureDir(runDir);

  const candidatesPath = path.join(runDir, "candidates.jsonl");
  if (!exists(candidatesPath)) throw new Error(`Missing candidates: ${candidatesPath}`);

  const statePath = path.join(runDir, "curator_state.json");
  const outPath = path.join(runDir, "curation.json");
  const logPath = path.join(runDir, "curation_log.jsonl");
  const llmCapturePath = args.llmCapture
    ? args.llmCapturePath
      ? path.isAbsolute(args.llmCapturePath)
        ? args.llmCapturePath
        : path.resolve(repoRoot, args.llmCapturePath)
      : path.join(runDir, "llm", "curate_proposals.json")
    : null;

  let state = null;
  if (exists(statePath) && !args.reset) {
    state = JSON.parse(readText(statePath));
    if (state.domain !== args.domain) throw new Error(`state.domain mismatch: ${state.domain} != ${args.domain}`);
    if (state.run_id !== args.runId) throw new Error(`state.run_id mismatch: ${state.run_id} != ${args.runId}`);
  } else {
    state = initState({ runId: args.runId, domain: args.domain, candidatesPath });
    writeJsonAtomic(statePath, state);
  }

  const fileSize = fs.statSync(candidatesPath).size;
  const cursor = Number.isFinite(state.cursor_bytes) ? Math.max(0, Math.floor(state.cursor_bytes)) : 0;
  const startByte = cursor <= fileSize ? cursor : 0;
  if (startByte !== cursor) state.cursor_bytes = startByte;

  const startedAt = utcNowIso();
  const inc = await readCandidatesIncremental({
    candidatesPath,
    startByte,
    maxCandidates: args.maxCandidates,
  });

  const byAction = { auto: 0, manual: 0, ignore: 0 };
  const byKind = {};

  for (const cand of inc.items) {
    const kind = String(cand && cand.kind ? cand.kind : "").trim() || "unknown";
    byKind[kind] = Number(byKind[kind] || 0) + 1;

    const decision = decideProposal({ domain: args.domain, candidate: cand });
    byAction[decision.action] = Number(byAction[decision.action] || 0) + 1;

    const proposalKey = decision.proposalKey;
    const proposalId = stableProposalId(proposalKey);
    const existing = state.groups[proposalKey] && typeof state.groups[proposalKey] === "object" ? state.groups[proposalKey] : null;
    const nowIso = utcNowIso();

    const candidateId = String(cand && cand.id ? cand.id : "").trim() || null;
    const src = summarizeSource(cand);

    if (!existing) {
      const g = {
        proposal_id: proposalId,
        kind,
        action: decision.action,
        reason: decision.reason,
        suggested: decision.suggested || null,
        first_seen_at: nowIso,
        last_seen_at: nowIso,
        count_candidates: 1,
        count_sources: 0,
        sample_candidate_ids: [],
        sample_sources: [],
      };
      if (candidateId) addToSample(g.sample_candidate_ids, candidateId, 20);
      if (src) {
        addToSample(g.sample_sources, src, 10);
        g.count_sources = 1;
      }
      state.groups[proposalKey] = g;
      continue;
    }

    existing.last_seen_at = nowIso;
    existing.count_candidates = Number(existing.count_candidates || 0) + 1;
    if (candidateId) addToSample(existing.sample_candidate_ids || (existing.sample_candidate_ids = []), candidateId, 20);

    if (src) {
      const beforeLen = Array.isArray(existing.sample_sources) ? existing.sample_sources.length : 0;
      addToSample(existing.sample_sources || (existing.sample_sources = []), src, 10);
      const afterLen = Array.isArray(existing.sample_sources) ? existing.sample_sources.length : beforeLen;
      if (afterLen > beforeLen) {
        existing.count_sources = Number(existing.count_sources || 0) + 1;
      }
    }
    state.groups[proposalKey] = existing;
  }

  state.stats.candidates_parsed = Number(state.stats.candidates_parsed || 0) + inc.parsed;
  state.stats.parse_errors = Number(state.stats.parse_errors || 0) + inc.errors;
  state.cursor_bytes = inc.nextCursor;
  state.updated_at = utcNowIso();
  writeJsonAtomic(statePath, state);

  let llmRun = null;
  if (args.llmProvider) {
    const llmStartedAt = utcNowIso();
    let llmUsage = null;
    try {
      const llm = createLLM({
        provider: args.llmProvider,
        model: args.llmModel,
        baseUrl: args.llmBaseUrl,
        apiKey: args.llmApiKey,
        fixturePath: args.llmFixture ? path.resolve(repoRoot, args.llmFixture) : null,
        timeoutMs: args.llmTimeoutMs,
      });

      const promptSystemAbs = path.isAbsolute(args.llmPromptSystem)
        ? args.llmPromptSystem
        : path.resolve(repoRoot, args.llmPromptSystem);
      const promptUserAbs = path.isAbsolute(args.llmPromptUser)
        ? args.llmPromptUser
        : path.resolve(repoRoot, args.llmPromptUser);
      if (!exists(promptSystemAbs)) throw new Error(`Missing --llm-prompt-system: ${promptSystemAbs}`);
      if (!exists(promptUserAbs)) throw new Error(`Missing --llm-prompt-user: ${promptUserAbs}`);

      const promptSystem = readText(promptSystemAbs);
      const promptUserTemplate = readText(promptUserAbs);
      const promptSha256 = sha256Hex(`${promptSystem}\n---\n${promptUserTemplate}`);

      const targetActions = parseActionSet(args.llmTargetActions);
      const groups = state.groups && typeof state.groups === "object" ? state.groups : {};
      const proposalIdToKey = new Map();
      for (const [proposalKey, group] of Object.entries(groups)) {
        const pid = group && group.proposal_id ? String(group.proposal_id) : "";
        if (pid) proposalIdToKey.set(pid, proposalKey);
      }

      const targets = [];
      for (const [proposalKey, group] of Object.entries(groups)) {
        const baselineAction = normalizeAction(group && group.action ? group.action : "");
        if (!baselineAction || !targetActions.has(baselineAction)) continue;
        const hasLlm = group && group.llm && typeof group.llm === "object" && normalizeAction(group.llm.action);
        if (hasLlm && !args.llmOverwrite) continue;
        const sampleSources = Array.isArray(group.sample_sources) ? group.sample_sources : [];
        const parsedSources = sampleSources
          .map((s) => {
            try {
              return JSON.parse(String(s));
            } catch {
              return String(s);
            }
          })
          .slice(0, 10);
        targets.push({
          proposal_id: String(group.proposal_id || ""),
          kind: String(group.kind || "unknown"),
          baseline: {
            action: baselineAction,
            reason: String(group.reason || ""),
            suggested: group.suggested || null,
          },
          counts: {
            candidates: Number(group.count_candidates || 0),
            sources: Number(group.count_sources || 0),
          },
          samples: {
            candidate_ids: Array.isArray(group.sample_candidate_ids) ? group.sample_candidate_ids.slice(0, 20) : [],
            sources: parsedSources,
          },
        });
      }

      targets.sort((a, b) => String(a.proposal_id).localeCompare(String(b.proposal_id)));
      const limited =
        args.llmMaxProposals > 0 && targets.length > args.llmMaxProposals ? targets.slice(0, args.llmMaxProposals) : targets;

      let llmApplied = 0;
      let llmInvalid = 0;
      let llmMissing = 0;
      let llmUpdatesReceived = 0;

      if (limited.length > 0) {
        const input = {
          version: 1,
          domain: args.domain,
          run_id: args.runId,
          proposals: limited,
        };
        const inputJson = JSON.stringify(input, null, 2);
        const userPrompt = fillTemplate(promptUserTemplate, {
          DOMAIN: args.domain,
          RUN_ID: args.runId,
          INPUT_JSON: inputJson,
        });

        const messages = [
          { role: "system", content: promptSystem },
          { role: "user", content: userPrompt },
        ];

        const resp = typeof llm.completeRaw === "function" ? await llm.completeRaw({ messages }) : null;
        const raw = resp ? resp.content : await llm.complete({ messages });
        const usage = resp && resp.usage ? resp.usage : null;
        llmUsage = usage;

        if (llmCapturePath) {
          writeJsonAtomic(llmCapturePath, {
            version: 1,
            ts: utcNowIso(),
            op: "curate_proposals",
            domain: args.domain,
            run_id: args.runId,
            llm: { provider: llm.provider, model: llm.model, base_url: llm.baseUrl || "" },
            prompts: {
              system: path.relative(repoRoot, promptSystemAbs),
              user: path.relative(repoRoot, promptUserAbs),
              sha256: promptSha256,
            },
            usage,
            request: { messages },
            response: { content: String(raw || "") },
            input_sha256: sha256Hex(`${promptSystem}\n---\n${userPrompt}`),
            output_sha256: sha256Hex(String(raw || "")),
          });
        }

        const parsed = JSON.parse(extractJsonFromText(raw));
        const updates = parsed && Array.isArray(parsed.updates) ? parsed.updates : [];
        llmUpdatesReceived = updates.length;

        for (const u of updates) {
          const pid = String(u && u.proposal_id ? u.proposal_id : "").trim();
          if (!pid) {
            llmInvalid += 1;
            continue;
          }
          const proposalKey = proposalIdToKey.get(pid);
          if (!proposalKey) {
            llmMissing += 1;
            continue;
          }
          const action = normalizeAction(u && u.action ? u.action : "");
          if (!action) {
            llmInvalid += 1;
            continue;
          }

          const group = groups[proposalKey];
          const nowIso = utcNowIso();

          const llmObj = {
            provider: llm.provider,
            model: llm.model,
            prompts: {
              system: path.relative(repoRoot, promptSystemAbs),
              user: path.relative(repoRoot, promptUserAbs),
              sha256: promptSha256,
            },
            updated_at: nowIso,
            action,
          };

          if (typeof u.reason === "string" && u.reason.trim()) llmObj.reason = u.reason.trim();
          if (typeof u.confidence === "number" && Number.isFinite(u.confidence)) {
            llmObj.confidence = Math.max(0, Math.min(1, u.confidence));
          }

          if ("suggested" in (u || {})) {
            if (u.suggested == null) {
              llmObj.suggested = null;
            } else if (typeof u.suggested === "object") {
              const sid = u.suggested.id ? parseSuggestedId(u.suggested.id, args.domain) : null;
              const topicRaw = sid ? sid.topic : u.suggested.topic;
              const slugRaw = sid ? sid.slug : u.suggested.slug;

              const topic = sanitizeTopicId(topicRaw);
              const slug = sanitizeSlugId(slugRaw);
              const title = String(u.suggested.title || (group && group.suggested && group.suggested.title) || "").trim();

              if (action === "ignore") {
                llmObj.suggested = null;
              } else if (!topic || !slug) {
                llmInvalid += 1;
                continue;
              } else {
                llmObj.suggested = {
                  id: `${args.domain}/${topic}/${slug}`,
                  domain: args.domain,
                  topic,
                  slug,
                  title,
                };
              }
            } else {
              llmInvalid += 1;
              continue;
            }
          } else if (action === "ignore") {
            llmObj.suggested = null;
          }

          group.llm = llmObj;
          groups[proposalKey] = group;
          llmApplied += 1;
        }

        state.groups = groups;
        state.updated_at = utcNowIso();
        writeJsonAtomic(statePath, state);
      }

      llmRun = {
        started_at: llmStartedAt,
        finished_at: utcNowIso(),
        provider: llm.provider,
        model: llm.model,
        prompts: {
          system: path.relative(repoRoot, promptSystemAbs),
          user: path.relative(repoRoot, promptUserAbs),
          sha256: promptSha256,
        },
        selection: {
          target_actions: Array.from(targetActions),
          max_proposals: args.llmMaxProposals,
          overwrite: !!args.llmOverwrite,
        },
        usage: llmUsage,
        capture: llmCapturePath ? path.relative(repoRoot, llmCapturePath) : null,
        stats: {
          eligible_total: targets.length,
          sent_total: limited.length,
          updates_received: llmUpdatesReceived,
          updates_applied: llmApplied,
          updates_invalid: llmInvalid,
          updates_missing: llmMissing,
        },
      };
    } catch (e) {
      llmRun = {
        started_at: llmStartedAt,
        finished_at: utcNowIso(),
        error: String(e && e.message ? e.message : e),
      };
      if (args.llmStrict) throw e;
      console.error(`[curator][llm] ${llmRun.error}`);
    }
  }

  const groups = state.groups && typeof state.groups === "object" ? state.groups : {};
  const proposalKeys = Object.keys(groups);
  const proposals = proposalKeys.map((k) => groupToOutput(groups[k]));
  proposals.sort((a, b) => String(a.proposal_id).localeCompare(String(b.proposal_id)));

  const candidatesTotal = Number(state.stats && state.stats.candidates_parsed ? state.stats.candidates_parsed : 0);
  const proposalsTotal = proposals.length;
  const duplicatesTotal = Math.max(0, candidatesTotal - proposalsTotal);

  const out = {
    version: 1,
    generated_at: utcNowIso(),
    run_id: args.runId,
    domain: args.domain,
    llm: llmRun,
    inputs: {
      candidates: path.relative(repoRoot, candidatesPath),
    },
    resume: {
      state: path.relative(repoRoot, statePath),
      cursor_bytes: state.cursor_bytes,
    },
    stats: {
      candidates_total: candidatesTotal,
      proposals_total: proposalsTotal,
      duplicates_total: duplicatesTotal,
      new_candidates_parsed: inc.parsed,
      parse_errors_total: Number(state.stats && state.stats.parse_errors ? state.stats.parse_errors : 0),
      by_action_new: byAction,
      by_kind_new: byKind,
    },
    proposals,
  };
  writeJsonAtomic(outPath, out);

  appendJsonl(logPath, {
    ts: utcNowIso(),
    run_id: args.runId,
    domain: args.domain,
    started_at: startedAt,
    finished_at: utcNowIso(),
    cursor_bytes: state.cursor_bytes,
    new_candidates_parsed: inc.parsed,
    parse_errors: inc.errors,
    proposals_total: proposalsTotal,
    duplicates_total: duplicatesTotal,
  });

  console.log(`[curator] curation: ${outPath}`);
  console.log(`[curator] state: ${statePath}`);
  console.log(`[curator] candidates_total=${candidatesTotal} proposals_total=${proposalsTotal} duplicates_total=${duplicatesTotal}`);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const repoRoot = path.resolve(__dirname, "..", "..");

  while (true) {
    await mainOnce({ repoRoot, args });
    if (!args.loop) break;
    if (args.sleepMs > 0) await sleep(args.sleepMs);
    if (args.cycleSleepMs > 0) await sleep(args.cycleSleepMs);
  }
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
