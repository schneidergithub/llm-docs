# Security Policy

## Reporting a vulnerability

If you believe you have found a security issue in the build tooling or workflows:
- Do not open a public issue with exploit details.
- Use GitHub's private vulnerability reporting if enabled, or contact maintainers via the repository's listed security contact.

## Threat model notes (public contributions)

Because this is a public corpus used by LLM pipelines:
- Raw HTML is blocked in documentation sources.
- Corpus exports are generated deterministically from validated sources.
- Maintain a strict separation between reference text and executable instructions.
