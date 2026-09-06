"""运行记录评测器的正负回归：真实执行、独立数值、失败证据与并发历史保留。"""

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "evals"))
import execution_checks


REFERENCE = '''"""给测试科学入口加一份真实执行记录，供评测器的正向回归使用。"""
import argparse
import json
import os
from pathlib import Path
import sys
import tomllib
from execution import Progress, execute, save_snapshot
from science import compute

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--config", type=Path, default=Path("config.toml"))
parser.add_argument("--records", type=Path, default=Path("records"))
parser.add_argument("--event-token", default="example")
parser.add_argument("--fail-after-read", action="store_true")
parser.add_argument("--list-runs", action="store_true")
parser.add_argument("--worker", action="store_true")
args = parser.parse_args()
if args.list_runs:
    rows = []
    for path in sorted((args.records / "index").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        rows.append({key: record[key] for key in ("attempt_id", "status", "exit_code", "record_path", "log_path")})
        rows[-1]["result_path"] = (record.get("progress") or {}).get("result_path")
    print(json.dumps(rows))
elif not args.worker:
    status, attempt = execute([sys.executable, str(ROOT / "analysis.py"), *sys.argv[1:], "--worker"],
                              args.records, ROOT, {"source_paths": [str(ROOT / "analysis.py")]})
    raise SystemExit(status)
else:
    attempt = Path(os.environ["SCIENTIFIC_EXECUTION_DIR"])
    progress = Progress(attempt)
    progress.enter("read")
    try:
        content = args.config.read_bytes()
        save_snapshot(attempt, args.config, content, "config_at_read")
        config = tomllib.loads(content.decode("utf-8"))
        data = args.config.parent / config["input"]["path"]
        save_snapshot(attempt, data, data.read_bytes(), "config_at_read")
        progress.enter("compute")
        result = compute(args.config, args.event_token, args.fail_after_read)
        progress.enter("save")
        output = attempt / "result.json"
        output.write_text(json.dumps(result), encoding="utf-8")
        progress.data["result_path"] = str(output)
    except BaseException:
        progress.finish("failed")
        raise
    else:
        progress.finish("succeeded")
'''


