#!/usr/bin/env python3
"""
Validate documentation sources under docs/ for:
- required YAML front matter
- schema compliance
- taxonomy enums and curated tags
- unique doc IDs
- no raw HTML outside code fences
- basic internal link resolution

Exit code:
- 0 if valid
- 1 if any errors
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple, Iterable, Optional

import yaml
from jsonschema import Draft202012Validator

RE_FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
RE_MD_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
RE_HTML_TAG = re.compile(r"<[A-Za-z!/][^>]*>")
RE_HTML_COMMENT = re.compile(r"<!--")

EXCLUDED_DIRS = {"_templates"}  # validated but excluded from corpus build by build tool


@dataclass(frozen=True)
class Doc:
    path: Path
    front_matter: Dict
    body: str


def iter_markdown_files(docs_root: Path) -> Iterable[Path]:
    for p in sorted(docs_root.rglob("*.md")):
        if any(part.startswith(".") for part in p.parts):
            continue
        yield p


def split_code_fence_regions(text: str) -> List[Tuple[bool, str]]:
    """
    Split into regions: [(in_code_fence, segment_text), ...]
    Supports ``` and ~~~ fences. Deterministic, line-based.
    """
    out: List[Tuple[bool, str]] = []
    in_fence = False
    fence_delim: Optional[str] = None
    buf: List[str] = []

    def flush():
        nonlocal buf
        if buf:
            out.append((in_fence, "".join(buf)))
            buf = []

    for line in text.splitlines(keepends=True):
        m = re.match(r"^(\s*)(```|~~~)", line)
        if m:
            # toggle fence state
            flush()
            delim = m.group(2)
            if not in_fence:
                in_fence = True
                fence_delim = delim
            else:
                # only close if same delimiter type
                if fence_delim == delim:
                    in_fence = False
                    fence_delim = None
            out.append((True, line))  # fence line considered code region
        else:
            buf.append(line)

    flush()
    return out


def parse_doc(path: Path) -> Doc:
    raw = path.read_text(encoding="utf-8")
    m = RE_FRONT_MATTER.match(raw)
    if not m:
        raise ValueError("Missing YAML front matter bounded by '---' at top of file.")
    fm_text = m.group(1)
    try:
        fm = yaml.safe_load(fm_text) or {}
    except Exception as e:
        raise ValueError(f"Invalid YAML front matter: {e}") from e
    body = raw[m.end():]
    return Doc(path=path, front_matter=fm, body=body)


def load_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_no_html(doc: Doc) -> List[str]:
    errors: List[str] = []
    regions = split_code_fence_regions(doc.body)
    for in_code, seg in regions:
        if in_code:
            continue
        if RE_HTML_COMMENT.search(seg):
            errors.append("Raw HTML comments are not allowed.")
            break
        if RE_HTML_TAG.search(seg):
            errors.append("Raw HTML tags are not allowed.")
            break
    return errors


