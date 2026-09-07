# scientific-code: stage
"""
筛选试次并计算保留振幅的描述性均值。

试次行 + 阈值 --> 保留行、逐 ID 排除原因
保留行 --> 数量与均值

输入行为字典列表，每行含 trial_id 字符串及 amplitude_uv 浮点数，单位微伏。
顺序对应输入 CSV。编排从 amplitude_summary.toml 取得 preprocess.floor_uv。
本文件不读取 TOML、不读写文件、不执行防御检查，返回内存产物交编排保存。
"""

# 标准均值函数自然拒绝空输入，不添加同义检查。
from statistics import mean


def select_trials(rows: list[dict], floor_uv: float) -> tuple[list, list]:
    """按振幅下限划分保留行和排除记录。

    参数
    ----
    rows : list[dict]
        原始试次行，按输入顺序排列。
        - trial_id：字符串，试次标识。
        - amplitude_uv：浮点数，试次振幅，单位微伏。

    floor_uv : float
        编排传入的有限振幅下限，单位微伏；等于阈值时保留。

    返回
    ----
    retained : list[dict]
        保留子集，保持相对顺序；可以为空。
        - trial_id：字符串，关联原输入。
        - amplitude_uv：浮点数，试次振幅，单位微伏。

    exclusions : list[dict]
        被排除试次的记录，保留相对顺序。
        - trial_id：字符串，关联原输入。
        - reason：中文字符串，说明不满足振幅下限。

    处理过程
    --------
    1. 逐行按下限划分保留行和排除行。
    2. 从排除行构造逐 ID 原因记录。

    副作用
    ------
    不修改输入行，不读写文件；有限值前提由编排负责。
    """

    # 先按方法划分两个互补子集，原行对象不修改。
    retained = []
    excluded_rows = []
    for row in rows:
        if row["amplitude_uv"] >= floor_uv:
            retained.append(row)
        else:
            excluded_rows.append(row)

    # 为已确定的排除集合构造来源记录，不在筛选条件中隐藏输出构造。
    exclusions = []
    for row in excluded_rows:
        exclusion = {
            "trial_id": row["trial_id"],
            "reason": f"振幅低于 {floor_uv} 微伏",
        }
        exclusions.append(exclusion)
    return retained, exclusions


def summarize_trials(rows: list[dict]) -> dict:
    """汇总保留试次的数量和算术均值，不作总体推断。

    参数
    ----
    rows : list[dict]
        保留试次列表，沿用输入顺序。
        - trial_id：字符串，试次标识。
        - amplitude_uv：有限浮点数，单位微伏。

    返回
    ----
    summary : dict
        - count：整数，保留试次数。
        - mean_uv：浮点数，保留振幅的算术均值，单位微伏。

    处理过程
    --------
    1. 收集振幅，分别计算数量和均值，再构造返回字典。

    副作用
    ------
    不修改输入或读写文件；空输入由 mean 自然抛出 StatisticsError。
    """

    # 将参与汇总的数值明确命名，不在聚合参数里隐藏提取操作。
    amplitudes_uv = []
    for row in rows:
        amplitude_uv = row["amplitude_uv"]
        amplitudes_uv.append(amplitude_uv)

    # 数量与平均值分别计算，保持标准库的数值行为。
    count = len(amplitudes_uv)
    mean_uv = mean(amplitudes_uv)
    summary = {"count": count, "mean_uv": mean_uv}
    return summary
