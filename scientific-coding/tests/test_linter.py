#!/usr/bin/env python3
"""Regression tests for scripts/scientific_code_lint.py.

Every check gets positive (violation fires), negative (clean code passes),
false-positive regression, and suppression fixtures where applicable. The
suite uses only the standard library and invokes the linter in-process.

Run from the skill directory:

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import scientific_code_lint as lint


def run_lint(root: Path, *extra: str) -> tuple[int, list[dict]]:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        code = lint.run([str(root), "--format", "json", *extra])
    return code, json.loads(stdout.getvalue())["issues"]


class TempProject(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, relative: str, content: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def issues(self, *extra: str) -> list[dict]:
        _, found = run_lint(self.root, *extra)
        return found

    def codes(self, *extra: str) -> set[str]:
        return {issue["code"] for issue in self.issues(*extra)}

    def make_artifact(
        self,
        relative: str,
        files: dict[str, str],
        approved: bool = False,
    ) -> Path:
        """Create a convention-conformant artifact directory."""
        directory = self.root / relative
        directory.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            (directory / name).write_text(content, encoding="utf-8")
        file_map = {name: lint.sha256_file(directory / name) for name in files}
        contract_path = "artifact_contract.toml"
        manifest = {
            "schema_version": 1,
            "contract": {
                "name": "TestDataset",
                "version": 1,
                "path": contract_path,
                "sha256": file_map[contract_path],
            },
            "identity_files": sorted(files),
            "files": file_map,
        }
        manifest["artifact_hash"] = lint.derived_artifact_hash(manifest)
        manifest["manifest_hash"] = lint.derived_manifest_hash(manifest)
        (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        if approved:
            approval = {
                "status": "approved",
                "artifact_hash": manifest["artifact_hash"],
                "manifest_hash": manifest["manifest_hash"],
                "reviewed_by": "tester",
            }
            (directory / "approval.json").write_text(
                json.dumps(approval), encoding="utf-8"
            )
        return directory


NO_ARTIFACTS = ("--no-artifact-checks",)


class StageImportTests(TempProject):
    def test_direct_sibling_import_flags(self) -> None:
        self.write("stages/preprocess_raw.py", '"""Preprocess."""\n')
        self.write(
            "stages/main_analysis.py",
            '"""Analysis."""\nimport preprocess_raw\n',
        )
        issues = self.issues(*NO_ARTIFACTS)
        sc001 = [i for i in issues if i["code"] == "SC001"]
        self.assertTrue(sc001)
        self.assertEqual(sc001[0]["severity"], "error")

    def test_transitive_import_flags_with_route(self) -> None:
        self.write("stages/preprocess_raw.py", '"""Preprocess."""\n')
        self.write(
            "lib/middle.py",
            '"""Helper."""\nfrom stages.preprocess_raw import main\n',
        )
        self.write(
            "stages/main_analysis.py",
            '"""Analysis."""\nimport lib.middle\n',
        )
        issues = [i for i in self.issues(*NO_ARTIFACTS) if i["code"] == "SC001"]
        self.assertTrue(issues)
        self.assertIn("transitively", issues[0]["message"])
        self.assertIn("lib.middle -> stages.preprocess_raw", issues[0]["message"])

    def test_transitive_import_via_view_flags_sc006(self) -> None:
        self.write("stages/preprocess_raw.py", '"""Preprocess."""\n')
        self.write(
            "lib/middle.py",
            '"""Helper."""\nfrom stages import preprocess_raw\n',
        )
        self.write("figures/figure_main.py", '"""Figure."""\nimport lib.middle\n')
        issues = [i for i in self.issues(*NO_ARTIFACTS) if i["code"] == "SC006"]
        self.assertTrue(issues)
        self.assertIn("transitively", issues[0]["message"])

    def test_third_party_stages_package_is_not_flagged(self) -> None:
        self.write("stages/preprocess_raw.py", '"""Preprocess."""\n')
        self.write(
            "stages/main_analysis.py",
            '"""Analysis."""\nimport stages.framework\n',
        )
        self.assertNotIn("SC001", self.codes(*NO_ARTIFACTS))

    def test_local_non_stage_import_is_clean(self) -> None:
        self.write("stages/preprocess_raw.py", '"""Preprocess."""\n')
        self.write("lib/seqio.py", '"""I/O helpers."""\n')
        self.write("stages/main_analysis.py", '"""Analysis."""\nimport lib.seqio\n')
        self.assertNotIn("SC001", self.codes(*NO_ARTIFACTS))

    def test_sys_path_style_bare_import_still_flagged(self) -> None:
        self.write("stages/preprocess_raw.py", '"""Preprocess."""\n')
        self.write(
            "figures/figure_main.py",
            '"""Figure."""\nimport sys\nsys.path.insert(0, "../stages")\n'
            "from preprocess_raw import main\n",
        )
        self.assertIn("SC006", self.codes(*NO_ARTIFACTS))


class CliSurfaceTests(TempProject):
    STAGE_HEAD = '"""Stage."""\nimport argparse\n\n\ndef main():\n    p = argparse.ArgumentParser()\n'
    STAGE_TAIL = "    p.parse_args()\n"

    def test_scientific_parameters_are_a_hard_error(self) -> None:
        self.write(
            "stages/main_analysis.py",
            self.STAGE_HEAD
            + '    p.add_argument("--config")\n'
            + '    p.add_argument("--seed")\n'
            + '    p.add_argument("--window-ms")\n'
            + self.STAGE_TAIL,
        )
        issues = [i for i in self.issues(*NO_ARTIFACTS) if i["code"] == "SC002"]
        self.assertTrue(issues)
        self.assertEqual(issues[0]["severity"], "error")
        self.assertIn("seed", issues[0]["message"])

    def test_operational_parameters_are_a_warning(self) -> None:
        self.write(
            "stages/main_analysis.py",
            self.STAGE_HEAD
            + '    p.add_argument("--config")\n'
            + '    p.add_argument("--log-level")\n'
            + '    p.add_argument("--output-dir")\n'
            + self.STAGE_TAIL,
        )
        issues = [i for i in self.issues(*NO_ARTIFACTS) if i["code"] == "SC002"]
        self.assertTrue(issues)
        self.assertEqual(issues[0]["severity"], "warning")

    def test_config_only_cli_is_clean(self) -> None:
        self.write(
            "stages/main_analysis.py",
            self.STAGE_HEAD + '    p.add_argument("--config")\n' + self.STAGE_TAIL,
        )
        self.assertNotIn("SC002", self.codes(*NO_ARTIFACTS))


class NetworkInputTests(TempProject):
    def test_network_call_in_stage_is_error(self) -> None:
        self.write(
            "stages/main_analysis.py",
            '"""Analysis."""\nimport requests\n\n\ndef main():\n'
            '    return requests.get("https://example.com").json()\n',
        )
        self.assertIn("SC008", self.codes(*NO_ARTIFACTS))

    def test_acquisition_stage_is_exempt(self) -> None:
        self.write(
            "stages/acquire_data.py",
            '"""Download raw data."""\nimport requests\n\n\ndef main():\n'
            '    return requests.get("https://example.com").json()\n',
        )
        self.assertNotIn("SC008", self.codes(*NO_ARTIFACTS))

    def test_marker_declared_stage_is_checked(self) -> None:
        self.write(
            "pipeline_step.py",
            '# scientific-code: stage\n"""Unconventionally named stage."""\n'
            "import requests\n\n\ndef main():\n"
            '    return requests.get("https://example.com").json()\n',
        )
        self.assertIn("SC008", self.codes(*NO_ARTIFACTS))

    def test_scope_config_declares_stage_roots(self) -> None:
        self.write(
            "scientific-code.toml",
            '[scope]\nstage_roots = ["research"]\ninfrastructure_roots = ["src"]\n',
        )
        self.write(
            "research/neural_features.py",
            '"""Neural features."""\nimport requests\n\n\ndef main():\n'
            '    return requests.get("https://example.com").json()\n',
        )
        self.assertIn("SC008", self.codes(*NO_ARTIFACTS))

    def test_marker_beats_infrastructure_root(self) -> None:
        self.write(
            "scientific-code.toml",
            '[scope]\ninfrastructure_roots = ["src"]\n',
        )
        self.write(
            "src/pipeline_step.py",
            '# scientific-code: stage\n"""Deliberate stage inside infra root."""\n'
            "import requests\n\n\ndef main():\n"
            '    return requests.get("https://example.com").json()\n',
        )
        self.assertIn("SC008", self.codes(*NO_ARTIFACTS))


class NamingDisciplineTests(TempProject):
    def test_infrastructure_utils_and_manager_are_not_flagged(self) -> None:
        self.write("infra/utils.py", '"""Shared infrastructure helpers."""\n')
        self.write(
            "infra/connection.py",
            '"""Database connections."""\n\n\nclass ConnectionManager:\n    pass\n',
        )
        codes = self.codes(*NO_ARTIFACTS)
        self.assertNotIn("SC102", codes)
        self.assertNotIn("SC103", codes)

    def test_utils_inside_stages_is_flagged(self) -> None:
        self.write("stages/utils.py", '"""Assorted study logic."""\n')
        self.assertIn("SC103", self.codes(*NO_ARTIFACTS))

    def test_manager_inside_stages_is_flagged(self) -> None:
        self.write(
            "stages/main_analysis.py",
            '"""Analysis."""\n\n\nclass AnalysisManager:\n    pass\n',
        )
        self.assertIn("SC102", self.codes(*NO_ARTIFACTS))


class HeuristicWarningTests(TempProject):
    def test_config_branch_warns_and_suppression_silences(self) -> None:
        body = (
            '"""Analysis."""\n\n\ndef main():\n    cfg = {"method": "hfb"}\n'
            '    if cfg["method"] == "hfb":\n        pass\n'
        )
        self.write("stages/main_analysis.py", body)
        self.assertIn("SC101", self.codes(*NO_ARTIFACTS))
        self.write(
            "stages/main_analysis.py",
            "# scientific-code: allow SC101 -- display-only switch, no science\n" + body,
        )
        self.assertNotIn("SC101", self.codes(*NO_ARTIFACTS))

    def test_checkpoint_warns_and_suppression_silences(self) -> None:
        self.write(
            "stages/permutation_analysis.py",
            '"""Permutation stage."""\n\n\ndef load_state(path):\n    ...\n',
        )
        self.assertIn("SC104", self.codes(*NO_ARTIFACTS))
        self.write(
            "stages/permutation_analysis.py",
            "# scientific-code: allow SC104 -- 4-day job on preemptible nodes\n"
            '"""Permutation stage."""\n\n\ndef load_state(path):\n    ...\n',
        )
        self.assertNotIn("SC104", self.codes(*NO_ARTIFACTS))

    def test_broad_exception_warns_in_stage_but_not_in_infra(self) -> None:
        self.write(
            "stages/main_analysis.py",
            '"""Analysis."""\n\n\ndef main():\n    try:\n        pass\n'
            "    except Exception:\n        pass\n",
        )
        self.assertIn("SC106", self.codes(*NO_ARTIFACTS))

        self.write(
            "infra/fetch.py",
            '"""Robust fetch."""\n\n\ndef main():\n    try:\n        pass\n'
            "    except Exception:\n        pass\n",
        )
        codes = self.codes(*NO_ARTIFACTS)
        # infra/fetch.py is not a stage/view, so only the stage occurrence counts
        self.assertIn("SC106", codes)
        infra_hits = [
            i for i in self.issues(*NO_ARTIFACTS)
            if i["code"] == "SC106" and "infra" in i["path"]
        ]
        self.assertFalse(infra_hits)

    def test_parameter_mutation_warns(self) -> None:
        self.write(
            "stages/main_analysis.py",
            '"""Analysis."""\n\n\ndef compute_features(data, config):\n'
            '    """Compute features.\n\n'
            "    Parameters: data frame. Method: ratio. Returns frame.\n"
            "    Mutation: modifies data in place.\n"
            '    """\n    data["f"] = data["x"] * 2\n    return data\n',
        )
        self.assertIn("SC107", self.codes(*NO_ARTIFACTS))


