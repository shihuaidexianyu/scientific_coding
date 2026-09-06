"""
在隔离副本实际执行运行记录案例，独立检查数值、失败日志与并发保留。

生成仓库 --> 临时副本 + 新输入 --> 真实 CLI --> JSON 索引/日志/结果 --> 检查证据

不导入被测科学函数，也不把模板字段存在当成成功。返回值保留原始日志和记录，
由上层 harness 保存为 outcomes.json；中文说明与估算质量交由语义评读。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "execution_records"
IGNORED = {".git", "__pycache__", ".venv", "venv", "node_modules"}


def digest(path: Path) -> str:
    """读取待比较文件的 SHA-256；此操作只属于离线评测。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(root: Path) -> dict[str, str]:
    """记录原仓库文件字节，确认探针没有改动作者源码或已有产物。"""
    result = {}
    for directory, children, names in os.walk(root):
        children[:] = [name for name in children if name not in IGNORED and not name.startswith(".")]
        for name in names:
            path = Path(directory) / name
            if not path.is_symlink():
                result[path.relative_to(root).as_posix()] = digest(path)
    return result


def invoke(project: Path, arguments: list[str], environment: dict) -> dict:
    """执行真实入口并保留退出码、完整终端输出与外部墙钟时间；超时结束本进程组。"""
    started = time.perf_counter()
    command = [sys.executable, "-u", str(project / "analysis.py"), *arguments]
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as error:
        child = subprocess.Popen(command, cwd=project, env=environment, stdout=output, stderr=error,
                                 start_new_session=os.name != "nt",
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        timed_out = False
        try:
            child.wait(timeout=20)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW, check=False)
            else:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            child.wait()
        output.seek(0)
        error.seek(0)
        return {"command": command, "exit_code": child.returncode, "timed_out": timed_out,
                "observed_wall_time_s": time.perf_counter() - started,
                "stdout": output.read().decode("utf-8", errors="replace"),
                "stderr": error.read().decode("utf-8", errors="replace")}


def make_input(directory: Path, number: int, kind: str) -> dict:
    """建立不同形状和阈值的新数据，并用独立列表算术生成预期结果。"""
    directory.mkdir(parents=True)
    threshold = 0.25 + number / 8
    control = [threshold - 0.125, threshold, threshold + 0.25, threshold + 1.75]
    treatment = [threshold - 0.5, threshold, threshold + 0.75,
                 threshold + 1.0, threshold + 2.25, threshold + number / 16]
    lines = ["trial_id,condition,amplitude_uv"]
    lines += [f"c{index},control,{value}" for index, value in enumerate(control)]
    lines += [f"t{index},treatment,{value}" for index, value in enumerate(treatment)]
    data = directory / "trials.csv"
    data.write_text("\n".join(lines) + "\n", encoding="utf-8")
    config = directory / "config.toml"
    text = f'[input]\npath = "trials.csv"\n[analysis]\nminimum_uv = {threshold}\n'
    if kind == "malformed":
        text += "broken = [\n"
    config.write_text(text, encoding="utf-8")
    retained_c = [value for value in control if value >= threshold]
    retained_t = [value for value in treatment if value >= threshold]
    mean_c = sum(retained_c) / len(retained_c)
    mean_t = sum(retained_t) / len(retained_t)
    return {"number": number, "kind": kind, "config": str(config), "input": str(data),
            "token": uuid.uuid4().hex, "config_sha256": digest(config), "input_sha256": digest(data),
            "expected": {"n_control": len(retained_c), "n_treatment": len(retained_t),
                         "control_mean_uv": mean_c, "treatment_mean_uv": mean_t,
                         "difference_uv": mean_t - mean_c}}


def descendants(value):
    """遍历 JSON 的字典/列表节点，使来源和资源的内部组织保持自由。"""
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from descendants(child)
    elif isinstance(value, list):
        for child in value:
            yield from descendants(child)


