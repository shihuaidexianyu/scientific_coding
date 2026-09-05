# scientific-code: acquisition-stage
"""生成两组独立合成试次，发布 RawTrials@1 原始数据。

输入与配置
----------
没有外部实验数据。读取调用方传入的采集 TOML，默认是项目根目录下
configs/acquire_data.toml；参数为每组试次数、种子、两组均值和基础标准差。

加工逻辑
--------
校验本阶段新引入的参数，按对照组、处理组顺序生成稳定试次 ID。
每次先抽取标准差倍数，再进行正态抽样，振幅保留四位小数。

输出文件
--------
在调用方指定的新目录中写入 data/raw_trials.csv、config.toml、run.json、
manifest.json 和 artifact_contract.toml。CSV 字段为 trial_id、condition、
amplitude_uv；单位为微伏。契约来自 contracts/raw_trials.toml，路径相对项目根目录。
返回内存中的试次行和产物绑定，供同一次流程直接使用。
"""

# 随机生成属于本阶段的科学逻辑，共享读写工具不执行科学计算。
from pathlib import Path
import random
import math
from artifact_io import PROJECT_ROOT, csv_bytes, publish_payload, read_config


def run(config_path: Path, output_dir: Path, *, review_required: bool = False) -> tuple[list[dict], dict]:
    """生成并保存独立的两组试次振幅。

    参数
    ----
    config_path : Path
        采集 TOML 文件路径；相对路径按调用时的工作目录读取。
        n_trials_per_condition、seed 为整数；control_mean_uv、treatment_mean_uv、
        amplitude_std_uv 为微伏数值，分别表示两组均值和基础标准差。

    output_dir : Path
        本次 RawTrials 的新目录，通常为 artifacts/run_<编号>/raw_trials。
        目录必须尚未发布；写入的文件结构见本文件头。

    review_required : bool
        默认 False；仅在调用方已选定此阶段为人工暂停点时为 True。

    处理逻辑
    --------
    1. 在生成入口检查本次配置，建立局部随机数发生器。
    2. 先生成对照组再生成处理组，按抽取的标准差倍数进行正态抽样。
    3. 由生成顺序构造 ID，振幅舍入四位，保存 CSV 和来源记录。

    产物
    ----
    rows : list[dict]
        每行一个试次的 list[dict]，长度为 N。
        trial_id 为唯一字符串，condition 为 control 或 treatment，
        amplitude_uv 为有限浮点数，单位为微伏；先 control 后 treatment，组内编号递增。
        N 等于每组试次数的两倍；ID 示例为 control-001。

    binding : dict
        包含 path、contract、artifact_hash、manifest_hash 的字典；各值为字符串。
        path 相对项目根目录，contract 为 RawTrials@1。
        artifact_hash 绑定数据身份，manifest_hash 绑定完整清单记录。

    副作用
    ------
    创建新产物目录及其文件；不修改调用方配置。
    """

    # 生成数据前一次性检查本阶段配置的科学约束。
    config = read_config(config_path)
    n = config["n_trials_per_condition"]
    if type(n) is not int or n < 2 or type(config["seed"]) is not int:
        raise ValueError("Use an integer seed and at least two trials per condition")
    parameters = [config[key] for key in ("control_mean_uv", "treatment_mean_uv", "amplitude_std_uv")]
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in parameters) or config["amplitude_std_uv"] <= 0:
        raise ValueError("Means must be finite and amplitude_std_uv must be positive")
    rng = random.Random(config["seed"])

    # 由生成顺序直接构造稳定 ID 和组顺序，无须生成后再扫描检查。
    rows = []
    for condition in ("control", "treatment"):
        mean = config[f"{condition}_mean_uv"]
        std = config["amplitude_std_uv"]
        for index in range(n):

            # 标准差倍数的混合是教学采集模型的一部分，不属于预处理。
            draw = rng.random()
            multiplier = 0.7 if draw < 0.1 else (1.0 if draw < 0.9 else 1.3)
            rows.append({
                "trial_id": f"{condition}-{index + 1:03d}",
                "condition": condition,
                "amplitude_uv": round(rng.gauss(mean, std * multiplier), 4),
            })

    # 保存生成的试次行，以及解释其读取方法和含义的契约。
    binding = publish_payload(
        {"data/raw_trials.csv": csv_bytes(rows, ["trial_id", "condition", "amplitude_uv"])},
        PROJECT_ROOT / "contracts/raw_trials.toml", config_path, Path(__file__),
        output_dir, [], config_values=config, review_required=review_required,
    )
    return rows, binding
