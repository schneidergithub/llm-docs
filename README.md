# LLM Reference Corpus (Public)

A public, contributor-friendly knowledge base designed to be:
- **Human-maintained** (Markdown sources under `docs/`)
- **Machine-ingestible** (deterministic corpus export under `dist/` produced by CI)
- **Benchmarkable** (versioned personas + question sets under `benchmarks/`)

This repository is optimized for **high accuracy** and **reproducible evaluation** across different LLMs and personas.

## Key principles

1. **Stable document IDs**  
   Every document has a permanent `id` in YAML front matter. IDs are never reused.

2. **Deterministic corpus snapshots**  
   Benchmarks run against a tagged corpus export (`corpus-vYYYY.MM.patch`).  
   Do not benchmark against an arbitrary commit on `main`.

3. **Strict metadata**  
   Documents must validate against the front matter schema and curated taxonomy.

4. **No raw HTML in docs**  
   Raw HTML is blocked to reduce hidden behavior and injection risk.

## Repository structure

- `docs/` — source Markdown
  - `business/`, `software-development/`, `shared/`
  - `_drafts/` (excluded from exports)
  - `_deprecated/` (excluded from exports)
  - `_templates/` (excluded from exports)
- `schema/` — taxonomy + JSON schema for front matter
- `tools/` — validators and corpus builder
- `dist/` — generated corpus artifacts (built in CI; not required to commit)
- `benchmarks/` — personas, question sets, rubric, and harness scaffold

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r tools/requirements.txt

python tools/validate_docs.py
python tools/build_corpus.py --corpus-version dev-local
```

## Creating a corpus release (reproducible snapshot)

1. Merge changes to `main`
2. Create a tag: `corpus-vYYYY.MM.patch`
3. Push the tag — CI will:
   - validate documents
   - build `dist/corpus.jsonl`, `dist/index.json`, `dist/manifest.json`
   - attach artifacts to the GitHub release

## Dual licensing

- **Code**: Apache-2.0 (`LICENSE-CODE`)
- **Documentation/content**: CC BY 4.0 (`LICENSE-CONTENT`)
