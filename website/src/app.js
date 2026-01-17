/* eslint-disable no-console */

function $(id) {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Missing element: ${id}`);
  return el;
}

function normalize(text) {
  return String(text || "").toLowerCase();
}

function escapeForClipboard(text) {
  return String(text || "");
}

function renderTemplate(text, skill) {
  const id = String(skill && skill.id ? skill.id : "");
  const parts = id.split("/");
  const domain = String(skill && skill.domain ? skill.domain : parts[0] || "");
  const topic = String(parts[1] || "");
  const slug = String(parts[2] || "");
  const title = String(skill && skill.title ? skill.title : "");
  const level = String(skill && skill.level ? skill.level : "");
  const risk = String(skill && skill.risk_level ? skill.risk_level : "");

  const vars = { id, domain, topic, slug, title, level, risk_level: risk };
  return String(text || "").replace(/\{\{([a-zA-Z0-9_]+)\}\}/g, (m, k) => (k in vars ? vars[k] : m));
}

async function copyText(text) {
  const value = escapeForClipboard(text);
  if (navigator.clipboard && navigator.clipboard.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const ta = document.createElement("textarea");
  ta.value = value;
  ta.style.position = "fixed";
  ta.style.left = "-1000px";
  document.body.appendChild(ta);
  ta.select();
  document.execCommand("copy");
  document.body.removeChild(ta);
}

function setBadge(el, text, cls) {
  el.textContent = text;
  el.className = `badge ${cls || ""}`.trim();
}

function parseHashId() {
  const h = window.location.hash || "";
  if (!h.startsWith("#")) return null;
  const id = decodeURIComponent(h.slice(1)).trim();
  return id || null;
}

function setHashId(id) {
  const next = `#${encodeURIComponent(id)}`;
  if (window.location.hash === next) return;
  window.location.hash = next;
}