class DocstringContractTests(TempProject):
    STAGE = "stages/main_analysis.py"

    def test_english_contract_passes(self) -> None:
        self.write(
            self.STAGE,
            '"""Analysis."""\n\n\ndef compute_features(data, config):\n'
            '    """Compute trial features.\n\n'
            "    Parameters\n    ----------\n    data : array-like\n"
            "        Preprocessed signals.\n\n"
            "    Returns\n    -------\n    ndarray\n        Feature matrix.\n\n"
            "    The transformation is a per-trial mean. No mutation or side effects.\n"
            '    """\n    return data\n',
        )
        self.assertNotIn("SC108", self.codes(*NO_ARTIFACTS))

    def test_chinese_contract_passes(self) -> None:
        self.write(
            self.STAGE,
            '"""分析阶段。"""\n\n\ndef compute_power(data, config):\n'
            '    """计算功率谱。\n\n'
            "    输入为预处理后的时频数据,输出为各通道功率值。\n"
            "    算法:对每个通道做 Welch 平均。无就地修改。\n"
            '    """\n    return data\n',
        )
        self.assertNotIn("SC108", self.codes(*NO_ARTIFACTS))

    def test_complete_module_docstring_waives_function_checks(self) -> None:
        self.write(
            self.STAGE,
            '"""Compute trial features from ProcessedDatasetV1.\n\n'
            "Input artifact: ProcessedDatasetV1 signals, microvolt, stimulus-locked.\n"
            "Transformation: per-trial baseline ratio and band power.\n"
            "Output artifact: FeatureMatrixV1. Mutation: none, no side effects.\n"
            '"""\n\n\ndef compute_features(data, config):\n    return data\n',
        )
        self.assertNotIn("SC108", self.codes(*NO_ARTIFACTS))

    def test_missing_contract_warns(self) -> None:
        self.write(
            self.STAGE,
            '"""Analysis."""\n\n\ndef compute_features(data, config):\n'
            "    return data\n",
        )
        self.assertIn("SC108", self.codes(*NO_ARTIFACTS))


