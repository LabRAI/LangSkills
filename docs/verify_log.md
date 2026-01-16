# Verify Log

## Missing-001
- 2026-01-15: `rm -rf /tmp/skill-llm-out && node agents/run_local.js --domain linux --topic filesystem/find-files --out /tmp/skill-llm-out --overwrite --capture`
  - Result: PASS
  - Notes: Capture succeeded and generated non-TODO skill payload.
  - Artifacts: `/tmp/skill-llm-out`
- 2026-01-15: `rm -rf /tmp/skill-llm-out && node agents/run_local.js --domain linux --topic filesystem/find-files --out /tmp/skill-llm-out --overwrite --capture --llm-provider mock --llm-fixture agents/llm/fixtures/rewrite.json`
  - Result: PASS
  - Notes: Mock LLM rewrite completed (offline provider).
  - Artifacts: `/tmp/skill-llm-out`
- 2026-01-15: `node scripts/validate-skills.js --skills-root /tmp/skill-llm-out --strict`
  - Result: PASS
  - Notes: Strict gate passed on generated skill.
  - Artifacts: (n/a)

## Missing-002
- 2026-01-15: `node scripts/validate-skills.js --strict`
  - Result: PASS
  - Notes: Strict gate enforces License fields + source_policy checks.
  - Artifacts: (n/a)
- 2026-01-15: `node scripts/validate-skills.js --skills-root /tmp/skill-llm-out --strict --require-no-verbatim-copy --cache-dir .cache/web`
  - Result: PASS
  - Notes: Verbatim-copy audit ran using `.cache/web` fetch cache.
  - Artifacts: `/tmp/skill-llm-out`, `.cache/web`
- 2026-01-15: `node scripts/self-check.js --with-capture --skip-remote`
  - Result: PASS
  - Notes: End-to-end capture smoke includes verbatim-copy audit.
  - Artifacts: (see command output temp dirs)

## Missing-003
- 2026-01-15: `rm -rf runs/linux-runner-demo /tmp/runner-out && node agents/runner/run.js --domain linux --out /tmp/runner-out --run-id linux-runner-demo --max-topics 2`
  - Result: PASS
  - Notes: First pass created `runs/linux-runner-demo/state.json` with cursor advanced.
  - Artifacts: `runs/linux-runner-demo/state.json`, `/tmp/runner-out`
- 2026-01-15: `node agents/runner/run.js --domain linux --out /tmp/runner-out --run-id linux-runner-demo --max-topics 2`
  - Result: PASS
  - Notes: Resume continued from previous cursor (no restart).
  - Artifacts: `runs/linux-runner-demo/state.json`, `/tmp/runner-out`
- 2026-01-15: `rm -rf runs/linux-runner-loop-demo /tmp/runner-loop-out && node agents/runner/run.js --domain linux --topic filesystem/find-files --out /tmp/runner-loop-out --run-id linux-runner-loop-demo --loop --max-cycles 2`
  - Result: PASS
  - Notes: Loop mode iterated across cycles (bounded by `--max-cycles` for test).
  - Artifacts: `runs/linux-runner-loop-demo/state.json`, `/tmp/runner-loop-out`

## Missing-004
- 2026-01-15: `node scripts/self-check.js --skip-remote`
  - Result: PASS
  - Notes: Includes `git-automation` dry-run + branch push in a temp repo + bare remote.
  - Artifacts: (see command output temp dirs)

## Missing-005
- 2026-01-15: `rg -n "^seeds:|^\\s+- https?://" agents/configs/*.yaml`
  - Result: PASS
  - Notes: Confirmed each domain config declares `seeds` as URL list.
  - Artifacts: `agents/configs/*.yaml`
- 2026-01-15: `rm -rf /tmp/skill-verify-runs /tmp/skill-verify-cache && node agents/crawler/run.js --domain linux --runs-dir /tmp/skill-verify-runs --run-id verify-linux-config-seeds --cache-dir /tmp/skill-verify-cache --max-pages 1 --max-depth 0`
  - Result: PASS
  - Notes: Crawler successfully read `seeds` from config and wrote `crawl_state.json` + `crawl_log.jsonl`.
  - Artifacts: `/tmp/skill-verify-runs/verify-linux-config-seeds/crawl_state.json`, `/tmp/skill-verify-runs/verify-linux-config-seeds/crawl_log.jsonl`, `/tmp/skill-verify-cache`
