# Scientific Coding Skill

`scientific-coding` 是一套面向 AI Agent 的科研流水线编码规范。它把科研代码视为“可执行的科学方法描述”，优先保证科学正确性、人工可审计性、显式数据血缘和可复现性，再考虑性能、复用和代码紧凑度。

## 适用范围

适用于：

- 数据预处理和特征构建
- 科学或统计分析
- 模型评估、交叉验证、bootstrap 和 permutation
- 科研实验脚本与科学可视化
- 长时间科研计算、性能优化和续跑设计

默认不用于通用数值库、dataset SDK、parser、基础设施、部署系统或生产服务。完整的触发边界和决策规则见 [SKILL.md](scientific-coding/SKILL.md)。

## 核心模型

```text
Declared Artifact + TOML Config + Code
                    |
                    v
             Scientific Stage
                    |
                    v
            Immutable Artifact
                    |
                    v
             Human Approval
```

Stage 之间只通过 Artifact Contract 连接。下游 Stage 不导入上游 Stage 的 Python 实现；具有不同科学含义的处理过程优先使用独立文件，而不是隐藏在运行时模式分支中。

## 目录结构

```text
scientific-coding/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── stage.md
│   ├── artifact.md
│   ├── view.md
│   ├── optimization.md
│   ├── resumability.md
│   └── audit.md
├── templates/
│   ├── stage_header.md
│   ├── artifact_contract.toml
│   ├── artifact_manifest.json
│   ├── approval.json
│   ├── pipeline.toml
│   ├── run_manifest.json
│   ├── runtime.json
│   ├── optimization_report.json
│   └── scientific-code.toml
├── scripts/
│   ├── scientific_code_lint.py
│   └── scientific_artifact.py
├── tests/
│   ├── test_linter.py
│   └── test_artifact.py
└── evals/
    ├── cases.toml
    ├── run_evals.py
    ├── graders.py
    └── fixtures/
```

`SKILL.md` 只保留高频规则与任务路由；Stage、Artifact、View、优化、续跑和审计细节按需从 `references/` 加载。

## 使用

将整个 `scientific-coding/` 目录放入 `$CODEX_HOME/skills/`（未设置 `CODEX_HOME` 时通常为 `~/.codex/skills/`），然后显式调用：

```text
Use $scientific-coding to audit this analysis stage.
```

该 skill 默认允许自动触发，因此处理科研 pipeline 任务时也可以由 Codex 自动选择。

## Deterministic Linter

在科研项目根目录运行：

```bash
python <skill-dir>/scripts/scientific_code_lint.py <project-root> --changed-only
```

CI 中对干净 checkout 使用 merge-base diff（`--changed-only` 在已提交的工作区检查不到任何文件）：

```bash
python <skill-dir>/scripts/scientific_code_lint.py . --base-ref origin/main --strict-warnings
```

输出 JSON：

```bash
python <skill-dir>/scripts/scientific_code_lint.py <project-root> --format json
```

项目可在根目录用 `scientific-code.toml` 显式声明目录角色（模板见 [templates/scientific-code.toml](scientific-coding/templates/scientific-code.toml)）：

```toml
[scope]
stage_roots = ["stages", "analysis"]
view_roots = ["figures", "views"]
artifact_roots = ["artifacts"]
infrastructure_roots = ["src", "infra"]
```

Stage/View 识别优先级：文件内 marker 注释（`# scientific-code: stage`）> 配置声明的 roots > 命名约定（`stages/` 目录、常见文件名前缀）。`infrastructure_roots` 下的文件不受命名纪律启发式约束，与 scope gate 一致。

Linter 检查 Stage-to-Stage import（含经本地模块的传递依赖）、科学参数 CLI、Artifact/Approval 完整性、View 与 Stage 耦合、隐藏网络输入等 hard errors，并对隐藏科学分支、过早抽象、checkpoint、无效优化证据、宽泛异常和输入 mutation 等风险给出 warnings。规则说明见 [audit.md](scientific-coding/references/audit.md)。

