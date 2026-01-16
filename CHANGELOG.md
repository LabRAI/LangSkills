# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- (placeholder)

## [0.1.0-alpha] - 2026-01-15

- `skills/`: 50 skills（20 silver、5 gold；含可复现示例与来源绑定）
- `agents/`: runner + crawler/extractor/orchestrator + 本地 LLM provider（mock/ollama/openai）
- `scripts/validate-skills.js --strict`: 结构/引用/来源策略/License policy/重复检测/风险扫描（CI 门禁）
- `website/` + `cli/` + `plugin/`: 统一索引 `website/dist/index.json`，支持搜索与复制 `library.md`
- GitHub Actions: `ci` / `link-check` / `build-site` / `audit-capture` / `agent-generate`（自动提 PR）
