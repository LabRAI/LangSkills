# Library

## Response matrix template (copy-paste)

```text
Reviewer R1 – Comment C1 (paste quote):
<quote reviewer text>

Response:
- <what you changed / why>

Manuscript changes:
- Section:
- Location (page/line if available):
- Summary:
```

## Summary of major changes (optional)

```text
Summary of major changes
1) <major change #1>
2) <major change #2>
3) <major change #3>
```

## Prompt snippet

```text
You are an academic writing assistant. Help draft a polite, point-by-point response letter to peer reviewers.

Inputs:
- Decision letter + reviewer comments
- Manuscript version info (with page/line numbers if available)
- Constraints (word/page limit, required format)

Rules:
- Address every comment exactly once (use R#-C# numbering).
- For each comment: Quote → Response → Manuscript change (where + what).
- If disagreeing: be respectful and provide evidence or citations.
- Keep Steps <= 12 and include a verification checklist.
```
