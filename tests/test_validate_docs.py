from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATE_SCRIPT = REPO_ROOT / "tools" / "validate_docs.py"
SCHEMA_DIR = REPO_ROOT / "schema"


def run_validate(repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATE_SCRIPT), "--repo-root", str(repo_root)],
        text=True,
        capture_output=True,
        check=False,
    )


class ValidateDocsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tmp.name)
        shutil.copytree(SCHEMA_DIR, self.repo_root / "schema")
        (self.repo_root / "docs").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_doc(self, relpath: str, content: str) -> Path:
        path = self.repo_root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dedent(content).lstrip(), encoding="utf-8")
        return path

    def test_accepts_valid_doc(self) -> None:
        self.write_doc(
            "docs/software-development/api/valid.md",
            """
            ---
            id: swd.api.valid.001
            title: Valid API doc
            domain: software-development
            status: stable
            audience: practitioner
            tags: [api, architecture]
            last_reviewed: "2026-02-10"
            summary: Valid document.
            ---

            # Valid API doc

            This document is valid.
            """,
        )

        result = run_validate(self.repo_root)

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

    def test_rejects_invalid_curated_tag(self) -> None:
        self.write_doc(
            "docs/software-development/api/bad-tag.md",
            """
            ---
            id: swd.api.bad_tag.001
            title: Invalid tag doc
            domain: software-development
            status: stable
            audience: practitioner
            tags: [not-allowed-tag]
            last_reviewed: "2026-02-10"
            summary: Invalid tag document.
            ---

            # Invalid tag doc

            Tag should fail validation.
            """,
        )

        result = run_validate(self.repo_root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("not in curated allowed_tags", result.stdout)

    def test_rejects_broken_relative_link(self) -> None:
        self.write_doc(
            "docs/shared/link-test.md",
            """
            ---
            id: shr.links.test.001
            title: Link test
            domain: shared
            status: stable
            audience: general
            tags: [governance]
            last_reviewed: "2026-02-10"
            summary: Link test document.
            ---

            # Link test

            Broken link: [missing](./does-not-exist.md)
            """,
        )

        result = run_validate(self.repo_root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("Broken relative link", result.stdout)

    def test_rejects_raw_html(self) -> None:
        self.write_doc(
            "docs/business/raw-html.md",
            """
            ---
            id: biz.html.test.001
            title: Raw HTML test
            domain: business
            status: stable
            audience: executive
            tags: [risk, strategy]
            last_reviewed: "2026-02-10"
            summary: Raw HTML validation test.
            ---

            # Raw HTML test

            <div>This should fail.</div>
            """,
        )

        result = run_validate(self.repo_root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("Raw HTML tags are not allowed", result.stdout)


if __name__ == "__main__":
    unittest.main()
