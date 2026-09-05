"""Exercise the delivered pipeline, its actual contracts, and review choices."""
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/minimal_pipeline"
SCRIPTS = ROOT / "scripts"


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


class PipelineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="scientific-pipeline-test-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name) / "example"
        shutil.copytree(EXAMPLE, self.work, ignore=shutil.ignore_patterns("artifacts", "__pycache__"))
        self.env = {**os.environ, "SCIENTIFIC_CODING_SCRIPTS": str(SCRIPTS), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}

    def command(self, *args):
        return subprocess.run([sys.executable, *map(str, args)], cwd=self.work, env=self.env, capture_output=True, text=True, encoding="utf-8")

    def run_pipeline(self, clock=None):
        before = set((self.work / "artifacts").glob("run_*"))
        if clock is None:
            result = self.command("pipeline.py")
        else:
            result = self.command("-c", f"from unittest.mock import patch; from pathlib import Path; import pipeline; from artifact_io import time; p=patch.object(time, 'time', return_value={clock}); p.start(); pipeline.run(Path('configs/pipeline.toml'))")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        created = set((self.work / "artifacts").glob("run_*")) - before
        self.assertEqual(len(created), 1)
        return created.pop()

    def test_continuous_pipeline_numbers_lineage_and_full_integrity(self):
        run = self.run_pipeline()
        raw = read_rows(run / "raw_trials/data/raw_trials.csv")
        retained = read_rows(run / "processed_trials/data/processed_trials.csv")
        exclusions = read_rows(run / "processed_trials/exclusions.csv")
        result = json.loads((run / "analysis_result/result.json").read_text(encoding="utf-8"))
        self.assertEqual(len(raw), 80)
        self.assertEqual({r["trial_id"] for r in raw}, {r["trial_id"] for r in retained} | {r["trial_id"] for r in exclusions})
        self.assertFalse({r["trial_id"] for r in retained} & {r["trial_id"] for r in exclusions})
        control = [float(r["amplitude_uv"]) for r in retained if r["condition"] == "control"]
        treatment = [float(r["amplitude_uv"]) for r in retained if r["condition"] == "treatment"]
        expected = sum(treatment) / len(treatment) - sum(control) / len(control)
        self.assertAlmostEqual(result["difference_uv"], expected, places=4)
        mapping = read_rows(run / "analysis_result/aggregation.csv")
        values = {r["trial_id"]: float(r["amplitude_uv"]) for r in retained}
        self.assertEqual(set(values), {r["trial_id"] for r in mapping})
        self.assertAlmostEqual(sum(float(r["weight"]) * values[r["trial_id"]] for r in mapping), expected)
        self.assertLess(result["ci_low_uv"], result["ci_high_uv"])
        self.assertIn(str(result["ci_low_uv"]), (run / "results.svg").read_text(encoding="utf-8"))
        self.assertEqual(list(run.rglob("approval.json")), [])
        checked = self.command(SCRIPTS / "scientific_code_lint.py", ".", "--full-artifact-checks", "--strict-warnings")
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_same_seed_new_clock_changes_provenance_only(self):
        first = self.run_pipeline(clock=1000000000)
        second = self.run_pipeline(clock=2000000000)
        for stage in ("raw_trials", "processed_trials", "analysis_result"):
            a = json.loads((first / stage / "manifest.json").read_text(encoding="utf-8"))
            b = json.loads((second / stage / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(a["artifact_hash"], b["artifact_hash"], stage)
            self.assertNotEqual(a["manifest_hash"], b["manifest_hash"], stage)

    def test_sensitivity_rerun_preserves_old_results_and_reconciles_exclusions(self):
        first = self.run_pipeline()
        old = {str(p.relative_to(first)): hashlib.sha256(p.read_bytes()).hexdigest() for p in first.rglob("*") if p.is_file()}
        config = self.work / "configs/preprocess.toml"
        config.write_text(config.read_text(encoding="utf-8").replace("= 0.2", "= 1.0"), encoding="utf-8")
        second = self.run_pipeline()
        self.assertEqual(old, {str(p.relative_to(first)): hashlib.sha256(p.read_bytes()).hexdigest() for p in first.rglob("*") if p.is_file()})
        excluded = read_rows(second / "processed_trials/exclusions.csv")
        self.assertTrue(excluded)
        self.assertTrue(all(float(r["amplitude_uv"]) < 1.0 for r in excluded))
        self.assertTrue(all(float(r["amplitude_uv"]) >= 1.0 for r in read_rows(second / "processed_trials/data/processed_trials.csv")))

    def test_requested_review_pauses_only_at_selected_point(self):
        config = self.work / "configs/pipeline.toml"
        config.write_text(config.read_text(encoding="utf-8").replace('pause_after = ""', 'pause_after = "preprocess"'), encoding="utf-8")
        run = self.run_pipeline()
        self.assertTrue((run / "processed_trials/manifest.json").exists())
        self.assertFalse((run / "raw_trials/approval.json").exists())
        self.assertFalse((run / "analysis_result").exists())
        self.assertEqual(json.loads((run / "processed_trials/approval.json").read_text(encoding="utf-8"))["status"], "pending_review")
        result = self.command(SCRIPTS / "scientific_artifact.py", "verify", run / "processed_trials", "--full")
        self.assertEqual(result.returncode, 0, result.stdout)
        result = self.command(SCRIPTS / "scientific_artifact.py", "verify", run / "processed_trials", "--require-review")
        self.assertEqual(result.returncode, 1)

    def test_external_tamper_is_rejected_at_entry(self):
        run = self.run_pipeline()
        data = run / "processed_trials/data/processed_trials.csv"
        data.write_text(data.read_text(encoding="utf-8").replace("control-001", "control-999"), encoding="utf-8")
        path = (run / "processed_trials").relative_to(self.work).as_posix()
        config = self.work / "configs/pipeline.toml"
        config.write_text(config.read_text(encoding="utf-8").replace('processed_artifact = ""', f'processed_artifact = "{path}"'), encoding="utf-8")
        result = self.command("pipeline.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Tracked content differs", result.stderr)

    def test_internal_pipeline_does_not_reload_or_reverify_its_outputs(self):
        result = self.command("-c", "from unittest.mock import patch; from pathlib import Path; import pipeline; import artifact_io; p=patch.object(artifact_io.integrity, 'verify_artifact_dir', side_effect=AssertionError('unexpected duplicate input verification')); p.start(); q=patch.object(artifact_io.integrity, 'payload_schema_problems', side_effect=AssertionError('unexpected duplicate schema scan')); q.start(); pipeline.run(Path('configs/pipeline.toml'))")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_failed_publication_cleans_its_staging_only(self):
        code = "from pathlib import Path; from unittest.mock import patch; import artifact_io; from stages import acquire_data; target=Path('artifacts/failed'); p=patch.object(artifact_io.artifact_tool, 'run', return_value=2); p.start(); acquire_data.run(Path('configs/acquire_data.toml'), target)"
        result = self.command("-c", code)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.work / "artifacts/failed").exists())
        self.assertEqual(list((self.work / "artifacts").glob(".staging-*")), [])


if __name__ == "__main__":
    unittest.main()
