#!/usr/bin/env python3
"""
Deterministically build a machine-ingestible corpus export from docs/.

Policies (strict):
- Curated taxonomy enforced (via validate_docs.py in CI)
- Exclude:
  - docs/_drafts/**
  - docs/_templates/**
  - docs/_deprecated/**
  - any doc with status != "stable" (including "deprecated" and "draft")
- Chunking:
  - primary: H2 sections (outside code fences)
  - each H2 section is further split into paragraph sub-chunks (outside code fences)
  - a "root" pseudo-H2 covers content before the first H2 (if any)
- Block HTML is enforced upstream by validator (not stripped here)

Outputs (in --out-dir):
- corpus.jsonl (one JSON object per chunk)
- index.json (doc-level index)
- manifest.json (build metadata)

Notes:
- Set BUILD_TIMESTAMP_UTC to make manifest timestamps deterministic across repeated builds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Iterable

import yaml

RE_FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

EXCLUDED_DIRS = {"_drafts", "_templates", "_deprecated"}

def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "root"

def split_code_fence_regions_lines(lines: List[str]) -> List[Tuple[bool, List[str]]]:
    """
    Split lines into regions: [(in_code_fence, lines), ...]
    Fence toggles on lines that start with ``` or ~~~ (optionally preceded by spaces).
    """
    out: List[Tuple[bool, List[str]]] = []
    in_fence = False
    fence_delim: Optional[str] = None
    buf: List[str] = []

    def flush():
        nonlocal buf
        if buf:
            out.append((in_fence, buf))
            buf = []

    for line in lines:
        m = re.match(r"^(\s*)(```|~~~)", line)
        if m:
            flush()
            delim = m.group(2)
            # fence line included as code region
            out.append((True, [line]))
            if not in_fence:
                in_fence = True
                fence_delim = delim
            else:
                if fence_delim == delim:
                    in_fence = False
                    fence_delim = None
        else:
            buf.append(line)

    flush()
    return out

@dataclass(frozen=True)
class Doc:
    path: Path
    fm: Dict
    body: str

def parse_doc(path: Path) -> Doc:
    raw = path.read_text(encoding="utf-8")
    m = RE_FRONT_MATTER.match(raw)
    if not m:
        raise ValueError("Missing YAML front matter.")
    fm = yaml.safe_load(m.group(1)) or {}
    body = raw[m.end():]
    return Doc(path=path, fm=fm, body=body)

def iter_docs(docs_root: Path) -> Iterable[Path]:
    for p in sorted(docs_root.rglob("*.md")):
        if any(part.startswith(".") for part in p.parts):
            continue
        if any(part in EXCLUDED_DIRS for part in p.parts):
            continue
        yield p

def extract_h1_title(body: str) -> Optional[str]:
    for line in body.splitlines():
        if re.match(r"^\s*#\s+\S+", line):
            return re.sub(r"^\s*#\s+", "", line).strip()
    return None

@dataclass
class Section:
    h2_title: str
    h2_slug: str
    lines: List[str]

def split_into_h2_sections(body: str) -> List[Section]:
    """
    Returns sections including a root pseudo-section for leading content before first H2.
    Only considers H2 headings outside fenced code blocks.
    """
    lines = body.splitlines(keepends=True)
    regions = split_code_fence_regions_lines(lines)

    sections: List[Section] = []
    current_title = "root"
    current_slug = "root"
    current_lines: List[str] = []

    def push():
        nonlocal current_lines, current_title, current_slug
        # Keep even empty root? we'll drop later if no content chunks.
        sections.append(Section(h2_title=current_title, h2_slug=current_slug, lines=current_lines))
        current_lines = []

    for in_code, reg_lines in regions:
        if in_code:
            current_lines.extend(reg_lines)
            continue

        for line in reg_lines:
            m = re.match(r"^\s*##\s+(.+?)\s*$", line)
            if m:
                # start new section
                push()
                current_title = m.group(1).strip()
                current_slug = slugify(current_title)
                current_lines = [line]
            else:
                current_lines.append(line)

    push()
    return sections

