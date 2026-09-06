"""
读取试次振幅并计算包含阈值的两组均值差；目前还没有完整运行记录。

配置 TOML + trials.csv --> 包含等号的筛选 --> 两组均值 --> records/result.json
"""

# 这个初始入口故意缺少日志和独立尝试目录，供改进任务使用。
import argparse
import csv
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tomllib


def compute(config_path: Path, token: str, fail_after_read: bool) -> dict:
    """读取配置和 CSV，返回保留试次数、两组均值及处理组减对照组的差。"""

    # 配置中的输入路径按配置所在目录解析，振幅单位为微伏。
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    data_path = config_path.parent / config["input"]["path"]
    with data_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))

    # 已有诊断程序的输出必须随本次运行保留，不能只记录父进程的 print。
    print("PARENT_STDOUT:" + token, flush=True)
    print("PARENT_STDERR:" + token, file=sys.stderr, flush=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name("diagnostic_child.py")), token], check=True)
    if fail_after_read:
        raise RuntimeError("intentional_after_read:" + token)

    # 同一阈值用于两个条件；空组是筛选新引入的科学风险。
    minimum = config["analysis"]["minimum_uv"]
    retained = [row for row in rows if float(row["amplitude_uv"]) >= minimum]
    control = [float(row["amplitude_uv"]) for row in retained if row["condition"] == "control"]
    treatment = [float(row["amplitude_uv"]) for row in retained if row["condition"] == "treatment"]
    if not control or not treatment:
        raise ValueError("Filtering left an empty condition")
    control_mean, treatment_mean = statistics.mean(control), statistics.mean(treatment)
    return {"n_control": len(control), "n_treatment": len(treatment),
            "control_mean_uv": control_mean, "treatment_mean_uv": treatment_mean,
            "difference_uv": treatment_mean - control_mean}


if __name__ == "__main__":

    # 诊断选项属于执行入口；科学参数仍由 TOML 决定。
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--records", type=Path, default=Path("records"))
    parser.add_argument("--event-token", default="example")
    parser.add_argument("--fail-after-read", action="store_true")
    parser.add_argument("--list-runs", action="store_true")
    args = parser.parse_args()
    if args.list_runs:
        print("[]")
    else:
        result = compute(args.config, args.event_token, args.fail_after_read)
        args.records.mkdir(parents=True, exist_ok=True)
        (args.records / "result.json").write_text(json.dumps(result), encoding="utf-8")
