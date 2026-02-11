---
id: swd.api.versioning.001
title: API versioning strategy
domain: software-development
status: stable
audience: practitioner
tags: [api, architecture, risk]
last_reviewed: 2026-02-10
summary: Practical versioning options and defaults for long-lived APIs.
---

# API versioning strategy

## Default strategy

Prefer additive, backward-compatible changes under a single major version when possible. Treat breaking changes as exceptional events requiring explicit migration planning.

## Common approaches

- **URI versioning** (e.g., `/v1/...`): simple and visible, but can encourage unnecessary proliferation of versions.
- **Header-based versioning**: keeps URLs stable, but requires stronger client tooling and operational discipline.

## Breaking change handling

When a breaking change is necessary:
- publish a new major version
- maintain both versions for a defined deprecation window
- provide a migration guide and a compatibility matrix
