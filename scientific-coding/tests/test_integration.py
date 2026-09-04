"""Integration tests: the committed example verifies, and the full lifecycle works from scratch."""

from __future__ import annotations

import csv
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
EXAMPLE = REPO_ROOT / "examples" / "minimal_pipeline"
ARTIFACT_CLI = SCRIPTS / "scientific_artifact.py"

sys.path.insert(0, str(SCRIPTS))

import scientific_artifact as artifact_tool  # noqa: E402


class _Tty(io.StringIO):
    """StringIO that claims to be a terminal, for approval prompts."""

    def isatty(self) -> bool:
        return True


def approve_via_mock_tty(run_dir: Path, note: str = "integration test approval") -> None:
    """Approve an artifact directory through the real CLI logic.

    Wraps scientific_artifact.run(["approve", ...]) with a fake TTY and a
    scripted "approve" confirmation, exactly like a human would type it.
    """
    import builtins

    input_lines = iter(["approve"])
    real_input = builtins.input
    builtins.input = lambda prompt="": next(input_lines)
    sys.stdin = _Tty()
    sys.stdout = _Tty()
    try:
        code = artifact_tool.run(
            ["approve", str(run_dir), "--reviewer", "integration-test", "--note", note]
        )
    finally:
        builtins.input = real_input
        sys.stdin = sys.__stdin__
        sys.stdout = sys.__stdout__
    if code != 0:
        raise AssertionError(f"approve exited {code} for {run_dir}")


def run_python(cwd: Path, script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def write_contract(run_dir: Path, name: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "artifact_contract.toml").write_text(
        f'''name = "{name}"
version = 1
description = "Integration-test contract for {name}."

[data]
path = "TODO"
representation = "TODO"
dimensions = ["TODO"]
dtype = "TODO"
unit = "TODO"
missing_value = "not_allowed"

[sample]
identity = "TODO"
id_column = "sample_id"
ordering = "TODO"
population = "TODO"

[compatibility]
consumers_require_exact_version = true
''',
        encoding="utf-8",
    )


class CommittedExampleTests(unittest.TestCase):
    def test_committed_example_lint_clean_full_checks(self) -> None:
        """The shipped example must pass the strictest lint mode."""
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "scientific_code_lint.py"),
                ".",
                "--full-artifact-checks",
            ],
            cwd=EXAMPLE,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"committed example lint failed:\n{result.stdout}\n{result.stderr}",
        )
        self.assertIn("0 error(s), 0 warning(s)", result.stdout)

    def test_committed_artifacts_are_approved(self) -> None:
        for name in ("raw_trials", "processed_trials", "analysis_result"):
            approval = json.loads(
                (EXAMPLE / "artifacts" / name / "run_001" / "approval.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(approval["status"], "approved", name)
            self.assertEqual(approval["reviewed_by"], "maintainer", name)

    def test_exclusion_ledger_is_row_level(self) -> None:
        with (EXAMPLE / "artifacts" / "processed_trials" / "run_001" / "exclusions.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            reader = csv.DictReader(handle)
            header = reader.fieldnames
            rows = list(reader)
        self.assertEqual(
            ["trial_id", "condition", "amplitude_uv", "reason"], header
        )
        self.assertEqual(rows, [])  # no exclusions in the shipped data


class FullLifecycleTests(unittest.TestCase):
    """Copy the example to a temp dir, run everything from scratch."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory(prefix="sci-lifecycle-")
        self.addCleanup(self._tmpdir.cleanup)
        self.work = Path(self._tmpdir.name) / "minimal_pipeline"
        shutil.copytree(EXAMPLE, self.work)
        # Drop committed artifacts; the test rebuilds them from stage code.
        shutil.rmtree(self.work / "artifacts")
        (self.work / "artifacts").mkdir()

    def _finalize_and_approve(self, relative: str, contract: str) -> Path:
        run_dir = self.work / "artifacts" / relative
        write_contract(run_dir, contract)
        finished = run_python(self.work, ARTIFACT_CLI, "finalize", str(run_dir.relative_to(self.work)))
        self.assertEqual(finished.returncode, 0, finished.stderr)
        approve_via_mock_tty(run_dir)
        return run_dir

    def test_full_lifecycle_lint_clean(self) -> None:
        acquire = run_python(self.work, self.work / "stages" / "acquire_data.py")
        self.assertEqual(acquire.returncode, 0, acquire.stderr)
        self._finalize_and_approve("raw_trials/run_001", "RawTrials")

        preprocess = run_python(self.work, self.work / "stages" / "preprocess.py")
        self.assertEqual(preprocess.returncode, 0, preprocess.stderr)
        self._finalize_and_approve("processed_trials/run_001", "ProcessedTrials")

        analyze = run_python(self.work, self.work / "stages" / "analyze.py")
        self.assertEqual(analyze.returncode, 0, analyze.stderr)
        self._finalize_and_approve("analysis_result/run_001", "AnalysisResult")

        figure = run_python(self.work, self.work / "figures" / "figure_results.py")
        self.assertEqual(figure.returncode, 0, figure.stderr)
        self.assertTrue((self.work / "figures" / "results.svg").is_file())

        result = run_python(self.work, SCRIPTS / "scientific_code_lint.py", ".", "--full-artifact-checks")
        self.assertEqual(
            result.returncode,
            0,
            f"rebuilt pipeline lint failed:\n{result.stdout}\n{result.stderr}",
        )

    def test_reproducible_same_seed_same_hash(self) -> None:
        """Same seed => identical payload bytes => identical artifact hash."""
        first = self.work / "artifacts" / "raw_trials" / "run_001"
        acquire = run_python(self.work, self.work / "stages" / "acquire_data.py")
        self.assertEqual(acquire.returncode, 0, acquire.stderr)
        write_contract(first, "RawTrials")
        finished = run_python(self.work, ARTIFACT_CLI, "finalize", "artifacts/raw_trials/run_001")
        self.assertEqual(finished.returncode, 0, finished.stderr)
        manifest_first = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
        hash_first = manifest_first["artifact_hash"]

        shutil.rmtree(first)
        acquire2 = run_python(self.work, self.work / "stages" / "acquire_data.py")
        self.assertEqual(acquire2.returncode, 0, acquire2.stderr)
        write_contract(first, "RawTrials")
        finished2 = run_python(self.work, ARTIFACT_CLI, "finalize", "artifacts/raw_trials/run_001")
        self.assertEqual(finished2.returncode, 0, finished2.stderr)
        manifest_second = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(hash_first, manifest_second["artifact_hash"])

    def test_pending_review_blocks_downstream_stage(self) -> None:
        """A downstream stage must refuse to consume a pending_review artifact."""
        acquire = run_python(self.work, self.work / "stages" / "acquire_data.py")
        self.assertEqual(acquire.returncode, 0, acquire.stderr)
        self._finalize_and_approve("raw_trials/run_001", "RawTrials")
        preprocess = run_python(self.work, self.work / "stages" / "preprocess.py")
        self.assertEqual(preprocess.returncode, 0, preprocess.stderr)

        run_dir = self.work / "artifacts" / "processed_trials" / "run_001"
        write_contract(run_dir, "ProcessedTrials")
        finished = run_python(self.work, ARTIFACT_CLI, "finalize", "artifacts/processed_trials/run_001")
        self.assertEqual(finished.returncode, 0, finished.stderr)
        # NOTE: deliberately not approved here.

        analyze = run_python(self.work, self.work / "stages" / "analyze.py")
        self.assertNotEqual(analyze.returncode, 0)
        self.assertIn("not approved", analyze.stderr)


if __name__ == "__main__":
    unittest.main()
