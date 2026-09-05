"""Regression tests for honest evaluation outcomes, evidence and fixture boundaries."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

EVALS = Path(__file__).resolve().parents[1] / "evals"
sys.path.insert(0, str(EVALS))
import graders
import layout_checks
import run_evals


class VerdictTests(unittest.TestCase):
    def test_judge_extra_dimensions_cannot_overwrite_mechanical_results(self):
        outcomes = {"dimensions": {"layout": {"pass": False, "failures": ["missing paragraph"]},
                                    "science": {"pass": True}}}
        judge = {"dimensions": {"layout": {"status": "met"}, "science": {"status": "unmet"},
                                "semantic_accuracy": {"status": "unknown"},
                                "formatter_execution": {"status": "met"}}}
        merged = graders.assessment_dimensions(outcomes, judge)
        self.assertIs(merged["layout"]["pass"], False)
        self.assertIs(merged["science"]["pass"], True)
        self.assertEqual(merged["semantic_accuracy"]["status"], "unknown")
        self.assertEqual(merged["formatter_execution"]["status"], "met")

    def verdict(self, **changes):
        value = {"linter": {"errors": 0}, "deterministic_violations": [],
                 "outcomes": {"pass": True}, "judge": {"pass": True}}
        value.update(changes)
        return value

    def test_linter_errors_fail_even_when_judge_passes(self):
        result = graders.decide_verdict(self.verdict(linter={"errors": 1}))
        self.assertIs(result["pass"], False)

    def test_unknown_judge_does_not_pass(self):
        result = graders.decide_verdict(self.verdict(judge={"pass": None}))
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["pass"])

    def test_missing_positive_evidence_does_not_pass(self):
        result = graders.decide_verdict(self.verdict(outcomes={"pass": None}), requires_judge=False)
        self.assertEqual(result["status"], "unknown")

    def test_mock_is_smoke_and_api_failure_is_invalid(self):
        self.assertEqual(graders.decide_verdict(self.verdict(), backend="mock")["status"], "smoke")
        self.assertIsNone(graders.decide_verdict(self.verdict(), backend="mock")["pass"])
        self.assertEqual(graders.decide_verdict(self.verdict(api_error=True))["status"], "invalid")

    def test_missing_actual_output_overrules_positive_judge(self):
        self.assertIs(graders.decide_verdict(self.verdict(outcomes={"pass": False}))["pass"], False)

    def test_mention_alone_is_not_trigger_evidence(self):
        self.assertIsNone(run_evals.skill_triggered("I used scientific-coding and read SKILL.md"))

    def test_successful_read_is_observed_but_failed_read_is_not(self):
        request = {"message": {"content": [{"type": "tool_use", "id": "r1", "name": "Read", "input": {"file_path": "/repo/.claude/skills/scientific-coding/SKILL.md"}}]}}
        result = {"message": {"content": [{"type": "tool_result", "tool_use_id": "r1", "is_error": False}]}}
        trajectory = json.dumps(request) + "\n" + json.dumps(result)
        self.assertIs(run_evals.skill_triggered(trajectory), True)
        result["message"]["content"][0]["is_error"] = True
        self.assertIsNone(run_evals.skill_triggered(json.dumps(request) + "\n" + json.dumps(result)))

    def test_tool_failure_is_not_an_api_failure(self):
        self.assertFalse(run_evals.invocation_failed(json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "is_error": True}]}}), 0))
        self.assertTrue(run_evals.invocation_failed(json.dumps({"type": "result", "is_error": True}), 0))

    def test_focused_execution_evidence_keeps_failed_tools_and_real_user_boundary(self):
        records = [
            {"message": {"content": [{"type": "tool_use", "id": "read", "name": "Read", "input": {"file_path": "analysis.py"}}]}},
            {"message": {"content": [{"type": "tool_result", "tool_use_id": "read", "is_error": False, "content": "long source"}]}},
            {"type": "eval_user_followup", "text": "Change the threshold"},
            {"message": {"content": [{"type": "tool_use", "id": "check", "name": "Bash", "input": {"command": "python formatter.py --check"}}]}},
            {"message": {"content": [{"type": "tool_result", "tool_use_id": "check", "is_error": True, "content": "spacing failed"}]}},
        ]
        focused = graders.execution_evidence("\n".join(json.dumps(item) for item in records))
        self.assertIs(focused[0]["success"], True)
        self.assertNotIn("output", focused[0])
        self.assertEqual(focused[1]["event"], "actual resumed user message")
        self.assertIs(focused[2]["success"], False)
        self.assertIn("spacing failed", focused[2]["output"])

    def test_judge_has_no_tool_or_permission_bypass(self):
        command = run_evals.judge_command("claude")
        self.assertNotIn("--dangerously-skip-permissions", command)
        self.assertEqual(command[command.index("--tools") + 1], "")

    def test_judge_unknown_criterion_cannot_pass_and_raw_is_saved(self):
        reply = json.dumps({"result": json.dumps({"pass": True, "criteria": {"actual output": "unknown"}})})
        with patch.object(graders.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, reply, "")) as invoked:
            value = graders.judge_case(run_evals.judge_command("claude"), {}, "", {}, "", Path.cwd())
        self.assertIsNone(value["pass"])
        self.assertEqual(value["raw"], reply)
        self.assertIn("input", invoked.call_args.kwargs)

    def test_summary_excludes_unknown_invalid_and_mock_denominators(self):
        records = []
        for status, passed in (("pass", True), ("fail", False), ("unknown", None), ("invalid", None), ("smoke", None)):
            records.append({"case": "demo", "mode": "explicit", "language": "en", "repetition": len(records) + 1,
                            "verdict": {**self.verdict(), "status": status, "pass": passed}})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_evals.summarize(records, root)
            text = (root / "summary.md").read_text(encoding="utf-8")
            self.assertIn("| 1/2 | 1 | 1 | 1 |", text)


class OutcomeTests(unittest.TestCase):
    def test_nested_oracle_checks_different_shapes_and_actual_persisted_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_evals.materialize_repo({"fixture": "nested_epochs"}, root, "baseline", "mock")
            subprocess.run([sys.executable, "analysis.py"], cwd=root, capture_output=True, check=True)
            outcome = layout_checks.nested_science(root)
            self.assertIs(outcome["pass"], True, outcome)
            summary_path = root / "results/summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["contrast"]["peak_uv"] = [-4, -4]
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            self.assertIs(layout_checks.nested_science(root)["pass"], False)

    def test_new_resume_never_injects_after_incomplete_first_result(self):
        case = next(item for item in run_evals.load_cases()["case"] if item["id"] == "resumed_docstring_layout")
        with tempfile.TemporaryDirectory() as temporary:
            result_root = Path(temporary)
            with patch.object(run_evals, "run_agent", return_value=("", 0, 0)) as agent, patch.object(run_evals, "apply_review_update") as inject:
                value = run_evals.run_single(case, "baseline", "zh", "mock", 1, result_root, 10, False)
            self.assertEqual(agent.call_count, 1)
            inject.assert_not_called()
            self.assertIs(value["pass"], None)
            self.assertIs(value["dimensions"]["science"]["pass"], False)
            conversation = json.loads(next(result_root.glob("*/conversation.json")).read_text(encoding="utf-8"))
            self.assertIn("not injected", conversation["kind"])

    def test_new_judge_dimensions_cannot_be_silently_omitted(self):
        reply = json.dumps({"result": json.dumps({"pass": True, "criteria": {"layout": "met"}})})
        with patch.object(graders.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, reply, "")):
            value = graders.judge_case(run_evals.judge_command("claude"), {"layout_spec": {"analysis.py": {}}}, "", {}, "", Path.cwd())
        self.assertIsNone(value["pass"])

    def test_empty_toml_comment_and_machine_directive_are_not_english_prose(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_evals.materialize_repo({"fixture": "scientific_review"}, root, "baseline", "mock")
            subprocess.run([sys.executable, "analysis.py"], cwd=root, capture_output=True, check=True)
            config = root / "configs/analysis.toml"
            config.write_text("# 科学参数\n#\n# ---\n# fmt: off\n[analysis]\n\n# 保留阈值，单位微伏。\nfloor_uv = 0.5\n", encoding="utf-8")
            result = graders.review_study_outcome(root, strict=False, require_docs=True)
            self.assertFalse(any("TOML explanatory" in failure for failure in result["failures"]))
            config.write_text(config.read_text(encoding="utf-8") + "\n# This is untranslated explanatory prose.\n", encoding="utf-8")
            result = graders.review_study_outcome(root, strict=False, require_docs=True)
            self.assertTrue(any("TOML explanatory" in failure for failure in result["failures"]))

    def test_real_human_edit_changes_existing_file_boundary_and_keeps_old_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_evals.materialize_repo({"fixture": "scientific_review"}, root, "baseline", "mock")
            old = subprocess.run([sys.executable, "analysis.py"], cwd=root, capture_output=True, text=True)
            self.assertEqual(old.returncode, 0, old.stderr)
            checked = graders.review_study_outcome(root, strict=False, require_docs=False)
            self.assertIs(checked["pass"], True, checked)
            manual = run_evals.apply_review_update(root)
            self.assertNotEqual(manual["analysis_change"]["before_sha256"], manual["analysis_change"]["after_sha256"])
            self.assertEqual(manual["analysis_change"]["comparison_edits"], 2)
            new = subprocess.run([sys.executable, "analysis.py"], cwd=root, capture_output=True, text=True)
            self.assertEqual(new.returncode, 0, new.stderr)
            summary = json.loads((root / "results/summary.json").read_text())
            self.assertEqual(summary["counts"], {"control": 4, "treatment": 5})
            self.assertAlmostEqual(summary["difference_uv"], 0.2)
            tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=root, capture_output=True, text=True)
            self.assertNotEqual(tests.returncode, 0, "The old equality test must become stale after the human edit")

    def test_resume_uses_same_real_cli_session_argument(self):
        with tempfile.TemporaryDirectory() as temporary:
            returned = subprocess.CompletedProcess([], 0, '{"type":"result","session_id":"session-example"}', "")
            with patch.object(run_evals.subprocess, "run", return_value=returned) as invoked:
                run_evals.run_agent("claude", "first user turn", Path(temporary), 10, session_id="session-example")
                self.assertIn("--session-id", invoked.call_args.args[0])
                run_evals.run_agent("claude", "later user change", Path(temporary), 10, session_id="session-example", resume=True)
                command = invoked.call_args.args[0]
                self.assertEqual(command[command.index("--resume") + 1], "session-example")
                self.assertNotIn("--session-id", command)
            self.assertEqual(run_evals.observed_session_ids(returned.stdout), ["session-example"])

    def test_spacing_fixture_oracle_preserves_multiline_strings_and_method(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_evals.materialize_repo({"fixture": "comment_spacing"}, root, "baseline", "mock")
            completed = subprocess.run([sys.executable, "analysis.py"], cwd=root, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout.strip(), "retained=2 mean_uv=1.000")
            result = graders.outcome_checks(root, {"outcome": "comment_spacing"}, {})
            self.assertIs(result["pass"], True, result)
            shell = root / "run.sh"
            shell.write_text(shell.read_text(encoding="utf-8").replace("Shell record\n#", "Shell record\n\n#"), encoding="utf-8")
            result = graders.outcome_checks(root, {"outcome": "comment_spacing"}, {})
            self.assertIs(result["pass"], False)
            self.assertTrue(any("Shell literal" in failure for failure in result["failures"]))

    def test_final_source_evidence_excludes_artifacts_and_marks_truncation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative, content in {"README.md": "Data documentation", "stages/analyze.py": "x = 1\n" * 20,
                                      "configs/method.toml": "floor = 0.5", "artifacts/run/readme.md": "payload noise",
                                      ".claude/skills/scientific-coding/SKILL.md": "installed skill"}.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            evidence = graders.source_evidence(root)
            self.assertEqual({item["path"] for item in evidence["files"]}, {"README.md", "stages/analyze.py", "configs/method.toml"})
            excerpt = graders.source_excerpt(evidence, per_file=10, total=15)
            self.assertIn("TRUNCATED FILE", excerpt)
            self.assertIn("omitted_files", excerpt)
            self.assertIn("stages/analyze.py", excerpt)

    def test_created_pipeline_has_independent_numeric_and_exclusion_oracle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            results = root / "results"
            results.mkdir()
            summary = {"counts": {"control": 5, "treatment": 6}, "means_uv": {"control": 1.2, "treatment": 1.35}, "difference_uv": 0.15}
            (results / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
            (results / "exclusions.csv").write_text("trial_id,condition,amplitude_uv,reason\ncontrol-001,control,0.2,below 0.5 uV\n", encoding="utf-8")
            (results / "results.svg").write_text('<svg><text>control treatment</text></svg>', encoding="utf-8")
            self.assertIs(graders.outcome_checks(root, {"outcome": "created_pipeline"}, {})["pass"], True)
            summary["difference_uv"] = -0.15
            (results / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
            self.assertIs(graders.outcome_checks(root, {"outcome": "created_pipeline"}, {})["pass"], False)

    def test_non_pipeline_fixture_keeps_supplied_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_evals.materialize_repo({"fixture": "plot_scientific_computation"}, root, "baseline", "mock")
            self.assertTrue((root / "artifacts/analysis_result/run_001/accuracy_by_subject.csv").is_file())

    def test_no_run_is_a_positive_outcome_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.assertIs(graders.outcome_checks(Path(temporary), {"outcome": "continuous"}, {})["pass"], False)

    def test_actual_pipeline_and_boundary_probes_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_evals.materialize_repo({"fixture": "minimal_pipeline"}, root, "baseline", "mock")
            result = subprocess.run([sys.executable, "pipeline.py"], cwd=root, env=run_evals.execution_env(), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            outcome = graders.outcome_checks(root, {"outcome": "continuous", "probe_boundaries": True}, {})
            self.assertIs(outcome["pass"], True, outcome)
            diagnostic = root / "artifacts/run_diagnostic_rejection"
            diagnostic.mkdir()
            (diagnostic / "pipeline_config.toml").write_text("# Rejection demonstration\n", encoding="utf-8")
            outcome = graders.outcome_checks(root, {"outcome": "continuous", "probe_boundaries": True}, {})
            self.assertIs(outcome["pass"], True, outcome)
            self.assertEqual(outcome["diagnostic_runs"][0]["run"], diagnostic.name)

    def test_diagnostic_runs_without_a_complete_primary_run_never_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "artifacts/run_only_diagnostic").mkdir(parents=True)
            outcome = graders.outcome_checks(root, {"outcome": "continuous", "probe_boundaries": True}, {})
            self.assertIs(outcome["pass"], False)

    def test_initial_run_snapshot_detects_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_evals.materialize_repo({"fixture": "minimal_pipeline", "initial_run": True}, root, "baseline", "mock")
            before = run_evals.artifact_snapshot(root)
            modified = root / next(iter(before))
            modified.write_bytes(b"changed")
            outcome = graders.outcome_checks(root, {"outcome": "continuous"}, before)
            self.assertTrue(any("changed or disappeared" in failure for failure in outcome["failures"]))


class DocstringLayoutTests(unittest.TestCase):
    source = '''"""
