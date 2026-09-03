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
│   └── optimization_report.json
├── scripts/
│   └── scientific_code_lint.py
└── evals/
    └── cases.toml
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

CI 中完成现有 warning 的人工分类后，可以启用严格模式：

```bash
python <skill-dir>/scripts/scientific_code_lint.py <project-root> --strict-warnings
```

输出 JSON：

```bash
python <skill-dir>/scripts/scientific_code_lint.py <project-root> --format json
```

Linter 检查 Stage-to-Stage import、复杂科学 CLI、Artifact/Approval 完整性、View 与 Stage 耦合、隐藏网络输入等 hard errors，并对隐藏科学分支、过早抽象、checkpoint、无 benchmark 优化、宽泛异常和输入 mutation 等风险给出 warnings。规则说明见 [audit.md](scientific-coding/references/audit.md)。

Artifact 完整性采用两层 hash：

- `artifact_hash` 标识 contract 与 scientific identity files；
- `manifest_hash` 绑定全部数据、运行时和 provenance 文件哈希。

这样 `run.json` 可以记录输出的 `artifact_hash`，同时避免自引用哈希循环。

## Templates 与 Evals

`templates/` 提供可修改的 Stage header、Artifact Contract、manifest、approval、pipeline、runtime、run provenance 和优化报告。示例值必须替换为实际研究语义，不能直接作为正式产物使用。

[行为评测集](scientific-coding/evals/cases.toml)包含 12 个案例，覆盖科学分支、重复逻辑、短任务优化、多日计算、I/O 瓶颈、无效并行、checkpoint、绘图污染、Stage 耦合、复杂 CLI 和过早框架化。

## 验证 Skill

```bash
python <skill-creator-dir>/scripts/quick_validate.py scientific-coding
python scientific-coding/scripts/scientific_code_lint.py . --changed-only --strict-warnings
```

当前版本已通过 Skill 结构校验、Python AST 校验、JSON/TOML 解析、文档链接检查和 linter 隔离行为测试。