class ExecutionEvalTests(unittest.TestCase):
    """每项只构造自身需要的隔离正例或真实缺陷，不覆盖作者已有产物。"""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="execution-eval-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "project"
        shutil.copytree(execution_checks.FIXTURE, self.root)

    def reference(self, replacements=()):
        """用现有已测运行边界建立能执行的正例，支持定点注入缺陷。"""
        (self.root / "analysis.py").rename(self.root / "science.py")
        text = REFERENCE
        for original, new in replacements:
            self.assertIn(original, text)
            text = text.replace(original, new)
        (self.root / "analysis.py").write_text(text, encoding="utf-8")
        shutil.copyfile(SKILL / "examples/minimal_pipeline/execution.py", self.root / "execution.py")

    def assess(self, variant="entry"):
        """调用与远端案例同一评分入口。"""
        return execution_checks.execution_outcome(self.root, {"execution_variant": variant})

    def test_unimplemented_fixture_fails_and_keeps_invocation_after_bad_query(self):
        before = execution_checks.fingerprint(self.root)
        outcome = self.assess()
        self.assertFalse(outcome["pass"])
        self.assertEqual(len(outcome["invocations"]), 1)
        self.assertEqual(outcome["invocations"][0]["invocation"]["exit_code"], 0)
        self.assertIn("PARENT_STDOUT", outcome["invocations"][0]["invocation"]["stdout"])
        self.assertEqual(len(outcome["queries"]), 1)
        self.assertEqual(outcome["queries"][0]["stdout"].strip(), "[]")
        self.assertEqual(before, execution_checks.fingerprint(self.root))

    def test_real_reference_entry_passes_alternate_data_and_both_failures(self):
        self.reference()
        outcome = self.assess()
        self.assertTrue(outcome["pass"], outcome["failures"])
        self.assertEqual(len(outcome["runs"]), 4)
        self.assertEqual([run["record"]["status"] for run in outcome["runs"]],
                         ["succeeded", "succeeded", "failed", "failed"])
        self.assertTrue(outcome["original_files_unchanged"])

    def test_real_reference_parallel_batch_keeps_five_attempts(self):
        self.reference()
        outcome = self.assess("batch")
        self.assertTrue(outcome["pass"], outcome["failures"])
        self.assertEqual(len(outcome["runs"]), 5)
        self.assertEqual(len({run["attempt_id"] for run in outcome["runs"]}), 5)

    def test_fabricated_scientific_result_fails_independent_oracle(self):
        self.reference((("result = compute(args.config, args.event_token, args.fail_after_read)",
                         "result = compute(args.config, args.event_token, args.fail_after_read)\n        result['difference_uv'] = 99"),))
        outcome = self.assess()
        self.assertFalse(outcome["pass"])
        self.assertTrue(any("oracle" in issue for issue in outcome["failures"]), outcome["failures"])

    def test_fake_zero_peak_memory_fails(self):
        self.reference()
        path = self.root / "execution.py"
        text = path.read_text(encoding="utf-8")
        needle = 'self.data["resources"] = resources'
        self.assertIn(needle, text)
        path.write_text(text.replace(needle, 'resources["peak_ram_bytes"] = 0\n        ' + needle), encoding="utf-8")
        outcome = self.assess()
        self.assertFalse(outcome["pass"])
        self.assertTrue(any("peak_ram_bytes" in issue for issue in outcome["failures"]), outcome["failures"])

    def test_missing_early_configuration_identity_fails(self):
        self.reference((("save_snapshot(attempt, args.config, content, \"config_at_read\")", "pass"),))
        outcome = self.assess()
        self.assertFalse(outcome["pass"])
        self.assertTrue(any("配置" in issue and "SHA-256" in issue for issue in outcome["failures"]))

    def test_real_stdout_without_child_stderr_fails(self):
        self.reference()
        path = self.root / "science.py"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("token], check=True)", "token], check=True, stderr=subprocess.DEVNULL)"), encoding="utf-8")
        outcome = self.assess()
        self.assertFalse(outcome["pass"])
        self.assertTrue(any("完整日志缺少" in issue for issue in outcome["failures"]))

    def test_fabricated_child_messages_do_not_replace_actual_child_execution(self):
        self.reference()
        path = self.root / "science.py"
        text = path.read_text(encoding="utf-8")
        original = 'subprocess.run([sys.executable, str(Path(__file__).with_name("diagnostic_child.py")), token], check=True)'
        replacement = ('for number in range(24):\n'
                       '        print(f"CHILD_STDOUT:{token}:{number}", flush=True)\n'
                       '        print(f"CHILD_STDERR:{token}:{number}", file=sys.stderr, flush=True)')
        self.assertIn(original, text)
        path.write_text(text.replace(original, replacement), encoding="utf-8")
        outcome = self.assess()
        self.assertFalse(outcome["pass"])
        self.assertTrue(any("没有实际调用" in issue for issue in outcome["failures"]))
        self.assertFalse(any("完整日志缺少" in issue for issue in outcome["failures"]))

    def test_old_log_mutation_is_detected(self):
        self.reference((("elif not args.worker:\n    status, attempt", "elif not args.worker:\n    for old in (args.records / 'attempts').glob('*/run.log'):\n        old.write_text('overwritten', encoding='utf-8')\n    status, attempt"),))
        outcome = self.assess()
        self.assertFalse(outcome["pass"])
        self.assertTrue(any("历史日志" in issue for issue in outcome["failures"]), outcome["failures"])

    def test_protected_child_edits_are_rejected_without_execution(self):
        path = self.root / "diagnostic_child.py"
        path.write_text(path.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
        outcome = self.assess()
        self.assertFalse(outcome["pass"])
        self.assertIn("逐字保留", outcome["failures"][0])


if __name__ == "__main__":
    unittest.main()
