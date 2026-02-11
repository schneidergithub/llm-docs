from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = REPO_ROOT / "tools" / "build_corpus.py"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "chunk_id_regression"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_build(repo_root: Path, version: str, out_dir: str, *, build_timestamp: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["BUILD_TIMESTAMP_UTC"] = build_timestamp
    return subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            "--repo-root",
            str(repo_root),
            "--corpus-version",
            version,
            "--out-dir",
            out_dir,
        ],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


class BuildCorpusTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tmp.name)
        (self.repo_root / "docs").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_doc(self, relpath: str, content: str) -> Path:
        path = self.repo_root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dedent(content).lstrip(), encoding="utf-8")
        return path

    def test_excludes_unstable_and_special_directories(self) -> None:
        self.write_doc(
            "docs/business/stable.md",
            """
            ---
            id: biz.product.stable.001
            title: Stable business doc
            domain: business
            status: stable
            audience: investor
            tags: [product, finance]
            last_reviewed: "2026-02-10"
            summary: Stable content.
            ---

            # Stable business doc

            Included content.
            """,
        )
        self.write_doc(
            "docs/business/draft-status.md",
            """
            ---
            id: biz.product.draft_status.001
            title: Draft status doc
            domain: business
            status: draft
            audience: investor
            tags: [product]
            last_reviewed: "2026-02-10"
            summary: Draft status content.
            ---

            # Draft status doc

            Excluded by status.
            """,
        )
        self.write_doc(
            "docs/_drafts/ignored.md",
            """
            ---
            id: swd.api.ignored.001
            title: Ignored by drafts path
            domain: software-development
            status: stable
            audience: practitioner
            tags: [api]
            last_reviewed: "2026-02-10"
            summary: Excluded by directory.
            ---

            # Ignored by drafts path

            Excluded by directory.
            """,
        )
        self.write_doc(
            "docs/_deprecated/old.md",
            """
            ---
            id: shr.old.doc.001
            title: Deprecated path doc
            domain: shared
            status: stable
            audience: general
            tags: [governance]
            last_reviewed: "2026-02-10"
            summary: Excluded by directory.
            ---

            # Deprecated path doc

            Excluded by directory.
            """,
        )

        result = run_build(
            self.repo_root,
            version="corpus-v2026.02.1",
            out_dir="dist/out",
            build_timestamp="2026-02-11T00:00:00+00:00",
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

        index = json.loads((self.repo_root / "dist" / "out" / "index.json").read_text(encoding="utf-8"))
        ids = [entry["doc_id"] for entry in index]

        self.assertEqual(ids, ["biz.product.stable.001"])

    def test_fixture_chunk_ids_and_repeat_build_checksums_are_stable(self) -> None:
        fixture_docs = FIXTURE_ROOT / "docs"
        shutil.copytree(fixture_docs, self.repo_root / "docs", dirs_exist_ok=True)

        first = run_build(
            self.repo_root,
            version="corpus-v2026.02.2",
            out_dir="dist/first",
            build_timestamp="2026-02-11T00:00:00+00:00",
        )
        second = run_build(
            self.repo_root,
            version="corpus-v2026.02.2",
            out_dir="dist/second",
            build_timestamp="2026-02-11T00:00:00+00:00",
        )

        self.assertEqual(first.returncode, 0, msg=first.stdout + first.stderr)
        self.assertEqual(second.returncode, 0, msg=second.stdout + second.stderr)

        expected_chunk_ids = json.loads(
            (FIXTURE_ROOT / "expected_chunk_ids.json").read_text(encoding="utf-8")
        )

        corpus_first_lines = (self.repo_root / "dist" / "first" / "corpus.jsonl").read_text(encoding="utf-8").splitlines()
        actual_chunk_ids = [json.loads(line)["chunk_id"] for line in corpus_first_lines]

        self.assertEqual(actual_chunk_ids, expected_chunk_ids)

        first_out = self.repo_root / "dist" / "first"
        second_out = self.repo_root / "dist" / "second"

        for name in ("corpus.jsonl", "index.json", "manifest.json"):
            self.assertEqual(sha256_file(first_out / name), sha256_file(second_out / name))


if __name__ == "__main__":
    unittest.main()
