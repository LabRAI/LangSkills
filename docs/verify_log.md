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
