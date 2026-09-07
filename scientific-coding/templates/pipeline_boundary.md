# 必要检查在编排中的调用顺序

这是调用顺序示意，不是完整可运行项目，也不是要求每个项目增加检查。
假定研究已选定组内 bootstrap，并已论证筛选可能使某组只剩一个试次、
下游实现却仍产生退化区间，因此需要在估计前检查实际保留组的样本量。
本例只展示这个前提；不重复检查已由同流程保证的 ID、类型或有限性。

## stage 业务模块

业务模块实现 `select_trials(rows, floor_uv)`、`group_amplitudes(retained)`
和 `estimate_interval(groups, analysis_config)`，不调用检查函数或发布结果。
筛选返回保留行及带 ID/原因的排除行；分组返回如下字典：

```text
groups : dict[str, list[float]]
  control   : 对照组保留振幅，单位微伏，保持原组内顺序
  treatment : 处理组保留振幅，单位微伏，保持原组内顺序
```

这些是科学步骤，可在原 stage 模块内实现；不需要因此新增三个正式阶段。
函数假设、参数和产物按 [stage_header.md](stage_header.md) 写中文文档。

## pipeline 文件中的必要检查函数

```python
def require_resampling_groups(groups):
    """拒绝不足以支持本研究组内 bootstrap 的保留组。

    参数
    ----
    groups : dict[str, list[float]]
        筛选后实际参与估计的振幅列表，单位为微伏。
        键为 control 和 treatment，值沿用各组内输入顺序。

    返回
    ----
    None
        两组均满足本研究要求时正常返回；不返回“已验证”包装对象。

    处理过程
    --------
    1. 分别读取两组实际样本量，拒绝少于两个试次的组。

    副作用
    ------
    不修改输入或读写文件；不满足时抛出 ValueError，交给外层日志记录。
    """

    # 筛选可能使一组只剩一个试次，当前估计实现不会自行拒绝退化区间。
    for condition in ("control", "treatment"):
        sample_count = len(groups[condition])
        if sample_count < 2:
            message = f"{condition} 筛选后仅 {sample_count} 个试次，无法执行本估计"
            raise ValueError(message)
```

## 同一 pipeline 文件中的顺序调用片段

以下片段位于实际编排函数内。`rows`、`floor_uv`、`analysis_config`、
`output_dir` 是已读取的实际输入和配置；普通文件/解析错误自然传播。
`publish_analysis` 是项目已有 I/O 边界，保存结果、排除记录与对应来源。

```python
# 科学筛选和分组仍在业务函数内，不混入检查函数。
retained, exclusions = select_trials(rows, floor_uv)
groups = group_amplitudes(retained)

# 针对筛选后新受到影响的前提检查一次，后续使用同一份 groups。
require_resampling_groups(groups)

# 检查失败时不会进入估计或发布，也不会改用兜底结果继续运行。
result = estimate_interval(groups, analysis_config)
publish_analysis(result, exclusions, output_dir)
```

不能把样本量检查放到筛选之前，也不能让 `select_trials` 或
`estimate_interval` 先发布正式结果。若单独运行分析阶段，其 CLI 应调用
同一个编排步骤，不能复制一份检查或反向导入编排器。

本例用 list 的 len，两个组的检查为常数时间且不复制样本。生成器或磁盘
数据应按实际接口设计，不为套用此片段先转全量列表。未给出硬件和真实
工作量，不能由此估计整条科研流水线的秒数。
