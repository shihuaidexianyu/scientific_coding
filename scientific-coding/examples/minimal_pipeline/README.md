# 从数据到结果的最小示例

源码文件头、函数文档、语义块注释与 TOML 说明均使用中文。函数采用真正的 docstring，语言服务可在调用处悬停显示参数内容、具体结构、处理逻辑及产物；各参数和部分之间留空行。

本示例研究独立生成的两组试次：保留试次的平均振幅相差多少？默认连续执行，不需要 approval.json 或人工输入确认。Python 3.11+，仅使用标准库。

## 最初有什么数据

没有外部实验数据。采集阶段根据 `configs/acquire_data.toml` 生成独立合成试次，默认每组 40 个。对照/处理组均值分别为 1.0/1.4 微伏，基础标准差为 0.4 微伏；每个试次按概率 0.1/0.8/0.1 选择 0.7/1.0/1.3 的标准差倍数，再进行正态抽样。种子确定生成顺序，数值保留四位小数。

这是假设试次独立的教学设计，不能直接用于把同一被试的重复试次当作独立被试进行推断。0.2 微伏的排除下限是示例方法，真实研究需给出依据。

全部初始输入是三份带注释的科学参数文件，以及描述执行路径的 `configs/pipeline.toml`。可用 `tomllib.loads(path.read_text(encoding="utf-8"))` 读取为字典。每个参数的单位、作用和边界约定写在键的正上方。

## 数据如何变化

| 阶段 | 数据结构与格式 | 读取、含义和处理 |
|---|---|---|
| acquire_data | RawTrials：UTF-8 CSV；trial_id、condition、amplitude_uv | 每行一个合成试次；ID 为 control-001 等。CSV 字符串转一次 float；单位微伏；生成顺序保持稳定。见 [原始契约](contracts/raw_trials.toml)。 |
| preprocess | ProcessedTrials：同结构 CSV，加 exclusions.csv | 振幅严格小于下限的试次被排除，等于下限保留。其余 ID、类型、单位和相对顺序不变；排除表逐 ID 记录原因和阶段。见 [处理后契约](contracts/processed_trials.toml)。 |
| analyze | AnalysisResult：JSON 标量字典，加 summary.md、aggregation.csv | 产生组均值、处理减对照的差值及 bootstrap 区间；n 的单位是试次。映射表保留每个试次对均值差的有符号贡献权重。见 [结果契约](contracts/analysis_result.toml)。 |
| figure_results | results.svg，加 results.provenance.json | 只将已有均值和区间映射为显示内容，不重新排除样本或计算区间。 |

实际运行的每份结果都携带对应契约、副本 config.toml、run.json 和 manifest.json。契约的 reading 节给出具体读取表达式和内存对象；run.json 记录实际输入绑定、有效配置、代码与环境。不存在的时间轴/坐标系不虚构字段。

## 运行

在此目录执行：

```bash
python pipeline.py
```

程序打印一个新的 `artifacts/run_<id>/`，其中有 raw_trials、processed_trials、analysis_result 和最终图。再次执行会新建运行目录，保留旧结果。运行目录 ID 和执行时间不会进入科学数据身份哈希。同种子、同配置、同契约的科学结果可复现，运行元数据哈希可以不同。

```bash
python ../../scripts/scientific_code_lint.py . --full-artifact-checks
```

`artifact_io.py` 复用 skill 的工具实现。将示例复制到独立目录时，设置执行环境变量 `SCIENTIFIC_CODING_SCRIPTS` 为该 skill 的 scripts 绝对路径；它只定位 I/O 工具，不选择科学方法。评测器会为自己的副本设置此路径。

## 检查放在哪里

阶段只验证新引入的科学参数。原始 ID 和顺序由生成过程保证；预处理不重复检查它们。筛选可能清空某组，所以预处理检查这一新风险。后续均值与 bootstrap 直接使用已满足条件的分组。finalize 检查声明契约并绑定文件哈希，不再扫描生产者已保证的逐行类型和 ID；它不等于独立的科学有效性检查。同次运行的后续函数不再重读或重新散列刚生成的数据。

若从 `raw_artifact` 或 `processed_artifact` 读取外部保存结果，入口验证一次载荷、契约、类型、ID 和分组要求，再把有效保证传给内部代码。不要用本示例的简化数据设计替代真实研究的边界判断。

## 可选的人工暂停

只有明确需要人工查看时，才将 `pause_after` 设为 acquire_data、preprocess 或 analyze。对应结果完整生成后停止，其他阶段不会自动增加暂停点。工具把这个显式要求写入该结果的 manifest。

人检查该目录的数据说明与结果后，可以执行：

```bash
python ../../scripts/scientific_artifact.py approve <artifact-directory> --reviewer <your-name>
```

终端确认记录的是一次决策，不证明审阅质量。若暂停在原始或预处理结果，下一次运行将该目录写入 raw_artifact 或 processed_artifact，并清空 pause_after；已完成的上游无需重跑。若暂停在最终分析结果，可先用 `load_external_artifact(path, "AnalysisResult@1")` 读取一次，再调用 `write_figure`。不要同时填写两种上游输入。