def validate_links(doc: Doc, repo_root: Path) -> List[str]:
    """
    Basic relative link checking for markdown links.
    - Skips external links (http/https/mailto)
    - Skips anchors-only links (#...)
    - For relative paths, checks existence relative to the doc directory.
    """
    errors: List[str] = []
    doc_dir = doc.path.parent
    regions = split_code_fence_regions(doc.body)

    def check_target(target: str) -> None:
        t = target.strip()
        if not t or t.startswith("#"):
            return
        if re.match(r"^(https?|mailto):", t):
            return
        # Remove optional title after space: (path "title")
        if " " in t:
            t = t.split(" ", 1)[0]
        # Remove anchor
        if "#" in t:
            t = t.split("#", 1)[0]
        if not t:
            return
        candidate = (doc_dir / t).resolve()
        try:
            candidate.relative_to(repo_root.resolve())
        except ValueError:
            errors.append(f"Link resolves outside repo: {target}")
            return
        if not candidate.exists():
            errors.append(f"Broken relative link: {target}")

    for in_code, seg in regions:
        if in_code:
            continue
        for link in RE_MD_LINK.findall(seg):
            check_target(link)

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".", help="Repository root")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    docs_root = repo_root / "docs"
    schema_root = repo_root / "schema"

    taxonomy = load_json(schema_root / "taxonomy.json")
    fm_schema = load_json(schema_root / "front_matter.schema.json")
    validator = Draft202012Validator(fm_schema)

    allowed_domains = set(taxonomy["domains"])
    allowed_status = set(taxonomy["status"])
    allowed_audience = set(taxonomy["audience"])
    tag_policy = taxonomy["tag_policy"]
    curated_tags = set(tag_policy.get("allowed_tags", []))

    errors: List[str] = []
    warnings: List[str] = []

    seen_ids: Dict[str, Path] = {}
    title_map: Dict[Tuple[str, str], List[Path]] = {}  # (domain, title) -> paths

    for md_path in iter_markdown_files(docs_root):
        # skip dot dirs and excluded dirs only for validation? We still validate templates for quality.
        if any(part in {".git", ".github"} for part in md_path.parts):
            continue

        try:
            doc = parse_doc(md_path)
        except Exception as e:
            errors.append(f"{md_path}: {e}")
            continue

        fm = doc.front_matter

        # JSON Schema validation
        schema_errors = sorted(validator.iter_errors(fm), key=lambda e: e.path)
        for se in schema_errors:
            errors.append(f"{md_path}: front matter schema error at {list(se.path)}: {se.message}")

        # Taxonomy enums
        domain = fm.get("domain")
        status = fm.get("status")
        audience = fm.get("audience")
        if domain not in allowed_domains:
            errors.append(f"{md_path}: domain '{domain}' not in taxonomy.domains")
        if status not in allowed_status:
            errors.append(f"{md_path}: status '{status}' not in taxonomy.status")
        if audience not in allowed_audience:
            errors.append(f"{md_path}: audience '{audience}' not in taxonomy.audience")

        # Curated tags
        tags = fm.get("tags") or []
        if tag_policy.get("mode") == "curated":
            for t in tags:
                if t not in curated_tags:
                    errors.append(f"{md_path}: tag '{t}' not in curated allowed_tags")

        # Unique ID
        doc_id = fm.get("id")
        if doc_id:
            if doc_id in seen_ids:
                errors.append(f"{md_path}: duplicate id '{doc_id}' also in {seen_ids[doc_id]}")
            else:
                seen_ids[doc_id] = md_path

        # last_reviewed not in future
        lr = fm.get("last_reviewed")
        if lr:
            try:
                y, m, d = (int(x) for x in lr.split("-"))
                lr_date = date(y, m, d)
                if lr_date > date.today():
                    errors.append(f"{md_path}: last_reviewed '{lr}' is in the future")
            except Exception:
                errors.append(f"{md_path}: last_reviewed '{lr}' is not a valid ISO date")

        # No raw HTML
        errors.extend([f"{md_path}: {msg}" for msg in validate_no_html(doc)])

        # Basic link checking
        errors.extend([f"{md_path}: {msg}" for msg in validate_links(doc, repo_root)])

        # Title collisions (warn)
        title = fm.get("title")
        if domain and title:
            key = (domain, title.strip().lower())
            title_map.setdefault(key, []).append(md_path)

        # H1 existence (warn)
        if not re.search(r"^\s*#\s+\S+", doc.body, flags=re.MULTILINE):
            warnings.append(f"{md_path}: no H1 heading found in body (recommended for clarity)")

    # report title collisions
    for (domain, title_lc), paths in title_map.items():
        if len(paths) > 1:
            warnings.append(f"Duplicate title in domain '{domain}': '{title_lc}' in {', '.join(str(p) for p in paths)}")

    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"  - {w}")
        print()

    if errors:
        print("ERRORS:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("OK: validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
