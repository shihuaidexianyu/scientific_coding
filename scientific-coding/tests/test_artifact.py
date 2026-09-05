"""Artifact integrity is independent of optional human review."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import scientific_artifact as artifact
from support import contract_text


def run_artifact(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = artifact.run(list(args))
    return code, out.getvalue(), err.getvalue()


class FakeTty(io.StringIO):
    def isatty(self):
        return True


class ArtifactToolTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sci-artifact-test-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name) / "run"
        self.directory.mkdir()
        (self.directory / "artifact_contract.toml").write_text(contract_text(), encoding="utf-8")
        (self.directory / "data.csv").write_text("id,x\n1,0.5\n", encoding="utf-8")
        (self.directory / "run.json").write_text('{"input_artifacts": []}', encoding="utf-8")

    def finalize(self, *args):
        code, out, err = run_artifact("finalize", str(self.directory), *args)
        self.assertEqual(code, 0, out + err)
        return json.loads((self.directory / "manifest.json").read_text(encoding="utf-8"))

    def test_default_finalization_needs_no_approval(self):
        manifest = self.finalize()
        self.assertFalse(manifest["review_required"])
        self.assertFalse((self.directory / "approval.json").exists())
        self.assertEqual(run_artifact("verify", str(self.directory), "--full", "--require-review")[0], 0)
        run = json.loads((self.directory / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(run["output_artifact_hash"], manifest["artifact_hash"])
        self.assertNotIn("run.json", manifest["identity_files"])

    def test_explicit_pause_separates_integrity_from_review(self):
        self.finalize("--request-review")
        self.assertEqual(run_artifact("verify", str(self.directory), "--full")[0], 0)
        self.assertEqual(run_artifact("verify", str(self.directory), "--require-review")[0], 1)
        with mock.patch.object(sys, "stdin", FakeTty()), mock.patch.object(sys, "stdout", FakeTty()), mock.patch("builtins.input", return_value="approve"):
            code = artifact.run(["approve", str(self.directory), "--reviewer", "isolated-test-reviewer"])
        self.assertEqual(code, 0)
        self.assertEqual(run_artifact("verify", str(self.directory), "--full", "--require-review")[0], 0)

    def test_tampered_payload_is_rejected_before_first_review(self):
        self.finalize("--request-review")
        (self.directory / "data.csv").write_text("id,x\n1,999\n", encoding="utf-8")
        self.assertEqual(run_artifact("verify", str(self.directory))[0], 0)
        self.assertEqual(run_artifact("verify", str(self.directory), "--full")[0], 1)
        with mock.patch.object(sys, "stdin", FakeTty()), mock.patch.object(sys, "stdout", FakeTty()), mock.patch("builtins.input") as confirmation:
            code = artifact.run(["approve", str(self.directory), "--reviewer", "isolated-test-reviewer"])
        self.assertEqual(code, 1)
        confirmation.assert_not_called()

    def test_default_artifact_missing_payload_or_bad_hash_is_rejected(self):
        self.finalize()
        path = self.directory / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["artifact_hash"] = "invalid"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertEqual(run_artifact("verify", str(self.directory))[0], 1)
        (self.directory / "data.csv").unlink()
        self.assertEqual(run_artifact("verify", str(self.directory), "--full")[0], 1)

    def test_finalized_result_is_not_overwritten(self):
        self.finalize()
        original = {p.name: p.read_bytes() for p in self.directory.iterdir()}
        self.assertEqual(run_artifact("finalize", str(self.directory))[0], 2)
        self.assertEqual(original, {p.name: p.read_bytes() for p in self.directory.iterdir()})

    def test_custom_identity_automatically_binds_contract(self):
        manifest = self.finalize("--identity", "data.csv")
        self.assertEqual(set(manifest["identity_files"]), {"artifact_contract.toml", "data.csv"})

    def test_execution_record_cannot_form_identity_cycle(self):
        self.assertEqual(run_artifact("finalize", str(self.directory), "--identity", "run.json")[0], 2)

    def test_placeholder_contract_cannot_be_finalized(self):
        path = self.directory / "artifact_contract.toml"
        path.write_text(contract_text().replace('representation = "scalar_measurements"', 'representation = "TODO"'), encoding="utf-8")
        self.assertEqual(run_artifact("finalize", str(self.directory))[0], 2)
        self.assertFalse((self.directory / "manifest.json").exists())

    def test_declared_sample_column_must_exist(self):
        path = self.directory / "artifact_contract.toml"
        path.write_text(contract_text().replace('[sample]', '[sample]\nid_column = "missing_id"'), encoding="utf-8")
        self.finalize()
        self.assertEqual(run_artifact("verify", str(self.directory), "--full")[0], 1)

    def test_invalid_contract_path_type_fails_cleanly(self):
        path = self.directory / "artifact_contract.toml"
        path.write_text(contract_text().replace('path = "data.csv"', 'path = 42'), encoding="utf-8")
        self.assertEqual(run_artifact("finalize", str(self.directory))[0], 2)
        self.assertFalse((self.directory / "manifest.json").exists())

    def test_optional_review_refuses_noninteractive_confirmation(self):
        self.finalize("--request-review")
        with mock.patch.object(sys, "stdin", io.StringIO()):
            code, _, _ = run_artifact("approve", str(self.directory), "--reviewer", "tester")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
