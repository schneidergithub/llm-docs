# Governance

This repository is maintained by a small set of maintainers who ensure:
- schema/taxonomy integrity
- validation and build tooling reliability
- release tagging discipline for reproducible corpus snapshots
- consistency of contributor expectations and enforcement

## Roles

- **Maintainers**: approve changes to `schema/`, `tools/`, `benchmarks/`, and repository policies.
- **Domain maintainers**: review changes under their domain paths (e.g., `docs/business/`).

## Decision policy

- Content rules, schemas, and export behavior are treated as **compatibility surfaces**.
- Changes that alter IDs, export structure, or chunking rules require:
  - explicit changelog note
  - maintainer approval
  - (if breaking) a major version bump of the corpus export schema.

## Release policy

Corpus releases use workflow dispatch in `.github/workflows/release.yml` with version input `corpus-vYYYY.MM.patch`.
The workflow commits generated artifacts under `dist/releases/<version>/`, updates `dist/latest/`, creates the annotated tag, and publishes the release.

Benchmarks should record:
- corpus version
- question set version
- persona file hash/version
- harness git SHA
- model identifier and generation parameters
