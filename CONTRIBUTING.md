# Contributing

## Requirements (strict)

All Markdown files under `docs/` (except `docs/_templates/`) MUST:

1. Start with YAML front matter bounded by `---`.
2. Include required fields: `id`, `title`, `domain`, `status`, `audience`, `tags`, `last_reviewed`.
3. Use values allowed by `schema/taxonomy.json`.
4. Contain **no raw HTML** (HTML tags, comments, or blocks).
5. Use a unique `id` that is never reused.

## Document metadata (front matter)

Example:

```markdown
---
id: swd.api.rate_limiting.001
title: Rate limiting patterns
domain: software-development
status: stable
audience: practitioner
tags: [api, resilience, throttling]
last_reviewed: 2026-02-10
---

# Rate limiting patterns
...
```

### Domains
- `business`
- `software-development`
- `shared`

### Status
- `draft` (allowed but excluded if placed under `docs/_drafts/`)
- `stable` (included in corpus exports)
- `deprecated` (excluded from corpus exports; use `superseded_by`)

### Curated tags (strict)
Tags must be from `schema/taxonomy.json` (`allowed_tags`).

## Deprecation policy (accuracy-preserving)

If a document is replaced:
- Keep the old document (do not delete history).
- Mark it as `status: deprecated` and add `superseded_by: <new_doc_id>`.
- Move it to `docs/_deprecated/` (recommended).

Deprecated docs are **excluded** from the exported corpus.

## Validation

Run locally before opening a PR:

```bash
pip install -r tools/requirements.txt
python tools/validate_docs.py
```

CI enforces validation on every PR.

## Style guidance (to improve LLM use)

- Prefer explicit headings (H2/H3) and short sections.
- Avoid ambiguous pronouns; name the subject directly.
- State assumptions and constraints.
- When making factual claims, include scope, conditions, and (if applicable) references to standards by name.
