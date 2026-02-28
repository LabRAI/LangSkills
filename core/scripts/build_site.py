from __future__ import annotations

import datetime as _dt
import html
import json
from pathlib import Path
from typing import Any

from ..utils.fs import ensure_dir, write_text_atomic
from ..utils.time import utc_now_iso_z


def build_site(*, repo_root: str | Path) -> tuple[Path, Path]:
    repo_root = Path(repo_root).resolve()
    skills_index_path = repo_root / "skills" / "index.json"
    if not skills_index_path.exists():
        raise FileNotFoundError(f"Missing: {skills_index_path}")

    idx = json.loads(skills_index_path.read_text(encoding="utf-8"))
    raw_items = idx.get("items") if isinstance(idx, dict) and isinstance(idx.get("items"), list) else []
    items = []
    seen: set[str] = set()
    for it in raw_items:
        if not isinstance(it, dict):
            continue
        key = str(it.get("skill_id") or it.get("dir") or it.get("source_id") or "").strip()
        if key in seen:
            continue
        seen.add(key)
        items.append(it)

    dist_dir = repo_root / "dist"
    ensure_dir(dist_dir)

    generated_at = utc_now_iso_z()
    write_text_atomic(dist_dir / "index.json", json.dumps({"generated_at": generated_at, **idx}, ensure_ascii=False, indent=2) + "\n")

    def esc(s: Any) -> str:
        return html.escape(str(s or ""), quote=True)

    rows = []
    for it in items:
        if not isinstance(it, dict):
            continue
        title = esc(it.get("title"))
        domain = esc(it.get("domain") or it.get("profile") or "")
        st = esc(it.get("source_type"))
        url = esc(it.get("source_url"))
        dir_ = esc(it.get("dir"))
        skill_kind = esc(it.get("skill_kind") or "")
        lang = esc(it.get("language") or "")
        skill_id = esc(it.get("skill_id") or it.get("source_id") or "")
        rows.append(
            f"<tr><td>{domain}</td><td>{skill_kind}</td><td>{st}</td><td>{lang}</td><td>{title}</td><td><a href=\"{url}\">source</a></td><td><code>{skill_id}</code></td><td><code>{dir_}</code></td></tr>"
        )

    html_text = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>LangSkills</title>
    <style>
      body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 24px; }}
      table {{ border-collapse: collapse; width: 100%; }}
      th, td {{ border: 1px solid #ddd; padding: 8px; vertical-align: top; }}
      th {{ background: #f7f7f7; text-align: left; }}
      input {{ width: 100%; padding: 10px; margin: 12px 0; font-size: 14px; }}
      code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }}
    </style>
  </head>
  <body>
    <h1>LangSkills</h1>
    <p>Generated at: {esc(generated_at)}</p>
    <input id="q" placeholder="Search: domain / title / url / dir" />
    <table>
      <thead>
        <tr><th>Profile</th><th>Skill Kind</th><th>Source</th><th>Lang</th><th>Title</th><th>URL</th><th>Skill ID</th><th>Dir</th></tr>
      </thead>
      <tbody id="rows">
        {"".join(rows)}
      </tbody>
    </table>
    <script>
      const q = document.getElementById('q');
      const tbody = document.getElementById('rows');
      const all = Array.from(tbody.querySelectorAll('tr'));
      q.addEventListener('input', () => {{
        const t = q.value.toLowerCase().trim();
        for (const tr of all) {{
          const s = tr.innerText.toLowerCase();
          tr.style.display = !t || s.includes(t) ? '' : 'none';
        }}
      }});
    </script>
  </body>
</html>
"""

    write_text_atomic(dist_dir / "index.html", html_text + "\n")
    return dist_dir / "index.json", dist_dir / "index.html"


def cli_build_site(argv: list[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    out_json, out_html = build_site(repo_root=repo_root)
    print(f"Wrote: {out_json.relative_to(repo_root).as_posix()}")
    print(f"Wrote: {out_html.relative_to(repo_root).as_posix()}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_build_site())