async function main() {
  const q = $("q");
  const results = $("results");
  const count = $("count");

  const empty = $("empty");
  const panel = $("panel");
  const panelTitle = $("panelTitle");
  const badgeDomain = $("badgeDomain");
  const badgeLevel = $("badgeLevel");
  const badgeRisk = $("badgeRisk");
  const tabLibrary = $("tabLibrary");
  const tabSkill = $("tabSkill");
  const tabSources = $("tabSources");
  const copyBtn = $("copyBtn");

  const tabs = Array.from(document.querySelectorAll(".tab"));

  let apiMode = false;
  let totalMatches = 0;

  let skills = [];
  const skillsById = new Map();
  const contentCache = new Map(); // `${id}|${tab}` -> string

  const MAX_RESULTS = 250;

  let currentId = null;
  let filtered = skills;
  let loadSeq = 0;
  let searchSeq = 0;

  async function tryFetchJson(url) {
    const resp = await fetch(url, { cache: "no-store" });
    if (!resp.ok) return null;
    try {
      return await resp.json();
    } catch {
      return null;
    }
  }

  async function apiFetchSkill(id) {
    const u = new URL("./api/skill", window.location.href);
    u.searchParams.set("id", id);
    const json = await tryFetchJson(u.toString());
    if (!json || !json.ok || !json.skill) return null;
    return json.skill;
  }

  async function apiSearch(query) {
    const u = new URL("./api/search", window.location.href);
    u.searchParams.set("q", query || "");
    u.searchParams.set("limit", String(MAX_RESULTS));
    const json = await tryFetchJson(u.toString());
    if (!json || !json.ok) return null;
    const results = Array.isArray(json.results) ? json.results : [];
    return { total: Number(json.total || 0), results };
  }

  async function initIndexOrApi() {
    // Prefer local backend API mode when available; fallback to static index.json.
    const summary = await tryFetchJson("./api/summary");
    if (summary && summary.ok) {
      apiMode = true;
      totalMatches = Number(summary.skills_count || 0);
      count.textContent = String(totalMatches);

      const initial = await apiSearch("");
      if (initial) {
        filtered = initial.results;
        totalMatches = initial.total;
        count.textContent = String(totalMatches);
        for (const s of filtered) if (s && s.id) skillsById.set(s.id, s);
      } else {
        filtered = [];
        totalMatches = 0;
        count.textContent = "0";
      }
      return;
    }

    const indexResp = await fetch("./index.json", { cache: "no-store" });
    if (!indexResp.ok) throw new Error(`Failed to load index.json: ${indexResp.status}`);
    const index = await indexResp.json();
    skills = Array.isArray(index.skills) ? index.skills : [];
    for (const s of skills) {
      s._haystack = normalize(`${s.id || ""} ${s.title || ""} ${s.domain || ""}`);
      if (s && s.id) skillsById.set(s.id, s);
    }
    filtered = skills;
    totalMatches = skills.length;
    count.textContent = String(totalMatches);
  }

  function renderList() {
    results.innerHTML = "";
    const frag = document.createDocumentFragment();
    const shown = filtered.slice(0, MAX_RESULTS);
    for (const s of shown) {
      const row = document.createElement("div");
      row.className = `row${s.id === currentId ? " active" : ""}`;
      row.dataset.id = s.id;

      const title = document.createElement("div");
      title.className = "row-title";
      title.textContent = s.title || s.id;

      const sub = document.createElement("div");
      sub.className = "row-sub";
      sub.textContent = `${s.id} · ${s.level}/${s.risk_level}`;

      row.appendChild(title);
      row.appendChild(sub);

      row.addEventListener("click", () => selectSkill(s.id));
      frag.appendChild(row);
    }
    if (totalMatches > shown.length) {
      const more = document.createElement("div");
      more.className = "row";
      more.style.cursor = "default";
      more.style.opacity = "0.8";
      more.innerHTML = `<div class="row-title">Showing ${shown.length} of ${totalMatches} matches</div><div class="row-sub">Refine your search to narrow results.</div>`;
      frag.appendChild(more);
    }
    results.appendChild(frag);
  }

  function activateTab(name) {
    for (const t of tabs) {
      const active = t.dataset.tab === name;
      t.classList.toggle("active", active);
    }
    tabLibrary.classList.toggle("hidden", name !== "library");
    tabSkill.classList.toggle("hidden", name !== "skill");
    tabSources.classList.toggle("hidden", name !== "sources");
    copyBtn.disabled = name !== "library";
    void ensureTabContent(name);
  }

  async function loadContent(s, tabName) {
    const cacheKey = `${s.id}|${tabName}`;
    if (contentCache.has(cacheKey)) return contentCache.get(cacheKey);

    // Back-compat: older index.json may embed full markdown.
    const embedded =
      tabName === "library" ? s.library_md : tabName === "skill" ? s.skill_md : tabName === "sources" ? s.sources_md : null;
    if (typeof embedded === "string" && embedded.length > 0) {
      contentCache.set(cacheKey, embedded);
      return embedded;
    }

    const fileKey = tabName === "library" ? "library" : tabName;
    let filePath = s.files && s.files[fileKey] ? String(s.files[fileKey]) : "";
    if (!filePath) {
      const baseId = (s.template ? String(s.template) : String(s.id || "")).replace(/^[\\/]+/, "");
      if (baseId.includes("..")) throw new Error(`Invalid id for ${tabName}`);
      const idPath = baseId;
      if (!idPath) throw new Error(`Missing id for ${tabName}`);
      const base = `skills/${idPath}`;
      if (tabName === "library") filePath = `${base}/library.md`;
      else if (tabName === "skill") filePath = `${base}/skill.md`;
      else if (tabName === "sources") filePath = `${base}/reference/sources.md`;
    }
    if (!filePath) throw new Error(`Missing file path for ${tabName}: ${s.id}`);

    const resp = await fetch(`./${filePath.replace(/^[\\/]+/, "")}`, { cache: "no-store" });
    if (!resp.ok) throw new Error(`Failed to load ${tabName} (${resp.status}): ${s.id}`);
    let text = await resp.text();
    if (s.template) text = renderTemplate(text, s);
    contentCache.set(cacheKey, text);
    return text;
  }

  async function ensureTabContent(tabName) {
    if (!currentId) return;
    const s = skillsById.get(currentId);
    if (!s) return;

    const seq = loadSeq;
    const target =
      tabName === "library" ? tabLibrary : tabName === "skill" ? tabSkill : tabName === "sources" ? tabSources : null;
    if (!target) return;

    if (!target.textContent) target.textContent = "Loading...";
    copyBtn.disabled = tabName !== "library";

    try {
      const text = await loadContent(s, tabName);
      if (seq !== loadSeq) return;
      target.textContent = text;
    } catch (e) {
      if (seq !== loadSeq) return;
      target.textContent = String(e && e.message ? e.message : e);
    }
  }

  function selectSkill(id) {
    const s = skillsById.get(id);
    if (!s) return;
    loadSeq++;
    currentId = s.id;
    setHashId(s.id);

    empty.classList.add("hidden");
    panel.classList.remove("hidden");

    panelTitle.textContent = s.title || s.id;
    setBadge(badgeDomain, s.domain || "unknown", "");
    setBadge(badgeLevel, s.level || "bronze", "");
    setBadge(badgeRisk, s.risk_level || "low", `risk-${s.risk_level || "low"}`);

    tabLibrary.textContent = s.library_md || "";
    tabSkill.textContent = s.skill_md || "";
    tabSources.textContent = s.sources_md || "";

    renderList();
    activateTab("library");
  }

  q.addEventListener("input", async () => {
    const v = normalize(q.value);
    if (!apiMode) {
      filtered = v ? skills.filter((s) => s._haystack.includes(v)) : skills;
      totalMatches = filtered.length;
      count.textContent = String(totalMatches);
      renderList();
      return;
    }

    const seq = ++searchSeq;
    const r = await apiSearch(v);
    if (seq !== searchSeq) return;
    if (!r) {
      filtered = [];
      totalMatches = 0;
      count.textContent = "0";
      renderList();
      return;
    }
    filtered = r.results;
    totalMatches = r.total;
    count.textContent = String(totalMatches);
    for (const s of filtered) if (s && s.id) skillsById.set(s.id, s);
    renderList();
  });

  for (const t of tabs) {
    t.addEventListener("click", () => activateTab(t.dataset.tab));
  }

  copyBtn.addEventListener("click", async () => {
    const s = currentId ? skillsById.get(currentId) : null;
    if (!s) return;
    const seq = loadSeq;
    try {
      const text = await loadContent(s, "library");
      if (seq !== loadSeq) return;
      await copyText(text || "");
    } catch (e) {
      alert(String(e && e.message ? e.message : e));
      return;
    }
    copyBtn.textContent = "Copied";
    setTimeout(() => {
      copyBtn.textContent = "Copy Library";
    }, 900);
  });

  await initIndexOrApi();
  renderList();

  const initial = parseHashId();
  if (initial) {
    if (!apiMode) {
      if (skillsById.has(initial)) selectSkill(initial);
    } else {
      const s = await apiFetchSkill(initial);
      if (s && s.id) {
        skillsById.set(s.id, s);
        selectSkill(s.id);
      }
    }
  }
}

main().catch((e) => {
  console.error(e);
  alert(String(e && e.message ? e.message : e));
});

