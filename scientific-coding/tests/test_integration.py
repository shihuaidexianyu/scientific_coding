"""
在隔离副本验证示例的科学结果、来源、日志、失败与指定暂停。

文件流程
--------
最小示例 + configs/*.toml --> 临时副本 --> 实际运行与反例 --> unittest 结果

输入为 examples/minimal_pipeline 及其契约、科学和编排 TOML。
每个测试独立创建临时目录，运行后核对数值、文件哈希、状态与日志；
只生成临时科学产物和诊断，清理范围由 TemporaryDirectory 管理。
"""
from concurrent.futures import ThreadPoolExecutor
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
        shutil.copytree(EXAMPLE, self.work, ignore=shutil.ignore_patterns("artifacts", "executions", "__pycache__"))
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
        record = json.loads(next((self.work / "executions/index").glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "paused")
        self.assertEqual(record["exit_code"], 0)
        self.assertEqual(record["progress"]["current_stage"], "preprocess")

    def test_external_tamper_is_rejected_at_entry(self):
        run = self.run_pipeline()
        data = run / "processed_trials/data/processed_trials.csv"
        data.write_text(data.read_text(encoding="utf-8").replace("control-001", "control-999"), encoding="utf-8")
        path = (run / "processed_trials").relative_to(self.work).as_posix()
        config = self.work / "configs/pipeline.toml"
        config.write_text(config.read_text(encoding="utf-8").replace('processed_artifact = ""', f'processed_artifact = "{path}"'), encoding="utf-8")
        result = self.command("pipeline.py")
        self.assertNotEqual(result.returncode, 0)
        records = [json.loads(p.read_text(encoding="utf-8")) for p in (self.work / "executions/index").glob("*.json")]
        failed = next(record for record in records if record["status"] == "failed")
        self.assertEqual(failed["exit_code"], result.returncode)
        self.assertEqual(failed["progress"]["current_stage"], "load_processed")
        log = Path(failed["log_path"]).read_text(encoding="utf-8")
        self.assertIn("Tracked content differs", log)
        self.assertIn("Traceback (most recent call last)", log)

    def test_execution_success_and_parallel_index_preserve_each_attempt(self):
        """验证并发完成的来源、阶段与独立索引，并确认再运行不改旧记录。

        参数
        ----
        self : PipelineTests
            含隔离示例目录与子进程环境的测试实例。

        返回
        ----
        None
            断言每个完成状态、实际日志和记录路径均一致。

        处理过程
        --------
        1. 并发执行三次，核对各自记录，再运行一次比较旧文件哈希。

        副作用
        ------
        只在本测试临时目录运行和保存文件。
        """

        with ThreadPoolExecutor(max_workers=3) as workers:
            outputs = list(workers.map(lambda _: self.command("pipeline.py"), range(3)))
        self.assertTrue(all(output.returncode == 0 for output in outputs))
        paths = list((self.work / "executions/index").glob("*.json"))
        self.assertEqual(len(paths), 3)
        result_paths = set()
        for path in paths:
            record = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(record, json.loads(Path(record["record_path"]).read_text(encoding="utf-8")))
            self.assertEqual(record["status"], "succeeded")
            self.assertEqual(record["exit_code"], 0)
            self.assertLess(record["started_at_utc"], record["finished_at_utc"])
            self.assertGreater(record["wall_time_s"], 0)
            progress = record["progress"]
            self.assertEqual([stage["name"] for stage in progress["stages"]],
                             ["setup", "acquire_data", "preprocess", "analyze", "figure"])
            self.assertTrue(all(stage["wall_time_s"] > 0 for stage in progress["stages"]))
            resources = progress["resources"]
            self.assertGreaterEqual(resources["cpu_time_s"], 0)
            self.assertTrue(resources["peak_ram_bytes"] is None or resources["peak_ram_bytes"] > 0)
            self.assertTrue(resources["ram_note"])
            self.assertIsNone(resources["peak_vram_bytes"])
            self.assertIn("不使用 GPU", resources["vram_note"])
            self.assertIn("Completed pipeline", Path(record["log_path"]).read_text(encoding="utf-8"))
            result_paths.add(progress["result_path"])
        self.assertEqual(len(result_paths), 3)
        before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in (self.work / "executions").rglob("*") if path.is_file()}
        self.run_pipeline()
        self.assertTrue(all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
                            for path, digest in before.items()))
        self.assertEqual(len(list((self.work / "executions/index").glob("*.json"))), 4)

    def test_configuration_failure_is_recorded_before_any_artifact(self):
        """验证早期配置错误仍保留尝试、异常和真实退出码。

        参数
        ----
        self : PipelineTests
            只操作隔离示例副本的测试实例。

        返回
        ----
        None
            对启动后的失败证据做断言。

        处理过程
        --------
        1. 传入不存在的配置，核对 setup 失败及完整异常日志。

        副作用
        ------
        生成一个失败尝试，无科学结果文件。
        """

        result = self.command("pipeline.py", "missing.toml")
        self.assertNotEqual(result.returncode, 0)
        record = json.loads(next((self.work / "executions/index").glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["exit_code"], result.returncode)
        self.assertEqual(record["progress"]["current_stage"], "setup")
        self.assertIsNone(record["progress"]["result_path"])
        self.assertIn("FileNotFoundError", Path(record["log_path"]).read_text(encoding="utf-8"))
        self.assertFalse((self.work / "artifacts").exists())

    def test_log_keeps_native_child_output_and_traceback_without_truncation(self):
        """验证文件描述符输出、子进程输出及长日志均被保存。

        参数
        ----
        self : PipelineTests
            拥有隔离目录和 UTF-8 子进程环境的实例。

        返回
        ----
        None
            核验完整输出字节与非零退出。

        处理过程
        --------
        1. 在记录器下输出长文本、原生 stderr 和孙进程输出，再抛出异常。

        副作用
        ------
        在临时目录保存刻意失败的日志，不改变科学示例。
        """

        task = "import os,subprocess,sys; print('A'*180000); os.write(2,b'NATIVE_STDERR\\n'); subprocess.run([sys.executable,'-c',\"print('GRANDCHILD')\"],check=True); raise RuntimeError('expected failure')"
        code = f"import sys; from pathlib import Path; from execution import execute; status,_=execute([sys.executable,'-u','-c',{task!r}],Path('executions'),Path.cwd(),{{'experiment_id':'failure_probe'}}); sys.exit(status)"
        result = self.command("-c", code)
        self.assertEqual(result.returncode, 1)
        record = json.loads(next((self.work / "executions/index").glob("*.json")).read_text(encoding="utf-8"))
        log = Path(record["log_path"]).read_text(encoding="utf-8")
        self.assertIn("A" * 180000, log)
        self.assertIn("NATIVE_STDERR", log)
        self.assertIn("GRANDCHILD", log)
        self.assertIn("Traceback (most recent call last)", log)
        self.assertIn("RuntimeError: expected failure", log)
        self.assertEqual(record["exit_code"], 1)
        self.assertIsNone(record["progress"])

    def test_failed_parameters_and_unparseable_config_keep_exact_sources(self):
        """验证发布前失败也能还原精确配置和启动源码。

        参数
        ----
        self : PipelineTests
            含临时副本的实例，改动不会影响仓库示例。

        返回
        ----
        None
            核验失败输入的实际字节和 SHA-256。

        处理过程
        --------
        1. 分别构造非法科学参数和无法解析的 TOML，运行后读取失败来源快照。

        副作用
        ------
        在临时项目内修改配置并生成两次失败记录。
        """

        config = self.work / "configs/acquire_data.toml"
        for content in (config.read_bytes().replace(b"= 40", b"= 1"), b"invalid = [\r\n"):
            config.write_bytes(content)
            before = set((self.work / "executions/index").glob("*.json"))
            result = self.command("pipeline.py")
            self.assertNotEqual(result.returncode, 0)
            path = (set((self.work / "executions/index").glob("*.json")) - before).pop()
            record = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(record["progress"]["current_stage"], "acquire_data")
            attempt = Path(record["record_path"]).parent
            entries = [json.loads((attempt / name).read_text(encoding="utf-8")) for name in record["config_snapshots"]]
            entry = next(entry for entry in entries if Path(entry["origin"]) == config)
            self.assertEqual(entry["sha256"], hashlib.sha256(content).hexdigest())
            self.assertEqual((attempt / entry["snapshot"]).read_bytes(), content)
            source = next(entry for entry in record["code_at_launch"] if entry["origin"].endswith("acquire_data.py"))
            self.assertEqual((attempt / source["snapshot"]).read_bytes(), (self.work / "stages/acquire_data.py").read_bytes())
            self.assertFalse((Path(record["progress"]["result_path"]) / "raw_trials").exists())

    def test_launch_failure_does_not_invent_a_child_exit_code(self):
        """验证未能创建子进程时不伪造其退出码。

        参数
        ----
        self : PipelineTests
            含隔离工作目录的测试实例。

        返回
        ----
        None
            确认启动器返回失败，记录区分启动失败与子进程失败。

        处理过程
        --------
        1. 启动不存在的可执行文件，检查 launch_failed 和异常日志。

        副作用
        ------
        只保存本次刻意构造的失败记录。
        """

        result = self.command("-c", "import sys; from pathlib import Path; from execution import execute; status,_=execute([str(Path('missing_program').resolve())],Path('executions'),Path.cwd(),{}); sys.exit(status)")
        self.assertEqual(result.returncode, 1)
        record = json.loads(next((self.work / "executions/index").glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "launch_failed")
        self.assertIsNone(record["exit_code"])
        self.assertIn("FileNotFoundError", Path(record["log_path"]).read_text(encoding="utf-8"))

    def test_external_binding_survives_downstream_failure(self):
        """验证复用外部结果后失败仍保留已建立的来源绑定。

        参数
        ----
        self : PipelineTests
            含隔离结果与配置的测试实例。

        返回
        ----
        None
            确认原 manifest 身份完整出现在新失败记录中。

        处理过程
        --------
        1. 生成有效结果，将其作为外部输入，再使分析参数失败。

        副作用
        ------
        只改变临时配置，保留第一次结果与失败尝试。
        """

        first = self.run_pipeline()
        source = first / "processed_trials"
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        pipeline_config = self.work / "configs/pipeline.toml"
        pipeline_config.write_text(pipeline_config.read_text(encoding="utf-8").replace(
            'processed_artifact = ""', f'processed_artifact = "{source.as_posix()}"'), encoding="utf-8")
        analysis_config = self.work / "configs/analyze.toml"
        analysis_config.write_text(analysis_config.read_text(encoding="utf-8").replace("= 2000", "= 1"), encoding="utf-8")
        result = self.command("pipeline.py")
        self.assertNotEqual(result.returncode, 0)
        records = [json.loads(path.read_text(encoding="utf-8")) for path in (self.work / "executions/index").glob("*.json")]
        failed = next(record for record in records if record["status"] == "failed")
        self.assertEqual(failed["progress"]["current_stage"], "analyze")
        binding = failed["input_bindings"][0]
        self.assertEqual(binding["artifact_hash"], manifest["artifact_hash"])
        self.assertEqual(binding["manifest_hash"], manifest["manifest_hash"])
        self.assertEqual(binding["role"], "ProcessedTrials@1")

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
