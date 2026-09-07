# 按需扩展，不作为普通实验的默认流程

只有当前任务明确需要对应能力时才读取。核心编排、中文说明、运行记录和
科学准确性要求不因使用扩展而放宽；高级文件名、JSON 模板和协议不必复制。

| 实际需求 | 文档 |
|---|---|
| 已测瓶颈的性能优化、前后对照 | [optimization.md](optimization.md) |
| 长任务的恢复、分片和中断等价性 | [resumability.md](resumability.md) |
| 外部产物的契约版本、精确哈希复用或用户指定审批协议 | [artifact.md](artifact.md) |
| 具体推断设计需要更多方法提醒 | [statistical_validity.md](statistical_validity.md) |
| 正在使用仓库的特定静态检查工具 | [lint.md](lint.md) |

高级运行机制的历史集成实现位于
[minimal_pipeline](../examples/minimal_pipeline/README.md)。它不是当前基础
架构示例，保留用于兼容和回归；其多配置及 stage 内检查不可作为新实验写法。
scripts/ 提供按需使用的技能工具，不要求复制进科研程序。本地开发测试、
评测和报告不随技能发布；保留历史失败证据，不用成功重试覆盖失败。