- 2026-01-15: `node scripts/self-check.js --skip-remote`
  - Result: PASS
  - Notes: End-to-end smoke includes crawler discovery+dedupe+enqueue (local seed + allowlist block) and site build pipeline.
  - Artifacts: (see command output temp dirs)

## Missing-006
- 2026-01-15: `node agents/orchestrator/run.js --domain integrations --run-id integrations-demo --crawl-max-pages 1 --extract-max-docs 1`
  - Result: PASS
  - Notes: Orchestrator ran crawler+extractor for integrations and wrote state/metrics.
  - Artifacts: `runs/integrations-demo/crawl_state.json`, `runs/integrations-demo/candidates.jsonl`, `runs/integrations-demo/metrics.json`

## Missing-007
- 2026-01-16: `node agents/orchestrator/run.js --domain linux --run-id tier0-ingest-demo-2 --crawl-max-pages 1 --crawl-max-depth 0 --extract-max-docs 0 --generate-max-topics 0`
  - Result: PASS
  - Notes: Tier0 `github_repo` ingest produced `repo_state.json` + `repo_docs.jsonl` (246 files across 4 upstream repos); include_globs enforced.
  - Artifacts: `runs/tier0-ingest-demo-2/repo_state.json`, `runs/tier0-ingest-demo-2/repo_docs.jsonl`, `runs/tier0-ingest-demo-2/candidates.jsonl`

## Missing-008
- 2026-01-16: `node scripts/build-site.js --out website/dist`
  - Result: PASS
  - Notes: `Skills indexed: 2050` (repo skills_count >= 2000).
  - Artifacts: `website/dist/index.json`
- 2026-01-16: `node scripts/validate-skills.js --strict --fail-on-license-review`
  - Result: PASS
  - Notes: Strict gate passed on 2050 skills (bronze `License: unknown` still warns).
  - Artifacts: (n/a)
- 2026-01-16: `node eval/harness/run.js --tasks eval/tasks/linux/smoke.json --out eval/reports/latest/report.json --out-md eval/reports/latest/report.md --fail-on-stale-gold`
  - Result: PASS
  - Notes: Local eval report generated; Release publishing requires a GitHub Actions run of `eval.yml`.
  - Artifacts: `eval/reports/latest/report.json`, `eval/reports/latest/report.md`

## Amb-002
- 2026-01-15: `node scripts/validate-skills.js --strict`
  - Result: PASS
  - Notes: License policy loaded from `scripts/license-policy.json`; denied licenses fail, review licenses warn.
  - Artifacts: (n/a)

## Milestones (M0/M1/M2)
- 2026-01-16: `node scripts/self-check.js --m0 --m1 --m2 --skip-remote`
  - Result: PASS
  - Notes: Single-run offline milestone smoke; includes `validate-skills --strict --fail-on-license-review` gate.
  - Artifacts: (see stdout for temp dirs and outputs)
- 2026-01-16: `node scripts/self-check.js --m0 --with-capture --skip-remote`
  - Result: PASS
  - Notes: Covers generator/capture/validator/site/cli/plugin/git/create-pr (remote Pages skipped).
  - Artifacts: `website/dist` (plus OS temp dirs printed in stdout)
- 2026-01-16: `node scripts/self-check.js --m1`
  - Result: PASS
  - Notes: Covers M0 + eval + lifecycle + pr-score + 2000-scale synthetic skills (offline default).
  - Artifacts: (see stdout for temp eval/lifecycle/pr-score outputs)
- 2026-01-16: `node scripts/self-check.js --m2`
  - Result: PASS
  - Notes: Covers M1 + 100k-scale synthetic index generation (metadata-only).
  - Artifacts: `website/dist/index.json` (plus OS temp dirs printed in stdout)
