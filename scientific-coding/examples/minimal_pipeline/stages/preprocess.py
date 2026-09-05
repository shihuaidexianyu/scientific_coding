# scientific-code: stage
"""按振幅下限筛选试次，发布 ProcessedTrials@1 和排除记录。

输入文件与配置
--------------
调用方从采集阶段或已验证的外部 RawTrials@1 提供试次行和来源绑定；
对应原始文件为该产物内的 data/raw_trials.csv。本文件不重复读取它。
读取 configs/preprocess.toml 的 amplitude_floor_uv，配置路径由调用方传入。
契约模板为 contracts/processed_trials.toml，模板路径相对项目根目录。

加工逻辑
--------
严格低于下限的试次进入排除表；等于下限时保留。
筛选保持保留试次的 ID、类型、单位及相对顺序；随后检查每组至少剩两个试次。

输出文件
--------
在指定新目录中写 data/processed_trials.csv 和 exclusions.csv，后者逐试次
记录原始数值、排除原因和阶段；同时保存配置、契约和来源记录。
返回保留行及对应产物绑定；不修改传入数据。
"""

# 共享代码仅负责序列化和产物发布。
from pathlib import Path
import math
from artifact_io import PROJECT_ROOT, csv_bytes, publish_payload, read_config


def run(rows: list[dict], input_binding: dict, config_path: Path,
        output_dir: Path, *, review_required: bool = False) -> tuple[list[dict], dict]:
    """筛选试次并保存逐样本排除原因。

    参数
    ----
    rows : list[dict]
        每行一个试次的 list[dict]，长度为 N。
        trial_id 为唯一字符串，condition 为 control 或 treatment，
        amplitude_uv 为有限浮点数，单位为微伏；顺序沿用上游。
        本函数沿用 RawTrials@1 在上游生成或外部入口建立的保证。

    input_binding : dict
        包含 path、contract、artifact_hash、manifest_hash 的字典；各值为字符串。
        path 相对项目根目录，contract 为 RawTrials@1。
        artifact_hash 绑定数据身份，manifest_hash 绑定完整清单记录。
        指向本次 rows 的确切来源，不根据一个状态标签猜测数据身份。

    config_path : Path
        科学配置文件路径；相对路径按调用时的工作目录读取。
        示例默认采用 configs/preprocess.toml，amplitude_floor_uv 为有限微伏下限。
        小于下限时排除、等于时保留。

    output_dir : Path
        本阶段的新输出目录，由编排器在本次 run 目录下指定；不覆盖已有产物。

    review_required : bool
        默认 False；仅在用户选定本阶段暂停时启用待评审记录。

    处理逻辑
    --------
    1. 读取并校验本阶段新引入的有限阈值。
    2. 将原始行分为保留与排除两部分，记录排除原因。
    3. 筛选后确认每组仍至少两个试次，再保存两张表及来源。

    产物
    ----
    retained : list[dict]
        与 rows 字段、单位和相对顺序一致的保留子集，每组至少两个试次。
        返回长度 M 不大于输入长度 N；被移除的行保存在 exclusions.csv。

    binding : dict
        包含 path、contract、artifact_hash、manifest_hash 的字典；各值为字符串。
        path 相对项目根目录，contract 为 ProcessedTrials@1。
        artifact_hash 绑定数据身份，manifest_hash 绑定完整清单记录。
        此处指向新发布的本阶段结果。

    副作用
    ------
    在 output_dir 写入本文件头列出的数据、契约、配置和来源文件；不修改 rows。
    """

    # 阈值是本阶段新输入，在此检查一次其为有限数。
    config = read_config(config_path)
    floor = config["amplitude_floor_uv"]
    if not isinstance(floor, (int, float)) or not math.isfinite(floor):
        raise ValueError("amplitude_floor_uv must be finite")

    # 将输入行划分为保留与排除两部分；筛选保留 ID、类型和相对顺序。
    retained, excluded = [], []
    for row in rows:
        if row["amplitude_uv"] < floor:
            excluded.append({**row, "reason": f"amplitude below {floor} uV", "stage": "preprocess"})
        else:
            retained.append(row)

    # 筛选可能使某组样本不足，因此此处检查新受到影响的分析前提。
    counts = {name: sum(row["condition"] == name for row in retained) for name in ("control", "treatment")}
    if min(counts.values()) < 2:
        raise ValueError("The chosen floor leaves fewer than two trials in a condition")

    # 保存划分的两部分，使每个被移除试次及其原因都可以追踪。
    columns = ["trial_id", "condition", "amplitude_uv"]
    binding = publish_payload(
        {
            "data/processed_trials.csv": csv_bytes(retained, columns),
            "exclusions.csv": csv_bytes(excluded, columns + ["reason", "stage"]),
        },
        PROJECT_ROOT / "contracts/processed_trials.toml", config_path, Path(__file__),
        output_dir, [{**input_binding, "role": "raw_trials"}], config_values=config, review_required=review_required,
    )
    return retained, binding
