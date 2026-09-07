"""
编排振幅描述实验：统一参数、必要检查、业务调用、结果与运行记录。

同目录 TOML --> 配置与路径 --> CSV 行 --> 有限性检查
    --> select_trials --> summarize_trials --> result.json
启动/失败/结束 --> runtime_support --> 日志、来源快照、时间与索引

CSV 为 UTF-8，字段 trial_id、amplitude_uv，后者转为微伏浮点数。
所有配置内相对路径以实际 TOML 目录为基准；默认 TOML 与本文件同目录。
输出含保留行、排除 ID/原因、count 和 mean_uv。具体设计见同目录 MD。
"""

# 标准库负责命令行、文件解析和有限数判定。
import argparse
import csv
import io
import math
import os
from pathlib import Path
import sys
import tomllib

# 从脚本位置定位本示例，启动工作目录不改变模块与默认配置位置。
script_location = Path(__file__)
SCRIPT_PATH = script_location.resolve()
PROJECT_ROOT = SCRIPT_PATH.parents[2]
project_root_text = str(PROJECT_ROOT)
sys.path.insert(0, project_root_text)
from runtime_support import Progress, execute, save_snapshot, write_json


def read_trials(path: Path, attempt: Path) -> list[dict]:
    """读取实际 CSV 字节、保存来源，再转换试次振幅。

    参数
    ----
    path : Path
        编排已解析的 CSV 绝对路径，UTF-8，列为 trial_id、amplitude_uv。

    attempt : Path
        本次已建立的运行记录目录，保存快照与 input_bindings。

    返回
    ----
    rows : list[dict]
        按 CSV 原顺序排列，每行含：
        - trial_id：字符串，试次 ID。
        - amplitude_uv：float 转换后的微伏数值，有限性尚未检查。

    处理过程
    --------
    1. 保存读取字节的快照与哈希，再按列名解析并转换振幅。

    副作用
    ------
    读取 CSV，写本次来源记录；读取或解析异常自然传播。
    """

    # 哈希对应本次实际读取的字节，不在下游重新读取或散列。
    content = path.read_bytes()
    binding = save_snapshot(attempt, path, content, "input_at_read")
    bindings_dir = attempt / "input_bindings"
    bindings_dir.mkdir()
    binding_path = bindings_dir / "trials.json"
    write_json(binding_path, binding)

    # 按原行顺序转换科学列，数据检查由调用方下一步完成。
    text = content.decode("utf-8")
    stream = io.StringIO(text)
    reader = csv.DictReader(stream)
    rows = []
    for item in reader:
        amplitude_uv = float(item["amplitude_uv"])
        row = {"trial_id": item["trial_id"], "amplitude_uv": amplitude_uv}
        rows.append(row)
    return rows


def require_finite_values(rows: list[dict], floor_uv: float) -> None:
    """在科学调用前拒绝可被解析器接受的 nan/inf。

    参数
    ----
    rows : list[dict]
        本次读取的试次行，含 trial_id 字符串、amplitude_uv 浮点数。

    floor_uv : float
        实际配置的振幅下限，单位微伏。

    返回
    ----
    None
        数值有限时正常返回，不包装数据或设置已验证标志。

    处理过程
    --------
    1. 检查阈值，再逐行检查实际振幅；错误包含具体试次 ID。

    副作用
    ------
    不修改数据；非有限值抛出 ValueError，交给已有执行记录捕获。
    """

    # 人工编辑可引入 nan/inf，解析器接受它们却会静默影响筛选与均值。
    if not math.isfinite(floor_uv):
        raise ValueError("振幅阈值必须有限")
    for row in rows:
        if not math.isfinite(row["amplitude_uv"]):
            message = f"试次 {row['trial_id']} 的振幅不是有限数"
            raise ValueError(message)