class OptimizationEvidenceTests(TempProject):
    STAGE = (
        '"""Permutation analysis stage.\n\n'
        "Input: NeuralFeatureV1. Transformation: label permutation.\n"
        "Output: PermutationResultV1. Mutation: none.\n"
        '"""\nfrom numba import njit\n\n\n@njit\ndef _work(data):\n    return data\n'
    )

    def setUp(self) -> None:
        super().setUp()
        self.write("stages/permutation_analysis.py", self.STAGE)

    def test_missing_report_warns(self) -> None:
        issues = [i for i in self.issues(*NO_ARTIFACTS) if i["code"] == "SC105"]
        self.assertTrue(issues)
        self.assertIn("no optimization_report.json", issues[0]["message"])

    def test_placeholder_report_does_not_satisfy(self) -> None:
        self.write(
            "optimization_report.json",
            json.dumps(
                {
                    "stage": "permutation_analysis",
                    "representative_workload": "TODO",
                    "decision": "accept",
                }
            ),
        )
        issues = [i for i in self.issues(*NO_ARTIFACTS) if i["code"] == "SC105"]
        self.assertTrue(issues)
        self.assertIn("lacks valid evidence", issues[0]["message"])

    def test_inconsistent_speedup_does_not_satisfy(self) -> None:
        self.write(
            "optimization_report.json",
            json.dumps(
                {
                    "stage": "permutation_analysis",
                    "representative_workload": "24 subjects, 10000 permutations",
                    "scientific_equivalence": {"result": "pass"},
                    "environment": {"git_commit": "abc123"},
                    "reference": {"end_to_end_wall_time_s": 1000.0},
                    "optimized": {"end_to_end_wall_time_s": 500.0},
                    "pipeline_speedup": 5.0,
                    "decision": "accept",
                }
            ),
        )
        issues = [i for i in self.issues(*NO_ARTIFACTS) if i["code"] == "SC105"]
        self.assertTrue(issues)
        self.assertIn("ratio", issues[0]["message"])

    def test_valid_report_satisfies(self) -> None:
        self.write(
            "optimization_report.json",
            json.dumps(
                {
                    "stage": "permutation_analysis",
                    "representative_workload": "24 subjects, 10000 permutations",
                    "scientific_equivalence": {"result": "pass"},
                    "environment": {"git_commit": "abc123"},
                    "reference": {"end_to_end_wall_time_s": 1000.0},
                    "optimized": {"end_to_end_wall_time_s": 500.0},
                    "pipeline_speedup": 2.0,
                    "decision": "accept",
                }
            ),
        )
        self.assertNotIn("SC105", self.codes(*NO_ARTIFACTS))


