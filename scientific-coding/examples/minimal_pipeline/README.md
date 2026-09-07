# 从数据到结果的最小示例

此旧集成示例仍采用分阶段配置，尚未迁移为“每实验一份 TOML、同目录 MD
和专属编排”的结构。新实验按[实验组织规则](../../references/experiment.md)
创建；不要复制这里的多配置读取方式作为新设计。

这是已有功能集成演示，包含可选的哈希产物协议、外部结果复用和人工暂停，
不要求新任务复制整套目录或基础设施。它展示已完成版本，不能作为初稿
预装检查的依据；新增检查统一按[必要性政策](../../references/checks.md)
在完整逻辑之后论证。已有示例尚未全面整改为新 80 字符与表达式规则，
其历史测试通过只证明当时检查范围，不能声称全面满足新增规范。

当前三个 stage 的 run() 仍包含配置/样本检查并直接发布产物，尚未迁移到
“编排负责必要检查”的新设计。不要直接复制这些 run() 作为新业务函数。
迁移须先分离计算和发布，再把必要检查移至编排的实际调用前后；仅复制
检查到 pipeline 会重复检查，等 run() 返回后才查又会晚于发布。
新调用顺序见[编排示意](../../templates/pipeline_boundary.md)。

源码文件头、函数文档、语义块注释与 TOML 说明均使用中文。函数采用真正的 docstring，语言服务可在调用处悬停显示参数内容、具体结构、处理逻辑及产物；各参数和部分之间留空行。

本示例研究独立生成的两组试次：保留试次的平均振幅相差多少？默认连续执行，不需要 approval.json 或人工输入确认。Python 3.11+，科学计算仅使用标准库；Windows 若已有 psutil 则用它读取进程峰值 RSS，未安装时保存未采集原因，Linux/macOS 使用标准库 resource。

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

入口打印新尝试的日志和记录路径。`execution.json` 的 `progress.result_path` 指向新 `artifacts/run_<id>/`，其中有 raw_trials、processed_trials、analysis_result 和最终图。再次执行会新建尝试和运行目录，保留旧结果。运行目录 ID 和执行时间不会进入科学数据身份哈希。同种子、同配置、同契约的科学结果可复现，运行元数据哈希可以不同。

每次命令留下 `executions/attempts/<id>/run.log`、`execution.json`、`progress.json`，并在 `executions/index/<id>.json` 产生独立索引。`run.log` 合并完整 stdout/stderr 与异常堆栈，使用 UTF-8 Python 输出；`execution.json` 保存 UTC 起止、实际子进程退出码、墙钟时间、来源路径与阶段信息。读取方式是 `json.loads(path.read_text(encoding="utf-8"))`；批量查询时遍历 index 下各 JSON 即可，不竞争同一个追加文件。

正常、失败、暂停、取消和启动失败分别记录。失败仍保留日志与已完成阶段，可能已有部分科学产物；只有 `status=succeeded` 且阶段完成才代表本次完整执行，仍不代表统计显著。未完成的记录不会自动改成成功。配置解析及业务模块导入在建立日志后进行，报错也可追溯。直接导入 `run()` 供嵌入和测试，记录由调用它的外部入口负责，内部科学函数不各自建立日志。

CPU 秒数覆盖工作进程的编排区间；峰值 RSS 覆盖该新进程的整个寿命，包括模块导入，不含父记录器和子进程。各阶段时间包含其读盘、计算和发布；本例无 GPU。无法采集的资源字段为 null，并保存具体原因。科学来源继续使用每个产物已有的 run.json；失败前还没有产物时，可从尝试中的 snapshots 读取启动源码和实际读入的配置原始字节，即使 TOML 解析失败也保留。副本使用 .snapshot 后缀，配套 .source.json 写原路径、SHA-256 和相对副本路径；它们只用于来源保存，不作为待执行源码或重复数据校验。

## 运算时间与效率

设 N 为保留试次数，B 为 bootstrap 次数，N0 为最初生成试次数。科学计算时间为 O(N0 + BN + B log B)，其中重采样约为 BN，B log B 来自排序 bootstrap 差值；内存为 O(N0 + B)，还包括 Python 行字典和序列化临时对象。完整运行还包含解释器启动、文件读写、来源记录和哈希成本，这些在本例的小数据下可能占主要部分。

默认 N0=80、B 取 configs/analyze.toml 的 n_bootstrap，单个科学 worker，不使用 GPU。目标机器未校准时不能可靠给出秒数；可先执行本例，从 execution.json 取 wall_time_s、各阶段时间与峰值 RSS，再改变一个规模（例如 B）验证扩展趋势。一次小样本运行不能证明大型数据的吞吐量。K 个相似独立任务使用 W 个 worker 时，ceil(K/W) × 单次时间只是理想近似，实际还受 I/O、内存争用和长尾影响。

```bash
python ../../scripts/scientific_code_lint.py . --full-artifact-checks
```

`artifact_io.py` 复用 skill 的工具实现。将示例复制到独立目录时，设置执行环境变量 `SCIENTIFIC_CODING_SCRIPTS` 为该 skill 的 scripts 绝对路径；它只定位 I/O 工具，不选择科学方法。评测器会为自己的副本设置此路径。

## 旧版示例的检查位置（尚未迁移）

阶段只验证新引入的科学参数。原始 ID 和顺序由生成过程保证；预处理不重复检查它们。筛选可能清空某组，所以预处理检查这一新风险。后续均值与 bootstrap 直接使用已满足条件的分组。finalize 检查声明契约并绑定文件哈希，不再扫描生产者已保证的逐行类型和 ID；它不等于独立的科学有效性检查。同次运行的后续函数不再重读或重新散列刚生成的数据。

若从 `raw_artifact` 或 `processed_artifact` 读取外部保存结果，入口验证一次载荷、契约、类型、ID 和分组要求，再把有效保证传给内部代码。不要用本示例的简化数据设计替代真实研究的边界判断。

## 可选的人工暂停

只有明确需要人工查看时，才将 `pause_after` 设为 acquire_data、preprocess 或 analyze。对应结果完整生成后停止，其他阶段不会自动增加暂停点。工具把这个显式要求写入该结果的 manifest。

人检查该目录的数据说明与结果后，可以执行：

```bash
python ../../scripts/scientific_artifact.py approve <artifact-directory> --reviewer <your-name>
```

终端确认记录的是一次决策，不证明审阅质量。若暂停在原始或预处理结果，下一次运行将该目录写入 raw_artifact 或 processed_artifact，并清空 pause_after；已完成的上游无需重跑。若暂停在最终分析结果，可先用 `load_external_artifact(path, "AnalysisResult@1")` 读取一次，再调用 `write_figure`。不要同时填写两种上游输入。
