# linux-bot: {{pr_title}}

## Summary
- Domain: **linux**
- Generated: {{generated_count}}
- Updated: {{updated_count}}
- Deprecated/Removed: {{deprecated_count}}
- Batch ID: {{batch_id}}
- Run URL: {{run_url}}

## Topics included
> 请按本表展示本次涉及的技能（生成/更新都列出）。

| ID | Title | Risk | Level | Action | Notes |
|---|---|---:|---:|---:|---|
{{topics_table}}

## Sources (auto-collected)
- Total sources: {{sources_total}}

**Source types**
- man pages: {{sources_man}}
- official docs: {{sources_official}}
- distro docs: {{sources_distro}}
- other: {{sources_other}}

**Top domains**
{{top_domains}}

## Validator results
- Format / required sections: {{check_format}}
- Steps <= 12: {{check_steps_limit}} (violations: {{violations_steps}})
- Sources >= 3: {{check_sources_min}} (violations: {{violations_sources}})
- Key-step citations present: {{check_keystep_citations}}
- Link check: {{check_links}} (broken: {{broken_links_count}})
- Duplication check: {{check_duplicates}} (candidates: {{dup_candidates_count}})
- Safety keyword scan: {{check_safety_scan}} (flags: {{safety_flags_count}})

## Safety & risk notes
**High risk skills (require explicit reviewer attention)**
{{high_risk_list}}

**Medium risk skills**
{{medium_risk_list}}

**Low risk skills**
{{low_risk_list}}

> Rule of thumb (must hold for high-risk skills):
> - clear warning in `Safety & Risk`
> - safe preview step (dry-run / echo / show plan)
> - explicit confirmation requirement for irreversible actions
> - verification step present
> - troubleshooting pointer present

## Reviewer checklist (DoD)
- [ ] Each `skill.md` includes: Goal, When to use, When NOT to use, Prerequisites, Steps (<=12), Verification, Safety & Risk, Troubleshooting pointer, Sources (>=3)
- [ ] Key steps (commands/parameters) are traceable to Sources (step-level citations for critical steps)
- [ ] No prohibited content per `SAFETY.md`
- [ ] No large verbatim copy-paste from sources
- [ ] Link-check passes or broken links are removed/justified and not used as key evidence
- [ ] For high-risk skills: strong warnings + confirmation language present
- [ ] `metadata.yaml` includes at least: id, title, domain, level, risk_level, owners, last_verified

## How to reproduce locally
```bash
# Example (adjust to your tooling)
node scripts/validate-skills.js

# Render topics_table (rows)
node scripts/render-topics-table.js --domain linux --out topics_table.md
```

## Notes to reviewers

{{notes}}
