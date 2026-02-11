# Question Sets

Question sets are versioned under subdirectories such as `v1/`.

## Required files per version

- `questions.jsonl`: one benchmark question per line.
- `rubric.json`: scoring axes and scale definitions.

## Versioning policy

Create a new version directory when changing question semantics or rubric criteria in a non-backward-compatible way.
