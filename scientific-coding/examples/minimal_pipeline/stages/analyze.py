# scientific-code: stage
"""计算保留试次的组均值差和 bootstrap 区间，发布 AnalysisResult@1。

输入文件与配置
--------------
调用方提供 ProcessedTrials@1 内存行及绑定，对应文件为产物目录中的
data/processed_trials.csv；本文件不重复读取它。
读取 configs/analyze.toml 中的 n_bootstrap、seed、confidence_level。
使用 contracts/analysis_result.toml 描述结果，模板路径相对项目根目录。

加工逻辑
--------
按组取出保留振幅，计算均值和处理组减对照组的差值；组内独立有放回抽样，
按排序后向下取整的索引构造分位数区间。试次是本教学模型的独立重采样单位。

输出文件
--------
指定新目录中包含 result.json 的估计值、区间和计数，summary.md 的中文解释，
aggregation.csv 的试次到对比量权重映射，以及配置、契约和来源记录。
权重表须按 trial_id 关联输入振幅才能还原未舍入均值差，不能单独还原区间。
返回结果字典和产物绑定；不把本示例的结论解释为参与者总体推断。
"""

# 随机抽样和均值计算在科学阶段内直接可见。
from pathlib import Path
import random
from artifact_io import PROJECT_ROOT, csv_bytes, json_bytes, publish_payload, read_config


def bootstrap_mean_difference_ci(control: list[float], treatment: list[float],
                                 n_bootstrap: int, seed: int, level: float) -> tuple[float, float]:
    """计算独立试次设计下的组均值差分位数 bootstrap 区间。

    参数
    ----
    control : list[float]
        对照组保留振幅的一维列表，长度为 n_control，单位为微伏。
        上游已保证每个值有限且至少有两个试次。

    treatment : list[float]
        处理组保留振幅的一维列表，长度为 n_treatment，单位为微伏。
        采用与 control 相同的既有约束，两组长度可以不同。

    n_bootstrap : int
        重采样重复次数 B，调用方已保证至少为 100；不是独立样本数量。

    seed : int
        局部伪随机数种子，决定抽样序列，不改变统计推断的适用前提。

    level : float
        区间中心概率，满足 0 < level < 1，例如 0.95。

    处理逻辑
    --------
    1. 各组独立有放回抽取与本组等长的样本，重复 B 次。
    2. 每次计算处理组均值减对照组均值，形成长度为 B 的差值列表。
    3. 排序后按声明的向下取整索引选取两端，右端索引最多为 B-1。
    增大 B 减少蒙特卡洛误差，不保证区间变窄。

    产物
    ----
    lower : float
        区间下端点，单位为微伏，对应排序后左侧分位数索引。

    upper : float
        区间上端点，单位为微伏；与 lower 组成长度为 2 的返回元组。

    副作用
    ------
    不修改输入列表，不读写文件；只使用函数内部的随机数发生器。
    """

    # 重复 B 次，每次独立地在两组内分别有放回抽样；不表示试次配对设计。
    rng = random.Random(seed)
    differences = []
    for _ in range(n_bootstrap):
        sampled_control = [control[rng.randrange(len(control))] for _ in control]
        sampled_treatment = [treatment[rng.randrange(len(treatment))] for _ in treatment]
        differences.append(sum(sampled_treatment) / len(treatment) - sum(sampled_control) / len(control))

    # 按声明的向下取整索引选取经验分位数，右端限制在有效索引内。
    differences.sort()
    lower = int(((1 - level) / 2) * n_bootstrap)
    upper = min(n_bootstrap - 1, int((1 - (1 - level) / 2) * n_bootstrap))
    return differences[lower], differences[upper]