class ArtifactIntegrityTests(TempProject):
    FILES = {
        "artifact_contract.toml": 'name = "TestDataset"\nversion = 1\n',
        "data.csv": "id,x\n1,0.5\n",
    }

    def test_valid_approved_artifact_is_clean_in_both_modes(self) -> None:
        self.make_artifact("artifacts/ds/run_001", self.FILES, approved=True)
        self.assertEqual(self.issues(), [])
        self.assertEqual(self.issues("--full-artifact-checks"), [])

    def test_tampered_payload_only_detected_in_full_mode(self) -> None:
        directory = self.make_artifact("artifacts/ds/run_001", self.FILES, approved=True)
        (directory / "data.csv").write_text("id,x\n1,0.9\n", encoding="utf-8")
        self.assertNotIn("SC007", self.codes())
        self.assertIn("SC007", self.codes("--full-artifact-checks"))

    def test_approval_hash_mismatch_detected_in_metadata_mode(self) -> None:
        directory = self.make_artifact("artifacts/ds/run_001", self.FILES, approved=True)
        approval = json.loads((directory / "approval.json").read_text(encoding="utf-8"))
        approval["artifact_hash"] = "sha256:" + "0" * 64
        (directory / "approval.json").write_text(json.dumps(approval), encoding="utf-8")
        self.assertIn("SC003", self.codes())

    def test_untracked_file_added_after_approval(self) -> None:
        directory = self.make_artifact("artifacts/ds/run_001", self.FILES, approved=True)
        (directory / "extra.csv").write_text("surprise\n", encoding="utf-8")
        self.assertIn("SC007", self.codes())

    def test_artifact_without_manifest_is_sc004(self) -> None:
        directory = self.root / "artifacts/ds/run_001"
        directory.mkdir(parents=True)
        (directory / "approval.json").write_text("{}", encoding="utf-8")
        self.assertIn("SC004", self.codes())

    def test_unapproved_input_is_sc005(self) -> None:
        self.make_artifact("artifacts/raw/run_001", self.FILES, approved=False)
        self.write(
            "run.json",
            json.dumps(
                {"input_artifacts": [{"path": "artifacts/raw/run_001"}]}
            ),
        )
        self.assertIn("SC005", self.codes())

    def test_approved_input_is_clean(self) -> None:
        directory = self.make_artifact("artifacts/raw/run_001", self.FILES, approved=True)
        manifest = json.loads(
            (directory / "manifest.json").read_text(encoding="utf-8")
        )
        self.write(
            "run.json",
            json.dumps(
                {
                    "input_artifacts": [
                        {
                            "path": "artifacts/raw/run_001",
                            "artifact_hash": manifest["artifact_hash"],
                            "manifest_hash": manifest["manifest_hash"],
                        }
                    ]
                }
            ),
        )
        self.assertNotIn("SC005", self.codes())

    def test_tampered_input_payload_only_detected_in_full_mode(self) -> None:
        directory = self.make_artifact("artifacts/raw/run_001", self.FILES, approved=True)
        self.write(
            "run.json",
            json.dumps(
                {"input_artifacts": [{"path": "artifacts/raw/run_001"}]}
            ),
        )
        (directory / "data.csv").write_text("id,x\n1,9.9\n", encoding="utf-8")
        self.assertNotIn("SC005", self.codes())
        self.assertIn("SC005", self.codes("--full-artifact-checks"))


