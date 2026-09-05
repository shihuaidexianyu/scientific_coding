# scientific-code: view
"""把 AnalysisResult@1 的既有估计值绘制为 SVG，并记录图的来源。

输入文件
--------
调用方传入 result.json 对应的标量字典和产物绑定；同次流程直接传内存数据。
从外部文件使用时，调用方先用 load_external_artifact 验证并读取一次。

加工逻辑与配置
--------------
将已有组均值线性映射为柱形坐标，把已有区间作为图注显示。
不重新筛选试次或计算统计区间；没有独立 TOML，科学参数来自上游分析结果，
其原始配置为 configs/analyze.toml。

输出文件
--------
写入调用方指定的 results.svg 及同名 results.provenance.json。
来源文件记录输入绑定、绘图代码哈希、输出哈希和显示含义；不修改输入结果。
"""

# 文件输出和来源工具不导入科学阶段的实现。
from pathlib import Path
from artifact_io import integrity, json_bytes


def render_svg(result: dict) -> str:
    """将已有均值和区间映射为可显示的 SVG 文本。

    参数
    ----
    result : dict
        AnalysisResult@1 的标量字典：control_mean_uv、treatment_mean_uv、
        difference_uv、ci_low_uv、ci_high_uv 为微伏浮点数；
        n_control、n_treatment 为试次数整数，n_bootstrap、seed 为整数，
        confidence_level 为严格位于 0 与 1 之间的概率浮点数，method 为方法字符串。
        调用方已建立这些值的含义，本函数不重新进行统计推断。

    处理逻辑
    --------
    1. 选择覆盖两个均值和零点的显示范围，建立微伏到像素的线性比例。
    2. 绘制两个均值柱，标注已有试次数，并将已有差值区间放入图注。

    产物
    ----
    svg : str
        完整独立 SVG 文本，画布为 640×400 像素，可按 UTF-8 保存为 .svg。
        区间描述均值差，不是两个组各自的误差条。

    副作用
    ------
    不修改 result，不读写文件；没有独立 TOML 配置。
    """

    # 显示范围覆盖两根柱及零点，不改变已有估计值。
    upper = max(2.0, result["control_mean_uv"], result["treatment_mean_uv"]) * 1.1
    lower = min(0.0, result["control_mean_uv"], result["treatment_mean_uv"])
    scale = 240 / (upper - lower)
    zero_y = 290 + lower * scale
    bars = []
    for x, condition, color in ((150, "control", "#4c78a8"), (350, "treatment", "#f58518")):

        # 把已有组均值映射为柱形坐标，并标注该组已有试次数。
        mean = result[f"{condition}_mean_uv"]
        y = zero_y - mean * scale
        bars.append(
            f'<rect x="{x}" y="{min(y, zero_y)}" width="100" height="{abs(mean * scale)}" fill="{color}"/>'
            f'<text x="{x + 50}" y="{y - 8}" text-anchor="middle">{mean} uV</text>'
            f'<text x="{x + 50}" y="325" text-anchor="middle">{condition} (n={result[f"n_{condition}"]} trials)</text>'
        )

    # 呈现分析结果中已保存的区间，不重新计算分位数。
    caption = f"{result['confidence_level']:.0%} CI of difference: [{result['ci_low_uv']}, {result['ci_high_uv']}] uV"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="400" viewBox="0 0 640 400">'
        '<rect width="640" height="400" fill="white"/>'
        '<g font-family="sans-serif" font-size="13" fill="#222">'
        '<text x="320" y="28" text-anchor="middle" font-size="18">Mean retained-trial amplitude</text>'
        f'<line x1="80" y1="{zero_y}" x2="580" y2="{zero_y}" stroke="black"/>'
        + ''.join(bars)
        + f'<text x="320" y="375" text-anchor="middle">{caption}</text></g></svg>\n'
    )


def write_figure(result: dict, binding: dict, output_path: Path) -> None:
    """保存结果图及其可追踪的来源记录。

    参数
    ----
    result : dict
        AnalysisResult@1 的标量字典：control_mean_uv、treatment_mean_uv、
        difference_uv、ci_low_uv、ci_high_uv 为微伏浮点数；
        n_control、n_treatment 为试次数整数，n_bootstrap、seed 为整数，
        confidence_level 为严格位于 0 与 1 之间的概率浮点数，method 为方法字符串。

    binding : dict
        包含 path、contract、artifact_hash、manifest_hash 的字典；各值为字符串。
        path 相对项目根目录，contract 为 AnalysisResult@1。
        artifact_hash 绑定数据身份，manifest_hash 绑定完整清单记录。
        这里描述 result 所属的分析产物。

    output_path : Path
        SVG 目标路径，通常位于本次新 run 目录；父目录由调用方创建。

    处理逻辑
    --------
    1. 调用 render_svg 呈现已有值并保存 UTF-8 SVG。
    2. 记录输入绑定、绘图源码哈希、SVG 哈希和显示含义，保存来源 JSON。

    产物
    ----
    返回值 : None
        文件产物为 output_path，以及将其后缀改为 .provenance.json 的来源文件。
        JSON 含 input_artifact 字典，以及 view_code_sha256、output_sha256、display 字符串。

    副作用
    ------
    写入两份文件，不修改输入；不重复验证同次流程刚生成的数据。
    """

    # 绘图使用本次流程中原样传递的结果与已知来源绑定。
    output_path.write_text(render_svg(result), encoding="utf-8")
    provenance = {
        "input_artifact": binding,
        "view_code_sha256": integrity.sha256_file(Path(__file__)),
        "output_sha256": integrity.sha256_file(output_path),
        "display": "two means in microvolts; interval refers to treatment minus control",
    }
    output_path.with_suffix(".provenance.json").write_bytes(json_bytes(provenance))
