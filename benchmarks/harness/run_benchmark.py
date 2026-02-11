#!/usr/bin/env python3
"""
Minimal local benchmark runner for an LLM reference corpus.

Purpose
- Build deterministic prompts from:
  - a corpus export (dist/corpus.jsonl)
  - a persona prompt (benchmarks/personas/*.md)
  - a question set (benchmarks/questions/*/questions.jsonl)
- Optionally validate response citations against corpus chunk IDs and compute basic, non-semantic checks.

Design goals
- Deterministic: stable ordering, stable prompt assembly.
- High integrity: citation validation checks chunk_id existence in corpus export.
- No network calls and no model-provider coupling. Outputs prompts for any runner to consume.

Outputs (in out_dir/)
- run_manifest.json
- prompts.jsonl
- (optional) results.json and results.jsonl if --responses is provided
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

# Citation format enforced by personas in this repo:
# (doc_id, chunk_id)
RE_CITATION = re.compile(
    r"\(\s*"
    r"(?P<doc_id>(?:biz|swd|shr)\.[a-z0-9_\-\.]+\.[0-9]{3,})\s*,\s*"
    r"(?P<chunk_id>[^)]+?)"
    r"\s*\)"
)

JSON = Dict[str, object]


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def iter_jsonl(path: Path) -> Iterable[Tuple[int, JSON]]:
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield i, json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON on {path}:{i}: {e}") from e


def write_json(path: Path, obj: JSON) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: List[JSON]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


@dataclass(frozen=True)
class Question:
    qid: str
    corpus_version: str
    doc_refs: List[str]
    question: str


def load_questions(questions_path: Path) -> List[Question]:
    questions: List[Question] = []
    seen: Set[str] = set()

    for lineno, obj in iter_jsonl(questions_path):
        for field in ("id", "corpus_version", "doc_refs", "question"):
            if field not in obj:
                raise ValueError(f"Missing '{field}' in {questions_path}:{lineno}")

        qid = str(obj["id"]).strip()
        if not qid:
            raise ValueError(f"Empty id in {questions_path}:{lineno}")
        if qid in seen:
            raise ValueError(f"Duplicate question id '{qid}' in {questions_path}:{lineno}")
        seen.add(qid)

        corpus_version = str(obj["corpus_version"]).strip()
        doc_refs = obj["doc_refs"]
        if not isinstance(doc_refs, list) or not all(isinstance(x, str) and x.strip() for x in doc_refs):
            raise ValueError(f"doc_refs must be a non-empty list of strings in {questions_path}:{lineno}")
        question_text = str(obj["question"]).strip()
        if not question_text:
            raise ValueError(f"Empty question in {questions_path}:{lineno}")

        questions.append(
            Question(
                qid=qid,
                corpus_version=corpus_version,
                doc_refs=[x.strip() for x in doc_refs],
                question=question_text,
            )
        )

    return questions


@dataclass
class CorpusDoc:
    doc_id: str
    title: str
    chunks: List[Tuple[str, str]]  # (chunk_id, content)
    chunk_ids: Set[str]


def load_corpus_subset(corpus_path: Path, needed_doc_ids: Set[str]) -> Tuple[str, Dict[str, CorpusDoc]]:
    """
    Load only records whose doc_id is in needed_doc_ids.
    Returns (detected_corpus_version, docs_map).
    """
    docs: Dict[str, CorpusDoc] = {}
    detected_version: Optional[str] = None

    for lineno, rec in iter_jsonl(corpus_path):
        doc_id = str(rec.get("doc_id", "")).strip()
        if not doc_id:
            raise ValueError(f"Missing doc_id in {corpus_path}:{lineno}")

        if detected_version is None:
            detected_version = str(rec.get("corpus_version", "")).strip() or "unknown"

        if doc_id not in needed_doc_ids:
            continue

        chunk_id = str(rec.get("chunk_id", "")).strip()
        content = str(rec.get("content", "")).strip()
        title = str(rec.get("title", "")).strip()

        if not chunk_id:
            raise ValueError(f"Missing chunk_id in {corpus_path}:{lineno}")
        if not title:
            title = doc_id

        doc = docs.get(doc_id)
        if doc is None:
            doc = CorpusDoc(doc_id=doc_id, title=title, chunks=[], chunk_ids=set())
            docs[doc_id] = doc

        # Maintain deterministic order based on corpus export ordering; sort later as a safety net.
        doc.chunks.append((chunk_id, content))
        doc.chunk_ids.add(chunk_id)

    # Safety: normalize chunk ordering by chunk_id.
    for d in docs.values():
        d.chunks.sort(key=lambda t: t[0])

    return detected_version or "unknown", docs


def extract_required_sections_from_persona(persona_text: str) -> List[str]:
    """
    Heuristic: find "Output format:" and collect subsequent bullet items ("- ...")
    until a blank line or a non-bullet section begins.
    """
    lines = persona_text.splitlines()
    required: List[str] = []
    in_block = False

    for i, line in enumerate(lines):
        if not in_block and line.strip().lower() == "output format:":
            in_block = True
            continue
        if in_block:
            if not line.strip():
                break
            m = re.match(r"^\s*-\s+(.*)$", line)
            if m:
                item = m.group(1).strip()
                if item:
                    required.append(item)
            else:
                # Stop if the block no longer looks like bullets
                break

    return required


def build_prompt(
    persona_text: str,
    q: Question,
    corpus_docs: Dict[str, CorpusDoc],
    max_context_chars: int,
    max_chunks_per_doc: int,
) -> Tuple[str, List[str]]:
    """
    Assemble a deterministic prompt. Returns (prompt_text, included_chunk_ids).
    Includes up to max_chunks_per_doc chunks per doc_ref and respects max_context_chars.
    """
    included_chunk_ids: List[str] = []
    context_parts: List[str] = []

    remaining = max_context_chars

    # Deterministic doc ordering based on provided doc_refs order, but normalize duplicates.
    seen_docs: Set[str] = set()
    doc_refs_ordered: List[str] = []
    for d in q.doc_refs:
        if d not in seen_docs:
            seen_docs.add(d)
            doc_refs_ordered.append(d)

    for doc_id in doc_refs_ordered:
        doc = corpus_docs.get(doc_id)
        if doc is None:
            continue

        header = f"\n[DOC {doc.doc_id}] {doc.title}\n"
        if len(header) > remaining:
            break
        context_parts.append(header)
        remaining -= len(header)

        count = 0
        for chunk_id, content in doc.chunks:
            if count >= max_chunks_per_doc:
                break
            block = f"- ({chunk_id}) {content}\n"
            if len(block) > remaining:
                break
            context_parts.append(block)
            remaining -= len(block)
            included_chunk_ids.append(chunk_id)
            count += 1

    prompt = (
        persona_text.rstrip()
        + "\n\n"
        + "Rules:\n"
        + "- Answer using ONLY the provided corpus excerpts.\n"
        + "- For factual claims, cite sources in the form: (doc_id, chunk_id).\n"
        + "- If you must assume, label it explicitly as an assumption.\n\n"
        + f"Question ({q.qid}):\n{q.question}\n\n"
        + "Corpus excerpts:\n"
        + "".join(context_parts).rstrip()
        + "\n\nAnswer:\n"
    )
    return prompt, included_chunk_ids


def validate_response_citations(
    answer: str,
    corpus_docs: Dict[str, CorpusDoc],
) -> JSON:
    """
    Validates that citations match (doc_id, chunk_id) format and that chunk_id exists in corpus export.
    Does NOT validate semantic faithfulness.
    """
    citations = list(RE_CITATION.finditer(answer))
    total = len(citations)

    valid = 0
    invalid: List[Dict[str, str]] = []

    for m in citations:
        doc_id = m.group("doc_id").strip()
        chunk_id = m.group("chunk_id").strip()
        doc = corpus_docs.get(doc_id)
        if doc is None or chunk_id not in doc.chunk_ids:
            invalid.append({"doc_id": doc_id, "chunk_id": chunk_id})
        else:
            valid += 1

    return {
        "citations_total": total,
        "citations_valid": valid,
        "citations_invalid": invalid,
    }


def basic_structure_check(answer: str, required_sections: List[str]) -> JSON:
    """
    Checks whether each required section appears as a substring (case-insensitive).
    This is a minimal structural compliance test.
    """
    a = answer.lower()
    missing = []
    for s in required_sections:
        if s.lower() not in a:
            missing.append(s)
    present = len(required_sections) - len(missing)
    return {
        "required_sections": required_sections,
        "sections_present": present,
        "sections_missing": missing,
    }


def load_responses(responses_path: Path) -> Dict[str, str]:
    """
    Responses JSONL format (one line per answer):
    {"id": "<question_id>", "answer": "<model answer>", "model": "...", "params": {...}}
    Only id and answer are required.
    """
    responses: Dict[str, str] = {}
    for lineno, obj in iter_jsonl(responses_path):
        if "id" not in obj or "answer" not in obj:
            raise ValueError(f"Responses must include 'id' and 'answer' in {responses_path}:{lineno}")
        qid = str(obj["id"]).strip()
        ans = str(obj["answer"])
        if not qid:
            raise ValueError(f"Empty response id in {responses_path}:{lineno}")
        responses[qid] = ans
    return responses


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True, help="Path to dist/corpus.jsonl")
    parser.add_argument("--questions", required=True, help="Path to benchmarks/questions/*/questions.jsonl")
    parser.add_argument("--persona", required=True, help="Path to benchmarks/personas/*.md")
    parser.add_argument("--out", default=None, help="Output directory (default: benchmarks/runs/<utc timestamp>)")
    parser.add_argument("--responses", default=None, help="Optional responses.jsonl to validate citations and structure")
    parser.add_argument("--max-context-chars", type=int, default=12000, help="Max chars of excerpts to include per prompt")
    parser.add_argument("--max-chunks-per-doc", type=int, default=30, help="Max chunks per referenced doc to include")
    args = parser.parse_args()

    repo_root = Path(".").resolve()
    corpus_path = Path(args.corpus).resolve()
    questions_path = Path(args.questions).resolve()
    persona_path = Path(args.persona).resolve()

    out_dir = Path(args.out).resolve() if args.out else (repo_root / "benchmarks" / "runs" / _utc_now_iso().replace(":", ""))
    out_dir.mkdir(parents=True, exist_ok=True)

    persona_text = read_text(persona_path)
    persona_sha = sha256_file(persona_path)
    required_sections = extract_required_sections_from_persona(persona_text)

    questions = load_questions(questions_path)
    questions_sha = sha256_file(questions_path)

    needed_doc_ids: Set[str] = set()
    expected_versions: Set[str] = set()
    for q in questions:
        needed_doc_ids.update(q.doc_refs)
        expected_versions.add(q.corpus_version)

    detected_corpus_version, corpus_docs = load_corpus_subset(corpus_path, needed_doc_ids)

    # Integrity note: question files declare corpus_version; enforce if possible.
    # If question set contains multiple versions, record them, but do not fail.
    declared_versions = sorted(expected_versions)

    run_manifest: JSON = {
        "run_id": sha256_bytes(f"{_utc_now_iso()}|{os.getpid()}".encode("utf-8"))[:12],
        "timestamp_utc": _utc_now_iso(),
        "paths": {
            "corpus": str(corpus_path),
            "questions": str(questions_path),
            "persona": str(persona_path),
            "out_dir": str(out_dir),
        },
        "hashes": {
            "persona_sha256": persona_sha,
            "questions_sha256": questions_sha,
            "runner_sha256": sha256_file(Path(__file__).resolve()),
        },
        "corpus_version": {
            "detected_from_corpus": detected_corpus_version,
            "declared_in_questions": declared_versions,
        },
        "settings": {
            "max_context_chars": int(args.max_context_chars),
            "max_chunks_per_doc": int(args.max_chunks_per_doc),
            "citation_format": "(doc_id, chunk_id)",
        },
        "counts": {
            "questions": len(questions),
            "doc_refs_unique": len(needed_doc_ids),
            "docs_loaded": len(corpus_docs),
        },
        "warnings": [],
    }

    # Warn on doc_refs missing from corpus export.
    missing_docs = sorted(d for d in needed_doc_ids if d not in corpus_docs)
    if missing_docs:
        run_manifest["warnings"].append(
            {
                "type": "missing_docs_in_corpus",
                "message": "Some doc_refs were not found in the corpus export. Prompts will omit excerpts for these docs.",
                "doc_ids": missing_docs,
            }
        )

    prompts_out: List[JSON] = []
    for q in questions:
        prompt, included_chunk_ids = build_prompt(
            persona_text=persona_text,
            q=q,
            corpus_docs=corpus_docs,
            max_context_chars=args.max_context_chars,
            max_chunks_per_doc=args.max_chunks_per_doc,
        )
        prompts_out.append(
            {
                "id": q.qid,
                "corpus_version": q.corpus_version,
                "doc_refs": q.doc_refs,
                "persona_sha256": persona_sha,
                "questions_sha256": questions_sha,
                "prompt": prompt,
                "included_chunk_ids": included_chunk_ids,
            }
        )

    # Deterministic ordering by question id.
    prompts_out.sort(key=lambda r: str(r["id"]))

    write_json(out_dir / "run_manifest.json", run_manifest)
    write_jsonl(out_dir / "prompts.jsonl", prompts_out)

    if args.responses:
        responses_path = Path(args.responses).resolve()
        responses = load_responses(responses_path)
        results_rows: List[JSON] = []
        missing_answers: List[str] = []

        for p in prompts_out:
            qid = str(p["id"])
            ans = responses.get(qid)
            if ans is None:
                missing_answers.append(qid)
                continue

            citation_check = validate_response_citations(ans, corpus_docs)
            structure_check = basic_structure_check(ans, required_sections)

            results_rows.append(
                {
                    "id": qid,
                    "corpus_version": p["corpus_version"],
                    "persona_sha256": persona_sha,
                    "citations": citation_check,
                    "structure": structure_check,
                    "note": "These checks do not validate semantic faithfulness; they validate format and corpus reference integrity only.",
                }
            )

        summary = {
            "responses_file": str(responses_path),
            "responses_sha256": sha256_file(responses_path),
            "answered": len(results_rows),
            "missing_answers": missing_answers,
        }

        write_json(out_dir / "results.json", {"summary": summary, "rows": results_rows})
        write_jsonl(out_dir / "results.jsonl", results_rows)

    print(f"Wrote: {out_dir / 'run_manifest.json'}")
    print(f"Wrote: {out_dir / 'prompts.jsonl'}")
    if args.responses:
        print(f"Wrote: {out_dir / 'results.json'}")
        print(f"Wrote: {out_dir / 'results.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())