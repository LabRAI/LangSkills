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

  const indexResp = await fetch("./index.json", { cache: "no-store" });
  if (!indexResp.ok) throw new Error(`Failed to load index.json: ${indexResp.status}`);
  const index = await indexResp.json();
  const skills = Array.isArray(index.skills) ? index.skills : [];
  for (const s of skills) {
    s._haystack = normalize(`${s.id || ""} ${s.title || ""} ${s.domain || ""}`);
  }
  count.textContent = String(skills.length);

  const skillsById = new Map(skills.map((s) => [s.id, s]));
  const contentCache = new Map(); // `${id}|${tab}` -> string

  const MAX_RESULTS = 250;

  let currentId = null;
  let filtered = skills;
  let loadSeq = 0;

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
    if (filtered.length > MAX_RESULTS) {
      const more = document.createElement("div");
      more.className = "row";
      more.style.cursor = "default";
      more.style.opacity = "0.8";
      more.innerHTML = `<div class="row-title">Showing ${MAX_RESULTS} of ${filtered.length} matches</div><div class="row-sub">Refine your search to narrow results.</div>`;
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
      const idPath = String(s.id || "").replace(/^\\/+/, "");
      if (!idPath) throw new Error(`Missing id for ${tabName}`);
      const base = `skills/${idPath}`;
      if (tabName === "library") filePath = `${base}/library.md`;
      else if (tabName === "skill") filePath = `${base}/skill.md`;
      else if (tabName === "sources") filePath = `${base}/reference/sources.md`;
    }
    if (!filePath) throw new Error(`Missing file path for ${tabName}: ${s.id}`);

    const resp = await fetch(`./${filePath.replace(/^\\/+/, "")}`, { cache: "no-store" });
    if (!resp.ok) throw new Error(`Failed to load ${tabName} (${resp.status}): ${s.id}`);
    const text = await resp.text();
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

  q.addEventListener("input", () => {
    const v = normalize(q.value);
    filtered = v ? skills.filter((s) => s._haystack.includes(v)) : skills;
    count.textContent = String(filtered.length);
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

  renderList();

  const initial = parseHashId();
  if (initial && skillsById.has(initial)) {
    selectSkill(initial);
  }
}

main().catch((e) => {
  console.error(e);
  alert(String(e && e.message ? e.message : e));
});