def find_field(value: dict, name: str):
    """查找顶层或 progress 等嵌套结构中的约定字段。"""
    for node in descendants(value):
        if isinstance(node, dict) and name in node:
            return True, node[name]
    return False, None


def finite_number(value) -> bool:
    """拒绝布尔值、NaN 和无穷，接受 JSON 中正常的实数。"""
    return type(value) in (int, float) and math.isfinite(value)


def locate(records: Path, value, project: Path) -> Path:
    """按查询协议解析路径，并拒绝指向原仓库或隔离目录之外的结果。"""
    if not isinstance(value, str) or not value:
        raise ValueError("索引缺少非空文件路径")
    path = Path(value)
    resolved = (path if path.is_absolute() else records / path).resolve()
    if not resolved.is_relative_to(project.resolve()):
        raise ValueError("索引文件路径越过隔离副本")
    if not resolved.is_file():
        raise ValueError("索引引用的文件不存在：" + str(resolved))
    return resolved


def query(project: Path, records: Path, environment: dict, evidence: list | None = None) -> tuple[list, dict]:
    """调用用户可用的查询 CLI，不从目录名字猜测运行是否成功。"""
    result = invoke(project, ["--list-runs", "--records", str(records)], environment)
    if evidence is not None:
        evidence.append(result)
    if result["exit_code"] != 0 or result["timed_out"]:
        raise ValueError("查询 CLI 没有正常完成：" + json.dumps(result, ensure_ascii=False))
    rows = json.loads(result["stdout"])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("查询 stdout 不是 JSON 对象数组")
    ids = [row.get("attempt_id") for row in rows]
    if any(not isinstance(item, str) or not item for item in ids) or len(set(ids)) != len(ids):
        raise ValueError("查询索引缺少唯一 attempt_id")
    return rows, result


