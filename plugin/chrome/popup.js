/* global chrome */

function $(id) {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Missing element: ${id}`);
  return el;
}

function normalize(text) {
  return String(text || "").toLowerCase();
}

function setStatus(text, kind = "muted") {
  const el = $("status");
  el.textContent = text;
  el.style.color = kind === "error" ? "#f87171" : "#94a3b8";
}

function setBadge(el, text, cls) {
  el.textContent = text;
  el.className = `badge ${cls || ""}`.trim();
}

async function copyText(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    await navigator.clipboard.writeText(String(text || ""));
    return;
  }
  throw new Error("Clipboard API not available");
}

const DEFAULT_BASE = "http://127.0.0.1:4173/";

async function loadBaseUrl() {
  const r = await chrome.storage.local.get(["baseUrl"]);
  return r.baseUrl || DEFAULT_BASE;
}

async function saveBaseUrl(baseUrl) {
  await chrome.storage.local.set({ baseUrl });
}

function normalizeBaseUrl(url) {
  let v = String(url || "").trim();
  if (!v) return DEFAULT_BASE;
  if (!v.endsWith("/")) v += "/";
  return v;
}

async function fetchIndex(baseUrl) {
  const url = `${baseUrl}index.json`;
  const resp = await fetch(url, { cache: "no-store" });
  if (!resp.ok) throw new Error(`Failed to load index.json (${resp.status})`);
  const json = await resp.json();
  const skills = Array.isArray(json.skills) ? json.skills : [];
  return { url, skills };
}

async function main() {
  const baseUrlInput = $("baseUrl");
  const saveBaseBtn = $("saveBase");
  const q = $("q");
  const results = $("results");
  const count = $("count");

  const detail = $("detail");
  const detailTitle = $("detailTitle");
  const badgeRisk = $("badgeRisk");
  const badgeLevel = $("badgeLevel");
  const library = $("library");
  const copyBtn = $("copy");
  const openBtn = $("open");

  let baseUrl = normalizeBaseUrl(await loadBaseUrl());
  baseUrlInput.value = baseUrl;

  let skills = [];
  let filtered = [];
  let current = null;
  const contentCache = new Map(); // id -> library text

  const MAX_RESULTS = 120;

  async function loadLibrary(s) {
    if (!s || !s.id) return "";
    if (contentCache.has(s.id)) return contentCache.get(s.id);

    // Back-compat: older index.json may embed full markdown.
    if (typeof s.library_md === "string" && s.library_md.length > 0) {
      contentCache.set(s.id, s.library_md);
      return s.library_md;
    }

    let filePath = s.files && s.files.library ? String(s.files.library) : "";
    if (!filePath) {
      const idPath = String(s.id || "").replace(/^\\/+/, "");
      if (!idPath) throw new Error("Missing id for library path");
      filePath = `skills/${idPath}/library.md`;
    }
    if (!filePath) throw new Error(`Missing library path: ${s.id}`);

    const url = `${baseUrl}${filePath.replace(/^\\/+/, "")}`;
    const resp = await fetch(url, { cache: "no-store" });
    if (!resp.ok) throw new Error(`Failed to load library (${resp.status}): ${s.id}`);
    const text = await resp.text();
    contentCache.set(s.id, text);
    return text;
  }

  async function reloadIndex() {
    setStatus("Loading index...");
    try {
      const { url, skills: next } = await fetchIndex(baseUrl);
      skills = next;
      for (const s of skills) {
        s._haystack = normalize(`${s.id || ""} ${s.title || ""} ${s.domain || ""}`);
      }
      filtered = skills;
      count.textContent = String(skills.length);
      setStatus(`Loaded: ${url}`);
      renderList();
    } catch (e) {
      setStatus(String(e && e.message ? e.message : e), "error");
      skills = [];
      filtered = [];
      count.textContent = "0";
      results.innerHTML = "";
    }
  }

  function renderList() {
    results.innerHTML = "";
    const shown = filtered.slice(0, MAX_RESULTS);
    for (const s of shown) {
      const item = document.createElement("div");
      item.className = "item";

      const t = document.createElement("div");
      t.className = "item-title";
      t.textContent = s.title || s.id;

      const sub = document.createElement("div");
      sub.className = "item-sub";
      sub.textContent = `${s.id} · ${s.level}/${s.risk_level}`;

      item.appendChild(t);
      item.appendChild(sub);
      item.addEventListener("click", () => select(s.id));
      results.appendChild(item);
    }
    if (filtered.length > MAX_RESULTS) {
      const item = document.createElement("div");
      item.className = "item";
      item.style.opacity = "0.8";
      const t = document.createElement("div");
      t.className = "item-title";
      t.textContent = `Showing ${MAX_RESULTS} of ${filtered.length} matches`;
      const sub = document.createElement("div");
      sub.className = "item-sub";
      sub.textContent = "Refine your search to narrow results.";
      item.appendChild(t);
      item.appendChild(sub);
      results.appendChild(item);
    }
  }

  async function select(id) {
    const s = skills.find((x) => x.id === id);
    if (!s) return;
    current = s;
    detail.classList.remove("hidden");
    detailTitle.textContent = s.title || s.id;
    setBadge(badgeRisk, s.risk_level || "low", `risk-${s.risk_level || "low"}`);
    setBadge(badgeLevel, s.level || "bronze", "");
    library.textContent = "Loading...";
    try {
      library.textContent = await loadLibrary(s);
    } catch (e) {
      library.textContent = String(e && e.message ? e.message : e);
    }
  }

  q.addEventListener("input", () => {
    const v = normalize(q.value);
    filtered = v ? skills.filter((s) => String(s._haystack || "").includes(v)) : skills;
    count.textContent = String(filtered.length);
    renderList();
  });

  copyBtn.addEventListener("click", async () => {
    if (!current) return;
    try {
      const text = await loadLibrary(current);
      await copyText(text || "");
    } catch (e) {
      setStatus(String(e && e.message ? e.message : e), "error");
      return;
    }
    copyBtn.textContent = "Copied";
    setTimeout(() => {
      copyBtn.textContent = "Copy";
    }, 900);
  });

  openBtn.addEventListener("click", async () => {
    if (!current) return;
    const url = `${baseUrl}#${encodeURIComponent(current.id)}`;
    await chrome.tabs.create({ url });
  });

  saveBaseBtn.addEventListener("click", async () => {
    baseUrl = normalizeBaseUrl(baseUrlInput.value);
    baseUrlInput.value = baseUrl;
    await saveBaseUrl(baseUrl);
    await reloadIndex();
  });

  await reloadIndex();
}

main().catch((e) => {
  setStatus(String(e && e.message ? e.message : e), "error");
});