def run(config_path: Path, progress: Progress) -> Path:
    """按本实验顺序读取、筛选、汇总并保存结果。

    参数
    ----
    config_path : Path
        选中 TOML 的绝对路径，节为 input、preprocess、output。
        字段分别为 trials_path、floor_uv、run_root。

    progress : Progress
        本次运行观察器；path 指向尝试目录的 progress.json，
        data 保存当前阶段、阶段时间、状态和 result_path，不控制计算。

    返回
    ----
    result_path : Path
        本次新目录内的 result.json 绝对路径，其内容为：
        - retained：含 trial_id、amplitude_uv 的字典列表。
        - exclusions：含 trial_id、reason 的字典列表。
        - summary：含 count 整数、mean_uv 微伏浮点数的字典。

    处理过程
    --------
    1. 读取一次配置与实际输入，在编排中检查有限性。
    2. 调用筛选及描述性汇总，再保存已计算结果。

    副作用
    ------
    读取 TOML/CSV，写来源、进度与新结果；失败传播，不覆盖旧结果。
    """

    # 业务模块在已被外层记录的工作进程中加载，导入失败也留下堆栈。
    progress.enter("加载方法")
    from stages.amplitudes import select_trials, summarize_trials

    # 参数只读一次，配置来源在解析前保存，错误 TOML 也能追溯。
    attempt = progress.path.parent
    progress.enter("配置与输入")
    content = config_path.read_bytes()
    save_snapshot(attempt, config_path, content, "config_at_read")
    config_text = content.decode("utf-8")
    config = tomllib.loads(config_text)
    progress.data["effective_config"] = config
    config_dir = config_path.parent
    input_name = config["input"]["trials_path"]
    input_location = config_dir / input_name
    input_path = input_location.resolve()
    output_name = config["output"]["run_root"]
    output_location = config_dir / output_name
    output_root = output_location.resolve()
    floor_uv = config["preprocess"]["floor_uv"]
    rows = read_trials(input_path, attempt)

    # 必要检查集中在编排；stage 使用同一份实际参数和输入。
    progress.enter("输入前提")
    require_finite_values(rows, floor_uv)

    # 本实验只有顺序调用，科学业务不接收总配置或执行状态。
    progress.enter("筛选")
    retained, exclusions = select_trials(rows, floor_uv)
    progress.enter("汇总")
    summary = summarize_trials(retained)

    # 计算完成才写结果，新编号避免覆盖；原子文件替换由已有 I/O 负责。
    progress.enter("保存")
    result = {
        "retained": retained,
        "exclusions": exclusions,
        "summary": summary,
    }
    output_dir = output_root / attempt.name
    output_dir.mkdir(parents=True, exist_ok=False)
    result_path = output_dir / "result.json"
    write_json(result_path, result)
    progress.data["result_path"] = str(result_path)
    print(f"保留 {summary['count']} 个试次，均值 {summary['mean_uv']} 微伏")
    return result_path


if __name__ == "__main__":

    # 脚本同目录默认配置，显式路径由命令行选择，不引入第二份参数来源。
    parser = argparse.ArgumentParser(description=__doc__)
    default_config = SCRIPT_PATH.with_name("amplitude_summary.toml")
    default_config_text = str(default_config)
    parser.add_argument("config", nargs="?", default=default_config_text)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    config_location = Path(arguments.config)
    config_path = config_location.resolve()
    config_path_text = str(config_path)
    script_path_text = str(SCRIPT_PATH)
    if not arguments.worker:
        command = [
            sys.executable,
            "-u",
            script_path_text,
            config_path_text,
            "--worker",
        ]
        stage_path = PROJECT_ROOT / "stages/amplitudes.py"
        stage_path_text = str(stage_path)
        runtime_path = PROJECT_ROOT / "runtime_support.py"
        runtime_path_text = str(runtime_path)
        source_paths = [script_path_text, stage_path_text, runtime_path_text]
        provenance = {
            "experiment_id": "amplitude_summary",
            "config_path": config_path_text,
            "source_paths": source_paths,
        }
        records_root = PROJECT_ROOT / "executions"
        status, attempt = execute(
            command, records_root, PROJECT_ROOT, provenance
        )
        raise SystemExit(status)

    # 工作进程进入同一编排；运行记录与科学业务分开。
    attempt = Path(os.environ["SCIENTIFIC_EXECUTION_DIR"])
    progress = Progress(attempt)
    try:
        run(config_path, progress)
    except BaseException as error:
        progress.data["error"] = {
            "type": type(error).__name__,
            "message": str(error),
        }
        progress.finish("failed")
        raise
    else:
        progress.finish("succeeded")
