# LLM Reference Corpus (Public)

A public, contributor-friendly knowledge base designed to be:
- **Human-maintained** (Markdown sources under `docs/`)
- **Machine-ingestible** (deterministic corpus export artifacts under `dist/`)
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
  - `business/`, `software-development/`, `shared/` (domain sources)
  - `_drafts/` (excluded from exports)
  - `_deprecated/` (excluded from exports)
  - `_templates/` (excluded from exports)
- `schema/` — taxonomy + JSON schema for front matter
- `tools/` — validators and corpus builder
- `dist/` — tracked release artifacts
  - `dist/releases/<corpus-version>/` (immutable release snapshot)
  - `dist/latest/` (mirror of newest release)
- `benchmarks/` — personas, question sets, rubric, and harness scaffold
- `tests/` — unit tests for validation/build tooling

## Local development

```bash
make setup

make validate
make test
make build VERSION=dev-local
```

Local development builds are written to `dist/dev-local/<version>/` (gitignored).

Python 3.11 is the baseline runtime used by CI.

## Release process (reproducible snapshot)

Release automation runs from GitHub Actions workflow **`release-corpus`** via manual dispatch.

1. Trigger workflow: `.github/workflows/release.yml`
2. Provide `version` in format `corpus-vYYYY.MM.patch`
3. Workflow will:
   - validate docs
   - build corpus for that version
   - write snapshot to `dist/releases/<version>/`
   - refresh `dist/latest/`
   - commit artifacts to `main`
   - create annotated tag `<version>`
   - create GitHub Release with attached artifacts

## Dual licensing

- **Code**: Apache-2.0 (`LICENSE-CODE`)
- **Documentation/content**: CC BY 4.0 (`LICENSE-CONTENT`)