def run(rows: list[dict], input_binding: dict, config_path: Path,
        output_dir: Path, *, review_required: bool = False) -> tuple[dict, dict]:
    """估计并保存保留试次的组均值差。

    参数
    ----
    rows : list[dict]
        每行一个试次的 list[dict]，长度为 N。
        trial_id 为唯一字符串，condition 为 control 或 treatment，
        amplitude_uv 为有限浮点数，单位为微伏；顺序沿用上游。
        本函数沿用 ProcessedTrials@1 在上游生成或外部入口建立的保证。

    input_binding : dict
        包含 path、contract、artifact_hash、manifest_hash 的字典；各值为字符串。
        path 相对项目根目录，contract 为 ProcessedTrials@1。
        artifact_hash 绑定数据身份，manifest_hash 绑定完整清单记录。
        指向本次 rows 的确切来源，不根据一个状态标签猜测数据身份。

    config_path : Path
        科学配置文件路径；相对路径按调用时的工作目录读取。
        示例默认采用 configs/analyze.toml。n_bootstrap 为至少 100 的整数，
        seed 为整数，confidence_level 为严格位于 0 与 1 之间的区间概率。

    output_dir : Path
        本阶段的新输出目录，由编排器在本次 run 目录下指定；不覆盖已有产物。

    review_required : bool
        默认 False；仅在用户选定本阶段暂停时启用待评审记录。

    处理逻辑
    --------
    1. 校验本阶段的重采样次数、种子和区间概率。
    2. 按组形成振幅向量，计算组均值及处理减对照的差值。
    3. 组内有放回重采样得到分位数区间，保存标量结果和试次贡献映射。

    产物
    ----
    result : dict
        n_control、n_treatment 为各组试次数整数。
        control_mean_uv、treatment_mean_uv、difference_uv、ci_low_uv、ci_high_uv
        为微伏浮点数；n_bootstrap、seed 为整数，confidence_level 为概率浮点数，
        method 为方法说明字符串。数值估计保留四位小数。

    binding : dict
        包含 path、contract、artifact_hash、manifest_hash 的字典；各值为字符串。
        path 相对项目根目录，contract 为 AnalysisResult@1。
        artifact_hash 绑定数据身份，manifest_hash 绑定完整清单记录。
        此处指向新发布的本阶段结果。

    副作用
    ------
    在 output_dir 写入本文件头列出的数据、契约、配置和来源文件；不修改 rows。
    """

    # 检查本阶段新引入的重采样选择，沿用仍有效的上游行级保证。
    config = read_config(config_path)
    count, level, seed = config["n_bootstrap"], config["confidence_level"], config["seed"]
    if type(count) is not int or count < 100 or type(seed) is not int or not isinstance(level, (int, float)) or not 0 < level < 1:
        raise ValueError("Use integer B >= 100, an integer seed, and 0 < confidence_level < 1")

    # 按组形成两个振幅向量，包含全部保留试次，再计算各组均值。
    control = [row["amplitude_uv"] for row in rows if row["condition"] == "control"]
    treatment = [row["amplitude_uv"] for row in rows if row["condition"] == "treatment"]
    control_mean = sum(control) / len(control)
    treatment_mean = sum(treatment) / len(treatment)

    # 围绕同一试次层面的目标量重采样；上游已保证两组样本量足够。
    low, high = bootstrap_mean_difference_ci(control, treatment, count, seed, level)
    result = {
        "n_control": len(control), "n_treatment": len(treatment),
        "control_mean_uv": round(control_mean, 4), "treatment_mean_uv": round(treatment_mean, 4),
        "difference_uv": round(treatment_mean - control_mean, 4),
        "ci_low_uv": round(low, 4), "ci_high_uv": round(high, 4),
        "confidence_level": level, "n_bootstrap": count, "seed": seed,
        "method": "对保留试次在各条件内独立重采样的分位数 bootstrap",
    }

    # 保留每个试次对汇总均值差的带符号权重，便于关联上游振幅。
    mapping = [{"trial_id": row["trial_id"], "condition": row["condition"],
                "contrast_id": "treatment_minus_control",
                "weight": 1 / len(treatment) if row["condition"] == "treatment" else -1 / len(control)}
               for row in rows]

    # 同时保存数值结果及可供人工阅读的解释。
    summary = (
        "# 保留试次的振幅对比\n\n"
        f"处理组减对照组：{result['difference_uv']} 微伏。"
        f"{level:.0%} 区间：[{result['ci_low_uv']}, {result['ci_high_uv']}] 微伏。\n\n"
        f"n_control={len(control)} 个试次；n_treatment={len(treatment)} 个试次。"
        f"B={count}，seed={seed}；各条件内独立重采样。"
        "这里报告单个对比量及其区间，没有定义多重检验族。"
        "推断描述保留的合成试次总体，不能推广为参与者总体结论。\n"
    )
    binding = publish_payload(
        {"result.json": json_bytes(result), "summary.md": summary.encode("utf-8"),
         "aggregation.csv": csv_bytes(mapping, ["trial_id", "condition", "contrast_id", "weight"])},
        PROJECT_ROOT / "contracts/analysis_result.toml", config_path, Path(__file__),
        output_dir, [{**input_binding, "role": "processed_trials"}], config_values=config, review_required=review_required,
    )
    return result, binding