def split_section_into_paragraphs(lines: List[str]) -> List[str]:
    """
    Split section lines into paragraph blocks separated by blank lines,
    without splitting inside fenced code blocks.
    Returns list of paragraph strings.
    """
    regions = split_code_fence_regions_lines(lines)

    paragraphs: List[str] = []
    buf: List[str] = []

    def flush():
        nonlocal buf
        text = "".join(buf).strip()
        if text:
            paragraphs.append(text + "\n")  # normalize newline at end
        buf = []

    for in_code, reg_lines in regions:
        if in_code:
            buf.extend(reg_lines)
            continue

        for line in reg_lines:
            if line.strip() == "":
                flush()
            else:
                buf.append(line)

    flush()
    return paragraphs

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--corpus-version", default=None, help="Corpus version (e.g., corpus-v2026.02.0)")
    parser.add_argument("--out-dir", default="dist/dev-local", help="Output directory")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    docs_root = repo_root / "docs"
    out_dir = repo_root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    corpus_version = args.corpus_version or os.environ.get("GITHUB_REF_NAME") or "dev-unknown"
    git_sha = os.environ.get("GITHUB_SHA", "unknown")

    records: List[Dict] = []
    doc_index: List[Dict] = []

    for md_path in iter_docs(docs_root):
        doc = parse_doc(md_path)
        fm = doc.fm

        if fm.get("status") != "stable":
            continue  # strict: only stable included

        doc_id = fm["id"]
        title = fm["title"]
        domain = fm["domain"]
        tags = fm["tags"]
        audience = fm["audience"]
        status = fm["status"]

        h1 = extract_h1_title(doc.body) or title

        sections = split_into_h2_sections(doc.body)

        chunk_count = 0
        for sec in sections:
            paras = split_section_into_paragraphs(sec.lines)
            for i, para in enumerate(paras, start=1):
                chunk_id = f"{doc_id}#h2:{sec.h2_slug}#p:{i:04d}"
                rec = {
                    "corpus_version": corpus_version,
                    "doc_id": doc_id,
                    "chunk_id": chunk_id,
                    "source_path": str(md_path.relative_to(repo_root)),
                    "title": title,
                    "domain": domain,
                    "status": status,
                    "audience": audience,
                    "tags": tags,
                    "heading_path": [h1, sec.h2_title],
                    "content_type": "text/markdown",
                    "content": para,
                    "sha256": sha256_hex(para),
                    "char_count": len(para),
                }
                records.append(rec)
                chunk_count += 1

        full_hash = sha256_hex(doc.body)
        doc_index.append({
            "doc_id": doc_id,
            "title": title,
            "domain": domain,
            "status": status,
            "audience": audience,
            "tags": tags,
            "source_path": str(md_path.relative_to(repo_root)),
            "body_sha256": full_hash,
            "char_count": len(doc.body),
            "chunk_count": chunk_count,
        })

    # deterministic ordering
    doc_index.sort(key=lambda d: d["doc_id"])

    corpus_path = out_dir / "corpus.jsonl"
    with corpus_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    index_path = out_dir / "index.json"
    index_path.write_text(json.dumps(doc_index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    build_timestamp_utc = os.environ.get("BUILD_TIMESTAMP_UTC")
    if not build_timestamp_utc:
        build_timestamp_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")

    manifest = {
        "corpus_version": corpus_version,
        "git_sha": git_sha,
        "build_timestamp_utc": build_timestamp_utc,
        "included_statuses": ["stable"],
        "excluded_dirs": sorted(EXCLUDED_DIRS),
        "record_count": len(records),
        "doc_count": len(doc_index),
        "output": {
            "corpus_jsonl": str(corpus_path.relative_to(out_dir)),
            "index_json": str(index_path.relative_to(out_dir)),
        },
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"Built corpus: {manifest['doc_count']} docs, {manifest['record_count']} chunks -> {out_dir}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
