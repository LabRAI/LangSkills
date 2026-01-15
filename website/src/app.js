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
  count.textContent = String(skills.length);

  let currentId = null;
  let filtered = skills;

  function renderList() {
    results.innerHTML = "";
    for (const s of filtered) {
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
      results.appendChild(row);
    }
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
  }

  function selectSkill(id) {
    const s = skills.find((x) => x.id === id);
    if (!s) return;
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
    filtered = skills.filter(
      (s) =>
        normalize(s.id).includes(v) ||
        normalize(s.title).includes(v) ||
        normalize(s.domain).includes(v),
    );
    renderList();
  });

  for (const t of tabs) {
    t.addEventListener("click", () => activateTab(t.dataset.tab));
  }

  copyBtn.addEventListener("click", async () => {
    const s = skills.find((x) => x.id === currentId);
    if (!s) return;
    await copyText(s.library_md || "");
    copyBtn.textContent = "Copied";
    setTimeout(() => {
      copyBtn.textContent = "Copy Library";
    }, 900);
  });

  renderList();

  const initial = parseHashId();
  if (initial && skills.some((x) => x.id === initial)) {
    selectSkill(initial);
  }
}

main().catch((e) => {
  console.error(e);
  alert(String(e && e.message ? e.message : e));
});

