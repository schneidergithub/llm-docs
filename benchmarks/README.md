# Benchmarks

This directory contains benchmark artifacts used to evaluate model behavior against corpus snapshots.

## Layout

- `benchmarks/personas/` contains persona instructions.
- `benchmarks/questions/` contains versioned question sets and rubrics.
- `benchmarks/harness/` contains integration notes for benchmark runners.

## Reproducibility requirements

Record these fields for every benchmark run:

- corpus version
- question set version
- persona file hash/version
- harness git SHA
- model identifier and generation parameters
- retrieval configuration (if any)