@unittest.skipUnless(shutil.which("git"), "git is required for selection tests")
class GitSelectionTests(TempProject):
    def git(self, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(self.root), *args],
            check=True,
            capture_output=True,
        )

    def make_repo(self) -> None:
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test")

    def test_changed_only_after_commit_checks_nothing(self) -> None:
        self.make_repo()
        self.write(
            "stages/main_analysis.py",
            '"""Analysis."""\nimport requests\n\n\ndef main():\n'
            '    return requests.get("https://example.com").json()\n',
        )
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "add stage")
        _, issues = run_lint(self.root, "--changed-only", "--no-artifact-checks")
        self.assertEqual(issues, [])

    def test_base_ref_catches_committed_violations(self) -> None:
        self.make_repo()
        self.write("stages/main_analysis.py", '"""Analysis."""\n')
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.write(
            "stages/main_analysis.py",
            '"""Analysis."""\nimport requests\n\n\ndef main():\n'
            '    return requests.get("https://example.com").json()\n',
        )
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "add network call")
        codes_clean, _ = run_lint(
            self.root, "--changed-only", "--no-artifact-checks"
        )
        codes_base, issues = run_lint(
            self.root, "--base-ref", "HEAD~1", "--no-artifact-checks"
        )
        self.assertFalse([i for i in issues if i["code"] == "SC008"] and codes_clean)
        self.assertTrue(any(i["code"] == "SC008" for i in issues))
        self.assertEqual(codes_base, 1)


