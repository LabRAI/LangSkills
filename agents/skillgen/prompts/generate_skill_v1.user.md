Domain: {{DOMAIN}}
Run ID: {{RUN_ID}}
Skill ID: {{SKILL_ID}}
Suggested title: {{TITLE}}

Proposal (JSON):
{{PROPOSAL_JSON}}

Sources (JSON; 1-based index is the citation number):
{{SOURCES_JSON}}

Materials (text snippets extracted from sources; may be incomplete):
{{MATERIALS_TEXT}}

Task:
Generate ONE skill JSON that matches the schema in the system prompt, using the suggested title and sources.

Guidance:
- Keep commands safe: prefer read-only / dry-run first, then the write action (if any).
- Use citations: every step should end up with at least one cite.
- Prefer Chinese output for end-user facing text (title/bullets/steps) unless the topic is clearly API/English-only.

Return ONLY the JSON object.

