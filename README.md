# scientific-coding

这是一个用于编写和修改科研代码的 skill。目标是让掌握 Python 基础的读者
能顺着数据理解科学方法，同时保留可复现的运行证据。科学准确性、可读性
优先于节省 token 或行数。

## 实验如何组织

```text
project/
├── experiments/
│   └── amplitude_summary/
│       ├── amplitude_summary.md     目的、设计、依据与运行说明
│       ├── amplitude_summary.toml   本实验唯一运行参数来源
│       └── run_amplitude_summary.py 专属顺序、分支、检查与参数分发
└── stages/
    └── amplitudes.py               清楚、独立的科学计算步骤
```

编排读取一次 TOML，按其目录解析配置内相对路径，再传具名参数给 stage。
stage 不读取总配置。不同实验可以有不同编排，允许少量清楚的调用重复，
不要求通用 pipeline 引擎。现有项目只在任务包含迁移时调整目录。

业务代码用具名中间变量、简单赋值、显式条件和循环表达方法。必要检查
放在实际编排中，在相关数据产生后、依赖计算或发布前执行；已经由同一
流程保证的事实不重复检查。第三方 API 的原生异常自然传播。

## 写代码的工作流程

```text
原始科学逻辑 → 简化并论证必要检查 → 中文说明 → 格式修正 → 验证
```

初稿不预装防御、兜底或门控。完整逻辑形成后，才按可信触发场景、后果、
已有保证和复杂度决定哪些检查不得不加。核验是作者的工作；各运行 stage
默认自动衔接，仅在用户指定审核点或尚未确定的实质科学决定处暂停。

文件头使用中文用途说明和字符流程图；函数使用真正的 docstring，分段写
参数、返回结构、处理过程和副作用。代码及 TOML 按语义块注释，块前空行，
每行至多 80 个 Unicode 字符。agent 编写并运行本任务的格式脚本，保护
字符串和代码含义，再用实际数据核验科学行为。

用户中途提问时先回答再继续。用户修改代码后，以当前文件为准，更新受
影响的说明和验证，保留仍有效的工作与旧结果。

## 核心规范与按需扩展

主入口是 [SKILL.md](scientific-coding/SKILL.md)，详细规则只有三个默认入口：

| 文档 | 负责的功能 |
|---|---|
| [实验组织](scientific-coding/references/experiment.md) | 目录、统一参数、方法边界与必要检查归属 |
| [可读性](scientific-coding/references/readability.md) | 初学者写法、中文注释、数据说明与格式验证 |
| [执行记录](scientific-coding/references/execution.md) | 完整日志、来源、失败、批量索引与运算成本 |

每次运行在业务开始前建立一份外层记录，保存实际输入、配置、代码和环境
来源，完整输出与堆栈，状态、退出码、起止时间、阶段耗时和可获取资源。
新运行使用新目录，失败和重试也进入索引。日志设施不参与科学计算。

交付代码时给出中文时间与内存估计，说明工作量、硬件/并发条件、瓶颈和
依据，区分实测、外推及未知。批量估计考虑争用、队列和长尾。

仅在明确需要时查看[扩展目录](scientific-coding/references/extensions.md)：
性能优化、断点恢复、独立产物协议等保留为可选能力。旧参考文件保留兼容
链接；评测工具和历史集成示例不进入普通任务的默认阅读路径。

## 运行基础示例

需要 Python 3.11+。从仓库根目录执行：

```powershell
cd scientific-coding/examples/basic_experiment
python experiments/amplitude_summary/run_amplitude_summary.py
```

四个合成试次经阈值筛选，保留三个，均值为 1.0 微伏；同时保存被排除的
试次 ID 和原因。示例用于展示组织方式，不提供科学推断。

结果位于示例的 `runs/<编号>/result.json`，完整日志和记录位于
`executions/attempts/<编号>/`，索引位于 `executions/index/`。
数据结构、设计依据及运行支持代码的职责见
[基础示例说明](scientific-coding/examples/basic_experiment/README.md)。

## 使用与维护

把完整 `scientific-coding/` 目录放入所用 agent 的技能目录，保留配套资源。
调用时说明实验目标、已有数据和方法，例如：

```text
使用 $scientific-coding，按这个 plan 完成实验。
保留我确定的方法与手动修改，交付验证、运行记录和运算成本估计。
```

Git 仅追踪技能指令、参考资料、工具、模板、配套示例与仓库说明。
开发测试、模型评测和运行产物留在本地，不随技能发布。

静态检查和程序回归不能证明模型稳定遵循，历史测试也不能充当修改后版本
的对照实验。模型身份需要核对实际运行环境和轨迹。
