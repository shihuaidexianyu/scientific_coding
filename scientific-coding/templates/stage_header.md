# 中文文件头与悬停函数文档模板

下例展示文档格式。实际生成时替换为项目真实的文件路径、字段、单位、配置和处理规则。函数文档必须放在语言服务能识别的位置；Python 中使用函数体首条语句的三引号 docstring。各参数、各返回值单独成段。

```python
# scientific-code: stage
"""筛选试次振幅并汇总保留样本的均值。

文件用途
--------
本文件提供振幅筛选和汇总函数，供流水线入口调用。

输入文件与数据
--------------
调用方读取 UTF-8 CSV 文件 data/trials.csv 的 amplitude_uv 列，
在外部入口将其转换为有限浮点数列表，再传给本文件中的函数。
每个元素代表一个试次，单位为微伏；保持 CSV 原始行顺序。

关联配置
--------
调用方读取 configs/preprocess.toml 的 amplitude_floor_uv 键，
把有限的数值阈值作为 floor_uv 传入。两个路径均相对项目根目录。

加工逻辑
--------
1. 保留振幅大于或等于阈值的试次。
2. 如果筛选后没有样本，给出明确错误。
3. 计算保留数量和算术均值，交给调用方保存。

产物与文件
----------
返回保留振幅列表和包含 count、mean_uv 的汇总字典。
本文件不直接读写文件；调用方负责将汇总写入声明的结果目录。
"""


def summarize_amplitudes(amplitudes_uv: list[float], floor_uv: float) -> tuple[list[float], dict]:
    """按阈值筛选试次，计算保留样本的数量与平均振幅。

    参数
    ----
    amplitudes_uv : list[float]
        一维试次振幅列表，长度为试次数 N，单位为微伏。
        顺序对应输入 CSV 的行顺序，例如 [0.2, 0.8, 1.2]。
        调用方已在外部入口保证每个元素是有限浮点数。

    floor_uv : float
        保留阈值，单位为微伏；来自配置中的 amplitude_floor_uv。
        小于阈值时排除，等于阈值时保留。调用方已保证阈值有限。

    处理逻辑
    --------
    1. 按原顺序保留振幅不低于 floor_uv 的元素。
    2. 筛选可能清空列表，因此在这一步检查是否还有保留样本。
    3. 计算保留数量及算术均值，不重复检查已确定的输入数值类型。

    产物
    ----
    retained : list[float]
        长度为 M 的保留振幅列表，0 < M <= N。
        数值单位为微伏，相对顺序保持不变。

    summary : dict
        count 为整数 M，表示保留的试次数。
        mean_uv 为浮点数，表示保留振幅的算术均值，单位为微伏。
        返回结构示例：{"count": 2, "mean_uv": 1.0}。

    副作用
    ------
    不修改传入列表，不读写文件；没有保留样本时抛出 ValueError。
    """

    # 按阈值筛选，列表推导保留原有相对顺序和数值单位。
    retained = [value for value in amplitudes_uv if value >= floor_uv]

    # 筛选可能移除全部样本，此时均值没有定义。
    if not retained:
        raise ValueError("阈值筛选后没有可用于计算均值的试次")

    # 对保留试次汇总数量和算术均值，并分别返回列表与汇总字典。
    summary = {"count": len(retained), "mean_uv": sum(retained) / len(retained)}
    return retained, summary
```

文件头说明整个文件负责什么；函数 docstring 说明调用接口、参数结构、处理逻辑和产物；函数体内的中文语义块注释对应实际操作。生成或修改后，agent 仍须编写并运行本次语言适用的格式脚本，保证块前空行。