class NestedProjectScopeTests(TempProject):
    """A monorepo root without its own config must inherit nested project scope."""

    def _nested_project(self) -> Path:
        nested = self.root / "packages" / "study_a"
        (nested / "stages").mkdir(parents=True, exist_ok=True)
        (nested / "figures").mkdir(parents=True, exist_ok=True)
        (nested / "scientific-code.toml").write_text(
            '[scope]\nstage_roots = ["stages"]\n'
            'view_roots = ["figures"]\nartifact_roots = ["artifacts"]\n'
            'infrastructure_roots = ["stages/common.py"]\n',
            encoding="utf-8",
        )
        (nested / "stages" / "common.py").write_text('"""Shared helpers."""\n')
        (nested / "stages" / "acquire.py").write_text(
            '"""Acquire."""\nimport common\n'
        )
        return nested

    def test_nested_scope_applies_from_monorepo_root(self) -> None:
        nested = self._nested_project()
        issues = [i for i in self.issues("--no-artifact-checks") if "packages" in i["path"]]
        self.assertFalse([i for i in issues if i["code"] == "SC001"])
        self.assertFalse([i for i in issues if i["code"] == "SC103"])

    def test_run_json_paths_resolve_against_owning_project(self) -> None:
        nested = self._nested_project()
        artifact = self.make_artifact(
            "packages/study_a/artifacts/raw/run_001",
            {
                "artifact_contract.toml": 'name = "Raw"\nversion = 1\n',
                "data.csv": "trial_id,amplitude\n1,1.0\n",
            },
            approved=True,
        )
        manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))
        approval = json.loads((artifact / "approval.json").read_text(encoding="utf-8"))
        run_record = {
            "input_artifacts": [
                {
                    "path": "artifacts/raw/run_001",
                    "artifact_hash": approval["artifact_hash"],
                    "manifest_hash": approval["manifest_hash"],
                }
            ]
        }
        self.write(
            "packages/study_a/artifacts/processed/run_001/run.json",
            json.dumps(run_record),
        )
        self.assertNotIn("SC005", self.codes())


class ViewScientificComputationTests(TempProject):
    """SC109: statistical computation belongs in analysis stages, not views."""

    DIRTY = '''\
"""Accuracy figure with inline inference."""
import numpy as np

xs = np.loadtxt("analysis_result.csv", skiprows=1)
clean = xs[np.abs(xs - np.median(xs)) < 3.0]
ci_low, ci_high = np.percentile(clean, [2.5, 97.5])
model = LinearModel().fit(clean.reshape(-1, 1))
'''

    CLEAN = '''\
"""Accuracy figure over approved analysis artifact."""
import matplotlib.pyplot as plt

fig, ax = plt.subplots()
ax.plot(ci_low_column, ci_high_column)
fig.savefig("figure_accuracy.svg")
'''

    def test_statistics_in_view_warns(self) -> None:
        self.write("figures/figure_accuracy.py", self.DIRTY)
        hits = [i for i in self.issues() if i["code"] == "SC109"]
        self.assertTrue(hits)
        self.assertEqual(hits[0]["severity"], "warning")

    def test_presentation_only_view_passes(self) -> None:
        self.write("figures/figure_accuracy.py", self.CLEAN)
        self.assertNotIn("SC109", self.codes())

    def test_stage_with_statistics_is_not_flagged(self) -> None:
        self.write("stages/bootstrap_ci.py", self.DIRTY)
        self.assertNotIn("SC109", self.codes())

    def test_provenance_docstring_does_not_fire(self) -> None:
        self.write(
            "figures/figure_results.py",
            '"""Render the approved bootstrap CI artifact as a bar figure."""\n'
            "import matplotlib.pyplot as plt\n\n"
            "fig, ax = plt.subplots()\n"
            "fig.savefig('out.svg')\n",
        )
        self.assertNotIn("SC109", self.codes())

    def test_suppression_directive(self) -> None:
        self.write(
            "figures/figure_accuracy.py",
            "# scientific-code: allow SC109 -- statistical term appears in prose comment only\n"
            + self.DIRTY,
        )
        self.assertNotIn("SC109", self.codes())


if __name__ == "__main__":
    unittest.main()