按给定阈值拆分试次。

原始行 --> 阈值筛选 --> 保留与排除
阈值配置 ------^
"""


def split(rows: list[dict], floor_uv: float) -> tuple[list, list]:
    """将可信试次拆分成保留和排除两组。

    参数
    ----
    rows : list[dict]
        已加载的试次，保持原输入顺序。

        amplitude_uv : float
            单条振幅，单位微伏。

    floor_uv : float
        保留振幅下限，单位微伏。

    返回
    ----
    retained : list[dict]
        满足下限的记录，相对顺序不变。

    excluded : list[dict]
        低于下限的记录，相对顺序不变。

    处理过程
    --------
    1. 通过第一次列表推导获得保留行。
    2. 通过第二次列表推导获得排除行。

    副作用
    ------
    无文件读写，不修改输入列表。
    """
    return ([r for r in rows if r["amplitude_uv"] >= floor_uv],
            [r for r in rows if r["amplitude_uv"] < floor_uv])
'''

    def check_source(self, source):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "analysis.py").write_text(source, encoding="utf-8")
            return layout_checks.check_layout(root, {"analysis.py": {"split": {
                "return_items": 2, "fields": {"参数": ["amplitude_uv"]}}}})

    def test_valid_layout_is_accepted_but_not_claimed_semantically_proven(self):
        checked = self.check_source(self.source)
        self.assertIs(checked["pass"], True, checked)
        self.assertIn("不证明", checked["limits"])

    def test_headings_alone_cannot_hide_packed_parameters_or_returns(self):
        packed = self.source.replace("floor_uv : float\n        保留振幅下限，单位微伏。",
                                     "floor_uv : float 保留振幅下限，单位微伏。")
        checked = self.check_source(packed)
        self.assertIs(checked["pass"], False)
        self.assertTrue(any("floor_uv" in item for item in checked["failures"]))
        packed_returns = self.source.replace("excluded : list[dict]", "排除列表也在上一项中说明")
        self.assertIs(self.check_source(packed_returns)["pass"], False)

    def test_wrong_heading_order_and_missing_item_blank_are_rejected(self):
        swapped = self.source.replace("    返回\n", "    TEMP\n").replace("    处理过程\n", "    返回\n").replace("    TEMP\n", "    处理过程\n")
        self.assertIs(self.check_source(swapped)["pass"], False)
        crowded = self.source.replace("单位微伏。\n\n    floor_uv", "单位微伏。\n    floor_uv")
        self.assertIs(self.check_source(crowded)["pass"], False)

    def test_module_opening_line_and_actual_nested_paths_are_checked(self):
        self.assertIs(self.check_source(self.source.replace('"""\n按给定', '"""按给定', 1))["pass"], False)
        failures = []
        rows = layout_checks.entries(["summary : dict", "    汇总。", "", "    counts : dict", "        计数。", "", "        control : int", "            对照数量。"], "sample", failures)
        self.assertEqual(rows[-1]["path"], "summary.counts.control")
        self.assertEqual(failures, [])

    def test_real_skill_template_accepts_field_bullets_and_vertical_flowchart(self):
        template = (EVALS.parent / "templates/stage_header.md").read_text(encoding="utf-8")
        source = template.split("```python\n", 1)[1].split("```", 1)[0]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "analysis.py"
            path.write_text(source, encoding="utf-8")
            specification = {"analysis.py": {"summarize_amplitudes": {
                "return_items": 2, "fields": {"返回": ["count", "mean_uv"]}}}}
            self.assertIs(layout_checks.check_layout(root, specification)["pass"], True)
            path.write_text(source.replace("+<--", "配置传入"), encoding="utf-8")
            self.assertIs(layout_checks.check_layout(root, specification)["pass"], True)

    def test_nested_bullet_fields_support_hierarchy_and_explicit_paths(self):
        failures = []
        rows = layout_checks.entries(["summary : dict", "    汇总。", "    - groups : dict，包含两组。",
                                      "        - control : dict，对照。", "            - n_trials：int，计数。",
                                      "    - contrast.peak_uv : list[float]，峰值。"], "sample", failures)
        self.assertEqual(rows[3]["path"], "summary.groups.control.n_trials")
        self.assertEqual(rows[4]["path"], "summary.contrast.peak_uv")
        self.assertEqual(failures, [])

    def test_shared_mapping_goes_to_semantics_but_missing_return_fields_still_fail(self):
        source = self.source.replace("满足下限的记录，相对顺序不变。", "满足下限的记录，相对顺序不变。\n        - counts : dict[str, int]，control 和 treatment 的试次数。")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "analysis.py"
            path.write_text(source, encoding="utf-8")
            specification = {"analysis.py": {"split": {"return_items": 2,
                "fields": {"返回": ["counts.control", "counts.treatment"]}}}}
            checked = layout_checks.check_layout(root, specification)
            self.assertIs(checked["pass"], True, checked)
            self.assertEqual(len(checked["semantic_review_required"]), 2)
            path.write_text(self.source, encoding="utf-8")
            self.assertIs(layout_checks.check_layout(root, specification)["pass"], False)


if __name__ == "__main__":
    unittest.main()