def inspect_run(project: Path, records: Path, row: dict, sample: dict,
                invocation: dict, source_hash: str, receipt_dir: Path) -> dict:
    """对一次真实运行核对科学数值、生命周期、来源和完整输出，返回逐项证据。"""
    failures = []
    record_path = locate(records, row.get("record_path"), project)
    log_path = locate(records, row.get("log_path"), project)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise ValueError("执行记录不是 JSON 对象")
    log = log_path.read_text(encoding="utf-8", errors="replace")
    success = sample["kind"] == "success"
    expected_status = "succeeded" if success else "failed"
    for key, expected in (("attempt_id", row["attempt_id"]), ("status", expected_status),
                          ("exit_code", invocation["exit_code"])):
        if record.get(key) != expected or row.get(key) != expected:
            failures.append(f"记录/查询的 {key} 与实际执行不一致")
    if invocation["timed_out"] or (invocation["exit_code"] == 0) != success:
        failures.append("正常/失败 CLI 的真实退出状态错误或超时")
    try:
        start = datetime.fromisoformat(record["started_at_utc"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(record["finished_at_utc"].replace("Z", "+00:00"))
        elapsed = record["wall_time_s"]
        if start.utcoffset() != timedelta(0) or end.utcoffset() != timedelta(0) or end < start:
            raise ValueError("起止时间不是有序 UTC")
        if not finite_number(elapsed) or elapsed <= 0 or elapsed > invocation["observed_wall_time_s"] + 1:
            raise ValueError("墙钟耗时与真实外部观察不符")
        if abs((end - start).total_seconds() - elapsed) > max(1, elapsed / 2):
            raise ValueError("起止时刻与耗时明显矛盾")
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        failures.append("生命周期：" + str(error))

    # 字段存在之外，还核对测量数值/缺失原因和真正完成或失败的阶段。
    for metric in ("cpu_time_s", "peak_ram_bytes"):
        found, value = find_field(record, metric)
        reasons = [text for node in descendants(record) if isinstance(node, dict)
                   for key, text in node.items() if ("note" in key or "reason" in key)
                   and isinstance(text, str) and text.strip()]
        if not found or (value is None and not reasons) or (value is not None and
                (not finite_number(value) or value < 0 or (metric == "peak_ram_bytes" and value == 0))):
            failures.append(metric + " 缺少有效测量或明确的未采集原因")
    _, stages = find_field(record, "stages")
    if not isinstance(stages, list) or not stages:
        failures.append("未保留主要阶段时间")
    else:
        for stage in stages:
            if not isinstance(stage, dict) or not stage.get("name") or not finite_number(stage.get("wall_time_s")) or stage["wall_time_s"] < 0:
                failures.append("阶段缺少名称或真实耗时")
                break
        if not success and not any(isinstance(stage, dict) and stage.get("status") == "failed" for stage in stages):
            failures.append("失败阶段没有标记为 failed")

    # 来源可在同一尝试的独立 JSON 文件中，不能只照抄模板或另一次任务的测量值。
    documents = [record]
    for path in record_path.parent.rglob("*.json"):
        try:
            documents.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    values = [node for document in documents for node in descendants(document) if isinstance(node, str)]
    expected_hashes = {"源码": source_hash, "配置": sample["config_sha256"]}
    if sample["kind"] != "malformed":
        expected_hashes["输入 CSV"] = sample["input_sha256"]
    for label, wanted in expected_hashes.items():
        if wanted not in values and "sha256:" + wanted not in values:
            failures.append(label + " 的实际 SHA-256 未保留")
    version = ".".join(str(part) for part in sys.version_info[:3])
    if not any(version in value for value in values):
        failures.append("没有记录实际 Python 版本")

    token = sample["token"]
    if sample["kind"] != "malformed":
        expected_messages = ["PARENT_STDOUT:" + token, "PARENT_STDERR:" + token]
        expected_messages += [f"CHILD_{stream}:{token}:{number}"
                              for stream in ("STDOUT", "STDERR") for number in range(24)]
        absent = [message for message in expected_messages if message not in log]
        if absent:
            failures.append(f"完整日志缺少 {len(absent)} 条父/子进程 stdout/stderr 消息")
        if not (receipt_dir / (token + ".json")).is_file():
            failures.append("没有实际调用已有诊断子进程")
    if not success and ("Traceback" not in log or
                        (sample["kind"] == "runtime_error" and "intentional_after_read:" + token not in log)):
        failures.append("失败日志没有完整 traceback 或本次真实错误")

    scientific_result = None
    protected = {str(record_path): digest(record_path), str(log_path): digest(log_path)}
    if success:
        result_path = locate(records, row.get("result_path"), project)
        scientific_result = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(scientific_result, dict):
            failures.append("科学结果不是 JSON 对象")
        else:
            for key, wanted in sample["expected"].items():
                actual = scientific_result.get(key)
                if not finite_number(actual) or not math.isclose(actual, wanted, rel_tol=1e-12, abs_tol=1e-12):
                    failures.append(f"独立数值 oracle 不一致：{key}")
        protected[str(result_path)] = digest(result_path)
    return {"pass": not failures, "failures": failures, "attempt_id": row["attempt_id"],
            "sample": sample, "invocation": invocation, "record": record, "log": log,
            "scientific_result": scientific_result, "protected_files": protected}


def execution_outcome(workdir: Path, case: dict) -> dict:
    """在独立副本完成 entry 或 batch 探针，所有失败保留为证据而不修改原产物。"""
    failures, runs, queries, invocations_evidence = [], [], [], []
    before = fingerprint(workdir)
    if not (workdir / "analysis.py").is_file():
        return {"pass": False, "failures": ["缺少 analysis.py"]}
    child_path = workdir / "diagnostic_child.py"
    if not child_path.is_file() or digest(child_path) != digest(FIXTURE / child_path.name):
        return {"pass": False, "failures": ["已有诊断子程序没有按约定逐字保留"]}
    try:
        with tempfile.TemporaryDirectory(prefix="execution-eval-") as temporary:
            project = Path(temporary) / "project"
            shutil.copytree(workdir, project, ignore=shutil.ignore_patterns(*IGNORED))
            records, inputs, receipts = project / "probe_records", project / "probe_inputs", project / "probe_receipts"
            receipts.mkdir()
            environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
            source_hash = digest(project / "analysis.py")

            # 只在临时副本给受保护子程序追加观察收据，证明确实运行了该子进程。
            child = project / "diagnostic_child.py"
            child.write_text(child.read_text(encoding="utf-8") +
                             "\nfrom pathlib import Path\nPath(" + repr(str(receipts)) +
                             ").joinpath(token + '.json').write_text('true', encoding='utf-8')\n", encoding="utf-8")

            def launch(sample):
                arguments = ["--config", sample["config"], "--records", str(records), "--event-token", sample["token"]]
                if sample["kind"] == "runtime_error":
                    arguments.append("--fail-after-read")
                result = invoke(project, arguments, environment)
                invocations_evidence.append({"sample": sample, "invocation": result})
                return result

            def collect(samples, invocations, previous_ids):
                rows, _ = query(project, records, environment, queries)
                fresh = [row for row in rows if row["attempt_id"] not in previous_ids]
                if len(fresh) != len(samples) or len(rows) != len(previous_ids) + len(samples):
                    raise ValueError("查询索引丢失/重复了真实尝试，或查询本身创建了尝试")
                remaining = list(fresh)
                for sample, invocation in zip(samples, invocations):
                    matches = []
                    for row in remaining:
                        record_path = locate(records, row.get("record_path"), project)
                        # 命令或来源中应能关联实际配置；日志 token 也可作为对应证据。
                        text = record_path.read_text(encoding="utf-8")
                        if sample["token"] in text or sample["config"] in text or sample["config"].replace("\\", "\\\\") in text:
                            matches.append(row)
                    if len(matches) != 1:
                        raise ValueError("不能把查询条目唯一对应到本次命令/配置")
                    row = matches[0]
                    remaining.remove(row)
                    checked = inspect_run(project, records, row, sample, invocation, source_hash, receipts)
                    runs.append(checked)
                    failures.extend(f"{sample['kind']}:{sample['number']}: {item}" for item in checked["failures"])
                return {row["attempt_id"] for row in rows}

            # 先建立真实历史结果，再观察后续运行是否改写它；共享索引本身允许追加。
            seed = make_input(inputs / "seed", 1, "success")
            seen = collect([seed], [launch(seed)], set())
            protected = dict(runs[0]["protected_files"])
            kinds = ("success", "success", "malformed", "runtime_error") if case.get("execution_variant") == "batch" else ("success", "malformed", "runtime_error")
            samples = [make_input(inputs / f"case_{index}", index + 3, kind) for index, kind in enumerate(kinds)]
            if case.get("execution_variant") == "batch":
                with ThreadPoolExecutor(max_workers=4) as pool:
                    invocations = list(pool.map(launch, samples))
                seen = collect(samples, invocations, seen)
            else:
                for sample in samples:
                    seen = collect([sample], [launch(sample)], seen)
            changed = [name for name, wanted in protected.items() if not Path(name).is_file() or digest(Path(name)) != wanted]
            if changed:
                failures.append("后续尝试改写或删除历史日志/记录/结果：" + ", ".join(changed))
            final_rows, _ = query(project, records, environment, queries)
            if {row["attempt_id"] for row in final_rows} != seen:
                failures.append("第二次只读查询改变或遗漏了索引")
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        failures.append(type(error).__name__ + ": " + str(error))
    unchanged = before == fingerprint(workdir)
    if not unchanged:
        failures.append("探针期间原仓库的源码或已有产物发生变化")
    return {"pass": not failures, "failures": failures, "probe_version": "execution-v1",
            "variant": case.get("execution_variant", "entry"), "runs": runs, "queries": queries,
            "invocations": invocations_evidence,
            "original_files_unchanged": unchanged,
            "dimensions": {"execution_records": {"pass": not failures, "failures": failures}},
            "scope": "真实 CLI、独立数值、早期配置失败、完整父/子输出、失败堆栈、来源、资源字段和历史保留；说明与估算准确性由 rubric 判定"}
