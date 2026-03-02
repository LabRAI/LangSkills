<div align="center">

# LangSkills: Evidence-Backed Skills for Vibe Research & Vibe Coding

<p>
  <a href="https://www.python.org/downloads/"><img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" /></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green?style=flat-square" /></a>
  <a href="https://github.com/LabRAI/LangSkills"><img alt="GitHub stars" src="https://img.shields.io/github/stars/LabRAI/LangSkills?style=flat-square&logo=github" /></a>
  <img alt="Skills: 101k+" src="https://img.shields.io/badge/skills-101%2C330-8A2BE2?style=flat-square" />
  <img alt="Bundles: 21" src="https://img.shields.io/badge/bundles-21-orange?style=flat-square" />
  <img alt="Papers: 62k+" src="https://img.shields.io/badge/papers-62%2C582-red?style=flat-square" />
</p>

<p>🌐 <a href="https://labrai.github.io/LangSkills/"><b>LangSkills — Evidence-Backed Skills for AI Agents</b></a></p>


<h3>📄 101K Skills from 62K+ Papers & 23K+ Tech Sources — Search, Generate, Reuse</h3>


[**Quick Start**](#-quick-start) · [**Skill Library**](#-the-skill-library) · [**Pipeline**](#-the-pipeline) · [**Installation**](#-installation) · [**OpenClaw**](#-openclaw-integration) · [**CLI Reference**](#%EF%B8%8F-cli-reference) · [**Configuration**](#%EF%B8%8F-configuration)

</div>

---

## 📰 News

- **2026-02-28** — v0.1.0: 101,330 skills across 21 domain bundles officially released
- **2026-02-27** — Pre-built SQLite bundles with FTS5 full-text search ready for download
- **2026-02-27** — Journal pipeline online: PMC, PLOS, Nature, eLife, arXiv full coverage

---

## ✨ Key Features

- **📚 Massive Pre-Built Skill Library**: 101,330 evidence-backed skills covering 62K+ research papers and 23K+ coding/tech sources — all searchable offline via FTS5-powered SQLite bundles.

- **🔧 Fully Automated Skill Pipeline**: Give it a topic → it discovers sources → fetches & extracts text → generates skills with an LLM → validates quality → publishes. One command, zero manual work.

- **🔬 Evidence-First, Never Hallucination-Only**: Every skill traces back to real web pages, academic papers, or code repositories with full provenance chains — metadata, quality scores, and source links included.

- **🌐 Multi-Source Intelligence**: Integrates Tavily, GitHub, Baidu, Zhihu, XHS, StackOverflow, arXiv, PMC, PLOS, Nature, eLife — 10+ data source providers for comprehensive coverage.

- **🧠 LLM-Powered Quality Gates**: Each skill is generated, validated, and scored by LLMs with configurable quality thresholds — ensuring high-signal, low-noise output at scale.

- **⚡ Drop-In Reusability**: Download domain-specific SQLite bundles, `skill-search` any keyword, and get structured Markdown ready to feed into any AI agent, RAG pipeline, or knowledge base.

- **🏗️ Extensible Architecture**: Modular source providers, LLM backends (OpenAI / Ollama), queue-based batch processing, and configurable domain rules — built to scale.

- **📦 21 Domain Bundles**: From Linux sysadmin to PLOS biology, from web development to machine learning — organized, versioned, and individually installable.

---

## 🚀 Quick Start

```bash
git clone https://github.com/LabRAI/LangSkills.git && cd LangSkills
pip install -r requirements.txt && cp .env.example .env
# → Fill in OPENAI_API_KEY and OPENAI_BASE_URL in .env

# Auto-detect your project and install only matching bundles (~50-200 MB)
python3 langskills_cli.py bundle-install --auto

# Search the pre-built skill library (Vibe Research)
python3 langskills_cli.py skill-search "kubernetes networking" --top 5

# Generate new skills from any topic (Vibe Coding)
python3 langskills_cli.py capture "Docker networking@15"
```

> Full setup details → [Installation](#-installation)

---

## 📄 The Skill Library

**62,582 research skills** distilled from academic papers + **23,765 coding/tech skills** from GitHub, StackOverflow, and the web — all searchable offline.

| Domain | Skills | Sources |
|:---|---:|:---|
| 📄 research-plos-\* | 35,505 | PLOS ONE, Biology, CompBio, Medicine, Genetics, NTD, Pathogens |
| 📄 research-arxiv | 3,483 | arXiv papers |
| 📄 research-elife | 391 | eLife journal |
| 📄 research-other | 23,203 | Other academic sources |
| 💻 linux | 7,455 | Linux / sysadmin |
| 💻 web | 6,029 | Web development |
| 💻 programming | 4,071 | General programming |
| 💻 devtools | 2,243 | Developer tools |
| 💻 security | 1,182 | Security |
| 💻 cloud / data / ml / llm / observability | 2,785 | Infra & ML |
| 🗂️ other | 14,983 | Uncategorized |
| | **101,330** | **21 SQLite bundles** |

<details>
<summary><b>🔍 How to Use the Library</b></summary>
<br/>

```bash
# Install a domain bundle (downloads from GitHub Releases)
python3 langskills_cli.py bundle-install --domain linux

# Or auto-detect your project type and install matching bundles
python3 langskills_cli.py bundle-install --auto

# Search skills offline (FTS5 full-text search)
python3 langskills_cli.py skill-search "container orchestration" --top 10

# Filter by domain and minimum quality score
python3 langskills_cli.py skill-search "CRISPR" --domain research --min-score 4.0

# Get full skill content as Markdown
python3 langskills_cli.py skill-search "React hooks" --content --format markdown
```

</details>

<details>
<summary><b>📦 Skill Package Structure</b></summary>
<br/>

Each skill is a structured Markdown package with full traceability:

```
skills/by-skill/<domain>/<topic>/
├── skill.md          # The skill content (tutorial / how-to / protocol)
├── metadata.yaml     # Provenance, tags, quality score, LLM model used
└── source.json       # Evidence trail back to original web/paper source
```

> Every skill traces to real sources — never hallucination-only.

</details>

---

## 🔧 The Pipeline

<details>
<summary><b>📋 Step-by-Step Usage</b></summary>
<br/>

**1. Explore sources** (optional)

```bash
python3 langskills_cli.py search tavily "Linux journalctl" --limit 20
python3 langskills_cli.py search github "journalctl" --limit 10
```

**2. Capture skills from a topic**

```bash
# Basic
python3 langskills_cli.py capture "journalctl@15"

# Target a specific domain
python3 langskills_cli.py capture "React hooks@20" --domain web

# All domains
python3 langskills_cli.py capture "Kubernetes" --all --total 30
```

> `@N` is shorthand for `--total N`. The pipeline auto-runs: search → fetch → generate → dedupe → improve → validate.

**3. Validate & publish**

```bash
python3 langskills_cli.py validate --strict --package
python3 langskills_cli.py reindex-skills --root skills/by-skill
```

**4. Build bundles & site**

```bash
python3 langskills_cli.py build-site
python3 langskills_cli.py build-bundle --split-by-domain
```

**5. Batch processing** (large-scale)

```bash
python3 langskills_cli.py queue-seed                     # seed from config
python3 langskills_cli.py topics-capture topics/arxiv.txt # or from file
python3 langskills_cli.py runner                          # start worker
python3 langskills_cli.py queue-watch                     # monitor
```

</details>

<details>
<summary><b>📂 Pipeline Output</b></summary>
<br/>

```
captures/<run-id>/
├── manifest.json          # Run metadata
├── sources/               # Fetched evidence per source
├── skills/                # Generated skill packages
│   └── <domain>/<topic>/
│       └── skill.md
└── quality_report.md      # Validation summary
```

</details>

---

## 📦 Installation

LangSkills supports **Linux**, **macOS**, and **Windows**. Python 3.10+ required.

<details>
<summary><b>🐧 Linux / 🍎 macOS</b></summary>
<br/>

```bash
git clone https://github.com/LabRAI/LangSkills.git && cd LangSkills
python3 -m venv .venv && source .venv/bin/activate
pip install -U pip && pip install -r requirements.txt
playwright install chromium          # optional: Baidu/Zhihu/XHS sources
cp .env.example .env                 # fill OPENAI_API_KEY + OPENAI_BASE_URL
python3 langskills_cli.py self-check --skip-remote
```

</details>

<details>
<summary><b>💻 Windows</b></summary>
<br/>

```cmd
git clone https://github.com/LabRAI/LangSkills.git && cd LangSkills
python -m venv .venv && .venv\Scripts\activate
pip install -U pip && pip install -r requirements.txt
copy .env.example .env               # fill OPENAI_API_KEY + OPENAI_BASE_URL
python langskills_cli.py self-check --skip-remote
```

</details>

<details>
<summary><b>Environment Variables</b></summary>
<br/>

| Variable | Required | Description |
|:---|:---:|:---|
| `OPENAI_API_KEY` | **Yes** | OpenAI-compatible API key for skill generation |
| `OPENAI_BASE_URL` | **Yes** | API base URL (e.g., `https://api.openai.com/v1`) |
| `OPENAI_MODEL` | No | Model name (default: `gpt-4.1-mini`) |
| `LLM_PROVIDER` | No | `openai` (default) or `ollama` |
| `GITHUB_TOKEN` | No | Recommended for GitHub search (avoids rate limits) |
| `TAVILY_API_KEY` | No | Required for Tavily web search |
| `LANGSKILLS_WORKDIR` | No | Runtime data directory (default: `var/`) |

> More variables → [Configuration](#%EF%B8%8F-configuration)

</details>

---

## 🤖 AI CLI One-Liner — Auto Setup

> Copy the prompt below and paste it into **Claude Code / Codex / Cursor / Windsurf** — the AI agent will automatically clone, install, configure, and verify LangSkills for you.

```text
Do the following steps in order. Do NOT skip any step.

1. Clone the repo and enter the directory:
   git clone https://github.com/LabRAI/LangSkills.git && cd LangSkills

2. Create a Python 3.10+ virtual environment and activate it:
   python3 -m venv .venv && source .venv/bin/activate

3. Upgrade pip and install all dependencies:
   pip install -U pip && pip install -r requirements.txt

4. (Optional) Install Playwright Chromium for Baidu/Zhihu/XHS source providers:
   playwright install chromium

5. Copy the environment template:
   cp .env.example .env

6. Ask me for my OPENAI_API_KEY and OPENAI_BASE_URL, then write them into .env.
   If I also have a TAVILY_API_KEY or GITHUB_TOKEN, write those too.

7. Run the self-check to verify everything is working:
   python3 langskills_cli.py self-check --skip-remote

8. If self-check passes, run a quick smoke test — search the built-in library:
   python3 langskills_cli.py skill-search "machine learning" --top 3

Done. Report the results of steps 7 and 8.
```

---

## 🦞 OpenClaw Integration

LangSkills is available as an [OpenClaw](https://github.com/nicobailon/openclaw) skill — giving any OpenClaw-powered agent access to 101K+ evidence-backed skills.

**Install from Claw Hub** (coming soon):

```bash
clawhub install langskills-search
```

**Manual install** — save the block below as `~/.openclaw/skills/langskills-search/SKILL.md`:

````markdown
---
name: langskills-search
version: 0.1.0
description: Search 101K evidence-backed skills from 62K+ papers & 23K+ tech sources
author: LabRAI
tags: [research, skills, knowledge-base, search, evidence]
requires:
  bins: ["python3"]
metadata: {"source": "https://github.com/LabRAI/LangSkills", "license": "MIT", "min_python": "3.10"}
---

# LangSkills Search

Search 101,330 evidence-backed skills covering 62K+ research papers and 23K+ coding/tech sources — all offline via FTS5 SQLite.

## When to Use

- User asks for best practices, how-tos, or techniques on a technical topic
- You need evidence-backed knowledge (not LLM-generated guesses)
- Research tasks that benefit from academic or real-world source citations

## First-Time Setup

```bash
git clone https://github.com/LabRAI/LangSkills.git && cd LangSkills
pip install -r requirements.txt
# Install all bundles (~1 GB) or pick a domain:
python3 langskills_cli.py bundle-install --auto
```

## Search Command

```bash
python3 langskills_cli.py skill-search "<query>" [options]
python3 langskills_cli.py skill-search --domains
python3 langskills_cli.py skill-search --kinds
```

### Parameters

| Flag | Description | Default |
|:---|:---|:---|
| `--top N` | Number of results | 5 |
| `--domains` | List available domains and exit | off |
| `--kinds` | List available skill kinds and exit | off |
| `--domain <d>` | Filter by domain | all |
| `--show-path` | Show local `skill.md` path for each result | off |
| `--min-score N` | Minimum quality score (0-5) | 0 |
| `--content` | Include full skill body | off |
| `--format markdown` | Output as Markdown | text |

### Example

```bash
python3 langskills_cli.py skill-search "CRISPR gene editing" --domain research --top 3 --content --format markdown
python3 langskills_cli.py skill-search "kubernetes networking" --top 5 --show-path
```

## Reading Results

Each result includes: **title**, **domain**, **quality score** (0-5), **source URL**, and optionally the full skill body. Higher scores indicate stronger evidence chains.

## Available Domains

`linux` · `web` · `programming` · `devtools` · `security` · `cloud` · `data` · `ml` · `llm` · `observability` · `research-arxiv` · `research-plos-*` · `research-elife` · `research-other`

## Tips

- Use `--content --format markdown` to get copy-paste-ready skill text
- Combine `--domain` with `--min-score 4.0` for high-quality results
- Run `bundle-install --auto` in a project directory to install only relevant domains
````

---

## 🖥️ CLI Reference

> All commands: `python3 langskills_cli.py <command>`

<details>
<summary>⚡ <b>Core Commands</b></summary>
<br/>

| Command | What It Does |
|:---|:---|
| `capture "<topic>@N"` | Full pipeline: discover → fetch → generate → validate `N` skills |
| `skill-search "<query>"` | Search the local skill library (FTS5 full-text) |
| `search <engine> "<query>"` | Search URLs via a specific provider (tavily / github / baidu) |
| `validate --strict --package` | Run quality gates on generated skills |
| `improve <run-dir>` | Re-improve an existing capture run in place |

</details>

<details>
<summary>🔄 <b>Batch Pipelines</b></summary>
<br/>

| Command | What It Does |
|:---|:---|
| `runner` | Resumable background worker: queue → generate → publish |
| `arxiv-pipeline` | arXiv papers: discover → download PDF → generate skills |
| `journal-pipeline` | Journals: crawl PMC / PLOS / Nature / eLife → generate |
| `topics-capture <file>` | Enqueue topics from a text file into the persistent queue |
| `queue-seed` | Auto-seed the queue from config-defined topic lists |

</details>

<details>
<summary>📚 <b>Library Management</b></summary>
<br/>

| Command | What It Does |
|:---|:---|
| `bundle-install --domain <d>` | Download a pre-built SQLite bundle from GitHub Releases |
| `bundle-install --auto` | Auto-detect project type and install matching bundles |
| `build-bundle --split-by-domain` | Build self-contained SQLite bundles from skills/ |
| `build-site` | Generate `dist/index.json` + `dist/index.html` |
| `reindex-skills` | Rebuild `skills/index.json` from the by-skill directory |

</details>

<details>
<summary>🔧 <b>More: Utilities & Diagnostics</b></summary>
<br/>

| Command | What It Does |
|:---|:---|
| `self-check --skip-remote` | Local environment sanity check |
| `auth zhihu\|xhs` | Interactive Playwright login helper |
| `sources-audit` | Audit source providers (speed, auth, failures) |
| `auto-pr` | Create a commit/branch and optionally push + open a PR |
| `queue-stats` | Show queue counts by stage / status / source |
| `queue-watch` | Live queue stats dashboard (rich) |
| `queue-gc` | Reclaim expired leases |
| `repo-index` | Traverse + statically index repo into captures |
| `repo-query "<query>"` | Evidence-backed search over symbol index |
| `backfill-package-v2` | Generate missing package v2 files |
| `backfill-verification` | Ensure Verification sections include fenced code |
| `backfill-sources` | Backfill `sources/by-id` from existing artifacts |

</details>

---

## ⚙️ Configuration

Master config: **`config/langskills.json`** — domains, URL rules, quality gates, license policy.

<details>
<summary>🤖 <b>LLM & API Keys</b></summary>
<br/>

| Variable | Required | Description |
|:---|:---:|:---|
| `OPENAI_API_KEY` | **Yes** | OpenAI-compatible API key for skill generation |
| `OPENAI_BASE_URL` | **Yes** | API base URL (e.g., `https://api.openai.com/v1`) |
| `OPENAI_MODEL` | No | Model name (default: `gpt-4.1-mini`) |
| `LLM_PROVIDER` | No | `openai` (default) or `ollama` |
| `OLLAMA_BASE_URL` | No | Ollama server URL |
| `OLLAMA_MODEL` | No | Ollama model name |

</details>

<details>
<summary>🔍 <b>Search & Data Sources</b></summary>
<br/>

| Variable | Required | Description |
|:---|:---:|:---|
| `TAVILY_API_KEY` | No | Required for Tavily web search |
| `GITHUB_TOKEN` | No | Recommended for GitHub search (avoids rate limits) |
| `LANGSKILLS_WEB_SEARCH_PROVIDERS` | No | Comma-separated list (default: `tavily,baidu,zhihu,xhs`) |

</details>

<details>
<summary>🎭 <b>Playwright & Auth (optional)</b></summary>
<br/>

| Variable | Description |
|:---|:---|
| `LANGSKILLS_PLAYWRIGHT_HEADLESS` | `0` (visible browser) or `1` (headless, default) |
| `LANGSKILLS_PLAYWRIGHT_USER_DATA_DIR` | Custom Chromium user data directory |
| `LANGSKILLS_PLAYWRIGHT_AUTH_DIR` | Auth state dir (default: `var/runs/playwright_auth`) |
| `LANGSKILLS_ZHIHU_LOGIN_TYPE` | `qrcode` or `cookie` |
| `LANGSKILLS_ZHIHU_COOKIES` | Zhihu cookie string (when login type = `cookie`) |
| `LANGSKILLS_XHS_LOGIN_TYPE` | `qrcode`, `cookie`, or `phone` |
| `LANGSKILLS_XHS_COOKIES` | XHS cookie string (when login type = `cookie`) |

> Zhihu and XHS support is limited due to platform restrictions; full coverage in a future release.

</details>

---

## 📁 Project Structure

<details>
<summary>🎯 <b>Core System</b></summary>
<br/>

| Module | Description |
|:---|:---|
| `langskills_cli.py` | CLI entry point (auto-detects venv) |
| `core/cli.py` | All CLI commands & arg parsing |
| `core/config.py` | Configuration management |
| `core/search.py` | Multi-provider search orchestration |
| `core/domain_config.py` | Domain rules & classification |
| `core/detect_project.py` | Auto-detect project type |

</details>

<details>
<summary>🤖 <b>LLM Backends (<code>core/llm/</code>)</b></summary>
<br/>

| Module | Description |
|:---|:---|
| `openai_client.py` | OpenAI-compatible client |
| `ollama_client.py` | Ollama local model client |
| `factory.py` | Client factory & routing |
| `base.py` | Base LLM interface |

</details>

<details>
<summary>🌐 <b>Source Providers (<code>core/sources/</code>)</b></summary>
<br/>

| Module | Description |
|:---|:---|
| `web_search.py` | Tavily web search |
| `github.py` | GitHub repository search |
| `stackoverflow.py` | StackOverflow Q&A |
| `arxiv.py` | arXiv paper fetcher |
| `baidu.py` | Baidu search (Playwright) |
| `zhihu.py` | Zhihu (Playwright) |
| `xhs.py` | XHS / RedNote (Playwright) |
| `journals/` | PMC, PLOS, Nature, eLife |

</details>

<details>
<summary>📦 <b>Data & Output</b></summary>
<br/>

| Directory | Description |
|:---|:---|
| `skills/by-skill/` | Published skills by domain/topic |
| `skills/by-source/` | Published skills by source |
| `dist/` | Pre-built SQLite bundles + site |
| `captures/` | Per-run capture artifacts |
| `config/` | Master config + schedules |

</details>

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Open an [issue](https://github.com/LabRAI/LangSkills/issues) to discuss the proposed change
2. Fork the repository and create your feature branch
3. Submit a pull request with a clear description

## 📄 License

This project is licensed under the [MIT License](LICENSE).

Copyright (c) 2026 [Responsible AI (RAI) Lab](https://github.com/LabRAI) @ Florida State University

---


## 🙏 Credits

- **Authors:** [Tianming Sha](https://shatianming5.github.io/) (Stony Brook University), [Dr. Yue Zhao](https://viterbi-web.usc.edu/~yzhao010/) (University of Southern California), [Dr. Lichao Sun](https://lichao-sun.github.io/) (Lehigh University), [Dr. Yushun Dong](https://yushundong.github.io/) (Florida State University)
- **Design:** Modular pipeline architecture with multi-source intelligence, built for extensibility and offline-first search
- **Skills:** 101,330 evidence-backed skills generated from 62K+ papers and 23K+ tech sources via LLM-powered quality gates
- **Sources:** Every skill traces to real web pages, academic papers, or code repositories (arXiv, PMC, PLOS, Nature, eLife, GitHub, etc.)

---

<p align="center">
  <a href="https://star-history.com/#LabRAI/LangSkills&Date">
    <img src="https://api.star-history.com/svg?repos=LabRAI/LangSkills&type=Date" width="600" alt="Star History" />
  </a>
</p>
