#!/usr/bin/env python3
"""Tests for scripts/scientific_artifact.py.

Covers the artifact lifecycle: init -> finalize -> verify -> approve, the
non-TTY approval refusal (the agent self-approval guard), and interop with
the linter's artifact checks.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import scientific_artifact as artifact
import scientific_code_lint as lint


def run_artifact(*argv: str) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = artifact.run(list(argv))
    return code, stdout.getvalue(), stderr.getvalue()


class FakeTty(io.StringIO):
    def isatty(self) -> bool:
        return True


class ArtifactToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.artifact_dir = self.root / "artifacts" / "ds" / "run_001"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def init_and_finalize(self) -> None:
        code, _, _ = run_artifact(
            "init", str(self.artifact_dir), "--contract", "TestDataset@1"
        )
        self.assertEqual(code, 0)
        (self.artifact_dir / "data.csv").write_text("id,x\n1,0.5\n", encoding="utf-8")
        (self.artifact_dir / "run.json").write_text(
            '{"run_id": "run_001", "status": "produced"}\n', encoding="utf-8"
        )
        code, out, _ = run_artifact("finalize", str(self.artifact_dir))
        self.assertEqual(code, 0, out)

    def read_manifest(self) -> dict:
        return json.loads(
            (self.artifact_dir / "manifest.json").read_text(encoding="utf-8")
        )

    def test_init_scaffolds_contract(self) -> None:
        code, _, _ = run_artifact(
            "init", str(self.artifact_dir), "--contract", "TestDataset@1"
        )
        self.assertEqual(code, 0)
        contract = (self.artifact_dir / "artifact_contract.toml").read_text(
            encoding="utf-8"
        )
        self.assertIn('name = "TestDataset"', contract)
        self.assertIn("version = 1", contract)

    def test_init_refuses_nonempty_directory(self) -> None:
        self.artifact_dir.mkdir(parents=True)
        (self.artifact_dir / "data.csv").write_text("x\n", encoding="utf-8")
        code, _, _ = run_artifact(
            "init", str(self.artifact_dir), "--contract", "TestDataset@1"
        )
        self.assertEqual(code, 2)

    def test_finalize_produces_verifying_manifest(self) -> None:
        self.init_and_finalize()
        code, out, _ = run_artifact("verify", str(self.artifact_dir))
        self.assertEqual(code, 0, out)
        manifest = self.read_manifest()
        self.assertEqual(manifest["state"], "produced")
        self.assertIn("artifact_contract.toml", manifest["identity_files"])
        self.assertIn("data.csv", manifest["identity_files"])
        # run.json is integrity-tracked but not an identity file
        self.assertIn("run.json", manifest["files"])
        self.assertNotIn("run.json", manifest["identity_files"])

    def test_finalize_patches_run_json_with_artifact_hash(self) -> None:
        self.init_and_finalize()
        manifest = self.read_manifest()
        run_record = json.loads(
            (self.artifact_dir / "run.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            run_record["output_artifact_hash"], manifest["artifact_hash"]
        )

    def test_finalize_submits_pending_review(self) -> None:
        self.init_and_finalize()
        approval = json.loads(
            (self.artifact_dir / "approval.json").read_text(encoding="utf-8")
        )
        self.assertEqual(approval["status"], "pending_review")
        self.assertEqual(approval["artifact_hash"], self.read_manifest()["artifact_hash"])

    def test_finalize_refuses_approved_artifact(self) -> None:
        self.init_and_finalize()
        approval = {
            "status": "approved",
            "artifact_hash": self.read_manifest()["artifact_hash"],
            "manifest_hash": self.read_manifest()["manifest_hash"],
        }
        (self.artifact_dir / "approval.json").write_text(
            json.dumps(approval), encoding="utf-8"
        )
        code, _, err = run_artifact("finalize", str(self.artifact_dir))
        self.assertEqual(code, 2)
        self.assertIn("immutable", err)

    def test_verify_full_detects_tamper_after_approval(self) -> None:
        self.init_and_finalize()
        manifest = self.read_manifest()
        approval = {
            "status": "approved",
            "artifact_hash": manifest["artifact_hash"],
            "manifest_hash": manifest["manifest_hash"],
        }
        (self.artifact_dir / "approval.json").write_text(
            json.dumps(approval), encoding="utf-8"
        )
        (self.artifact_dir / "data.csv").write_text("id,x\n1,9.9\n", encoding="utf-8")
        code, out, _ = run_artifact("verify", str(self.artifact_dir), "--full")
        self.assertEqual(code, 1)
        self.assertIn("SC007", out)

    def test_approve_refuses_non_tty(self) -> None:
        self.init_and_finalize()
        # The test harness stdin/stdout are not TTYs; approval must refuse.
        if sys.stdin.isatty():
            self.skipTest("interactive environment")
        code, _, err = run_artifact(
            "approve", str(self.artifact_dir), "--reviewer", "tester"
        )
        self.assertEqual(code, 2)
        self.assertIn("human action", err)
        approval = json.loads(
            (self.artifact_dir / "approval.json").read_text(encoding="utf-8")
        )
        self.assertEqual(approval["status"], "pending_review")

    def test_approve_interactive_flow(self) -> None:
        self.init_and_finalize()
        fake_in, fake_out = FakeTty(), FakeTty()
        with mock.patch.object(sys, "stdin", fake_in), mock.patch.object(
            sys, "stdout", fake_out
        ), mock.patch("builtins.input", return_value="approve"):
            code = artifact.run(
                ["approve", str(self.artifact_dir), "--reviewer", "tester"]
            )
        self.assertEqual(code, 0)
        approval = json.loads(
            (self.artifact_dir / "approval.json").read_text(encoding="utf-8")
        )
        self.assertEqual(approval["status"], "approved")
        self.assertEqual(approval["reviewed_by"], "tester")
        # The linter must now fully accept the approved artifact.
        collector = lint.IssueCollector(self.root, suppressions={})
        lint.verify_artifact_dir(self.artifact_dir, collector, full=True)
        self.assertEqual(collector.issues, [])

    def test_approve_wrong_confirmation_aborts(self) -> None:
        self.init_and_finalize()
        fake_in, fake_out = FakeTty(), FakeTty()
        with mock.patch.object(sys, "stdin", fake_in), mock.patch.object(
            sys, "stdout", fake_out
        ), mock.patch("builtins.input", return_value="yes"):
            code = artifact.run(
                ["approve", str(self.artifact_dir), "--reviewer", "tester"]
            )
        self.assertEqual(code, 1)
        approval = json.loads(
            (self.artifact_dir / "approval.json").read_text(encoding="utf-8")
        )
        self.assertEqual(approval["status"], "pending_review")


if __name__ == "__main__":
    unittest.main()
