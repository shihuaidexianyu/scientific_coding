# Scientific Coding Skill

`scientific-coding` 面向科研流水线，让研究者能沿着代码理解数据和方法。当前修订同时调整规范、模板、可运行示例、工具和行为评测。

## 阅读与执行约定

- **中文且可在调用处阅读。** Python 文件头的 `"""` 独占一行，用途之后用字符流程图展示真实输入、加工、输出和关联 TOML。函数文档固定按“用途、参数、返回、处理过程、副作用”排列；名称与类型单独一行，说明缩进，条目之间空行，嵌套字段分别列出。详见[完整排版示例](scientific-coding/templates/stage_header.md)。示例的全部说明性注释与数据指南使用中文，保留代码和字段标识。
- **按职责分轮，局部返工。** 实现、简化、说明、格式、核验依次完成；完整 plan 或跨多个函数的说明/简化，在环境允许时由另一个 agent 只读核验最终源码。由明确负责人修正具体问题，中途保留用户改动，只更新受影响的解释与验证。详见[分轮与协作规则](scientific-coding/references/workflow.md)。
- **按语义操作注释。** 一行或连续几行共同完成一件事时，在前面就地解释目的、数据和重要变化。每段注释前空一行，注释与代码相邻；agent 须自行编写并运行适用于本次各语言文件的格式处理脚本来保证排版。TOML 每个配置节和键也有说明。模块概述不能替代计算旁的解释。
- **把数据讲清楚。** 入口集中列出全部初始数据；每个阶段说明产物的格式、字段或轴、类型、单位、ID、对齐规则、读取方法和相对输入的变化。未落盘的关键中间变量就在代码旁说明。
- **复用已有保证。** 外部输入在真实入口验证一次；同一流程已验证或按构造保证的事实，后续直接使用。只有变换可能破坏保证、对象或版本改变、重新读取可变外部数据时，才检查受影响的事实。
- **默认连续完成。** 阶段和中间文件不自动产生人工关卡；只在用户选定的评审点或尚未确定的重要科学选择处暂停。重跑保留新结果和实际来源，无需默认审批文件。
- **保持适用范围。** 新科研项目默认使用注释完整的 TOML；已有项目沿用现有配置系统。用户可以选择工程默认值，不把流水线机制强加给通用库、模拟器或基础设施。

详见 [SKILL.md](scientific-coding/SKILL.md)、[可读性规范](scientific-coding/references/readability.md)、[阶段规范](scientific-coding/references/stage.md)和[数据与产物规范](scientific-coding/references/artifact.md)。多输入汇合要说明角色、关联键、基数及缺失匹配处理；拆分和聚合要保留样本映射。

## 使用与示例

将整个 `scientific-coding/` 目录安装到你的技能目录，或在项目的 `.agents/skills/` 下放置它，然后显式调用：

```text
Use $scientific-coding to improve this analysis stage.
```

Python 3.11+ 即可运行自带示例，无额外计算库依赖。从本仓库根目录执行：

```bash
python scientific-coding/examples/minimal_pipeline/pipeline.py
```

示例从合成试次生成、排除记录、bootstrap 分析一直运行到 SVG 图，每次写入新的 `artifacts/run_*/`。真实观测数据尚未提供，示例数值仅演示方法与数据组织。初始数据说明、全部中间数据、配置和按需暂停方式见[示例说明](scientific-coding/examples/minimal_pipeline/README.md)。不随仓库分发伪装成人工批准的演示产物。

## 检查工具

从仓库根目录检查科研项目：

```bash
python scientific-coding/scripts/scientific_code_lint.py <project-root> --changed-only

# 检查 merge-base 以来的提交变化；项目自行决定是否把警告设为失败。
python scientific-coding/scripts/scientific_code_lint.py <project-root> --base-ref origin/main

# 独立审计时核对全部实际载荷，而非在每个内部调用处反复验证。
python scientific-coding/scripts/scientific_code_lint.py <project-root> --full-artifact-checks --format json
```

Linter 检查依赖边界、配置、来源绑定和产物完整性，也报告可人工判断的启发式警告。它无法判断注释是否真正帮助理解或某个检查是否有新增价值；这些要沿实际数据流评审。规则与抑制说明见 [audit.md](scientific-coding/references/audit.md)。多个子项目各自使用最近的 `scientific-code.toml`。

默认元数据模式检查结构、路径、派生哈希和可选审核绑定，并读取小型契约；完整模式另核对所有已完成产物的实际内容，与审批状态无关。`artifact_hash` 标识科学身份文件，`manifest_hash` 绑定包括运行记录在内的完整文件集合；运行时间不应进入科学身份。

需要哈希绑定产物时，使用生命周期工具：

```bash
python scientific-coding/scripts/scientific_artifact.py init <dir> --contract ProcessedDataset@1

# 补齐真实契约并生成数据后完成产物；默认没有人工审批记录。
python scientific-coding/scripts/scientific_artifact.py finalize <dir>
python scientific-coding/scripts/scientific_artifact.py verify <dir> --full
```

只有用户选定评审点时，才用 `finalize --request-review` 生成待评审记录。`verify --require-review` 另核对该决定。`approve <dir> --reviewer <id>` 是交互式记录工具，确认前总会核对完整内容；终端确认本身不能证明科学评审已经发生。完整目录的原子发布由示例 I/O 边界负责，单独 `finalize` 不等于原子发布。

`templates/` 中 JSON 是结构示意，零哈希和示例环境值必须换成真实值；TOML 模板可按实际研究修改。默认流程不复制 `approval.json` 模板。

## 回归与行为评测

以下命令均从本仓库根目录运行：

```bash
python -m unittest discover -s scientific-coding/tests
python scientific-coding/scripts/scientific_code_lint.py .

# 只检查评测器流程；mock 不计为模型成功或技能触发。
python scientific-coding/evals/run_evals.py --backend mock --repetitions 1

# 真实模型在独立临时项目中工作，可并发重复运行并与 baseline 比较。
python scientific-coding/evals/run_evals.py --backend claude --mode explicit --language zh --repetitions 3 --workers 12 --judge
python scientific-coding/evals/run_evals.py --backend claude --mode baseline --language zh --repetitions 3 --workers 12 --judge
```

`baseline` 只是不安装项目级技能副本，未隔离全局技能和环境指令，不能直接视为完全无技能对照。

真实 agent 使用本机 CLI 与其当前模型配置；`claude` 后端名称不保证实际供应商或模型身份。评测保留提示词、轨迹、修改、结果检查、linter 输出和独立评审。没有实际完成证据、评审未知、执行无效和 mock 冒烟运行分别记录，不能当作通过；技能触发以读取记录为证，不凭名字出现判断。模型评审不使用工具或写入权限。

单元及集成回归涵盖科学数值、样本血缘、同种子跨时间复现、旧结果保护、默认连续执行、显式暂停、外部数据篡改、内部避免重复验证和工具误报。GitHub 工作流位于仓库根目录 `.github/workflows/`。
