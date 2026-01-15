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

const DEFAULT_BASE = "https://shatianming5.github.io/skill_lain/";

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

  async function reloadIndex() {
    setStatus("Loading index...");
    try {
      const { url, skills: next } = await fetchIndex(baseUrl);
      skills = next;
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
    for (const s of filtered) {
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
  }

  function select(id) {
    const s = skills.find((x) => x.id === id);
    if (!s) return;
    current = s;
    detail.classList.remove("hidden");
    detailTitle.textContent = s.title || s.id;
    setBadge(badgeRisk, s.risk_level || "low", `risk-${s.risk_level || "low"}`);
    setBadge(badgeLevel, s.level || "bronze", "");
    library.textContent = s.library_md || "";
  }

  q.addEventListener("input", () => {
    const v = normalize(q.value);
    filtered = skills.filter(
      (s) =>
        normalize(s.id).includes(v) ||
        normalize(s.title).includes(v) ||
        normalize(s.domain).includes(v),
    );
    renderList();
  });

  copyBtn.addEventListener("click", async () => {
    if (!current) return;
    await copyText(current.library_md || "");
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