Artifact 完整性分两级：默认元数据模式校验 schema、路径、派生 hash 和 approval 绑定，不读取 payload（大数据下保持廉价）；`--full-artifact-checks` 额外重算 approved artifact 与 recorded input 的 payload 哈希，用于发布验证或定期完整性审计：

```bash
python <skill-dir>/scripts/scientific_code_lint.py . --full-artifact-checks
```

Artifact 完整性采用两层 hash：

- `artifact_hash` 标识 contract 与 scientific identity files；
- `manifest_hash` 绑定全部数据、运行时和 provenance 文件哈希。

这样 `run.json` 可以记录输出的 `artifact_hash`，同时避免自引用哈希循环。

## Artifact 生命周期工具

哈希协议（identity files → `artifact_hash` → `run.json` → `manifest_hash` → approval）不应由 agent 手写。`scripts/scientific_artifact.py` 是唯一的参考实现：

```bash
python <skill-dir>/scripts/scientific_artifact.py init     <dir> --contract ProcessedDataset@1
python <skill-dir>/scripts/scientific_artifact.py finalize <dir>   # 算哈希、写 manifest、提交待审核
python <skill-dir>/scripts/scientific_artifact.py verify   <dir> [--full]
python <skill-dir>/scripts/scientific_artifact.py approve  <dir> --reviewer <id>
```

**批准是人的动作。** `finalize` 写入 `pending_review` 记录（agent 的"提交审核"通道）；`approve` 拒绝在非交互终端运行，并要求人工输入确认。Agent 永远不得创建或修改 approval 记录——这是 SKILL.md 的 Non-Negotiable Rule。

## Templates 与 Evals

`templates/` 提供可修改的 Stage header、Artifact Contract、manifest、approval、pipeline、runtime、run provenance、优化报告和项目 scope 配置。示例值必须替换为实际研究语义，不能直接作为正式产物使用。

[行为评测集](scientific-coding/evals/cases.toml)包含 16 个案例，覆盖科学分支、重复逻辑、短任务优化、多日计算、I/O 瓶颈、无效并行、checkpoint、绘图污染、Stage 耦合、复杂 CLI、过早框架化、agent 自我批准、reusable library / simulation engine negative control 和存量 Hydra 项目。每个案例可带真实 fixture 仓库（`evals/fixtures/`）、机器可判定的 `fail_if_patterns` 和中文 prompt。

评测不再是纸面规格——用 runner 实际执行：

```bash
# 验证 harness 管线（不调用 agent）
python evals/run_evals.py --backend mock --mode explicit

# 真实评测:explicit / implicit / baseline(无 skill 对照)
python evals/run_evals.py --backend claude --mode explicit --repetitions 5
python evals/run_evals.py --backend codex --mode implicit --language zh --judge
python evals/run_evals.py --backend claude --mode baseline --cases bad_parallelism
```

每次运行保存 prompt、trajectory、git diff、linter 输出和 verdict 到 `evals/results/<timestamp>/`，并聚合 summary。`--judge` 启用 LLM rubric 评审（消耗 token）。注意：真实 backend 会以跳过权限确认的方式在一次性 fixture 仓库中运行 agent，请自行审视后执行。

## 验证 Skill

```bash
python scientific-coding/scripts/scientific_code_lint.py . --changed-only
python -m unittest discover -s scientific-coding/tests -v
```

`tests/` 为每条 linter 规则提供 positive / negative / 误报回归 / suppression fixture（含 infrastructure 误报、中文 docstring、占位优化报告、第三方 `stages` 包、传递 import 等历史缺陷的回归测试），并覆盖 artifact CLI 的完整生命周期与非 TTY 批准拒绝。集成测试额外保证：`examples/minimal_pipeline` 以 `--full-artifact-checks` 全绿、全流程在临时目录从零重建后仍全绿、同 seed 重跑产生相同 artifact_hash、以及 `pending_review` 状态的 artifact 会阻断下游 stage 运行。

