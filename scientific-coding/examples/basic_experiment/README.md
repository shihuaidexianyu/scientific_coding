# 基础实验示例

先读 [实验设计](experiments/amplitude_summary/amplitude_summary.md)，再读
同目录的 TOML 和 run_amplitude_summary.py，最后读 stages/amplitudes.py。
它们展示统一参数、专属顺序编排、外置必要检查、中文说明和描述性科学计算。
从本目录运行：

```sh
python experiments/amplitude_summary/run_amplitude_summary.py
```

默认数据有四行，阈值等号保留，结果应有三个保留试次、均值 1.0 微伏，
排除 t1。无随机推断，无配置继承、通用 DAG、契约版本或审批协议。
每次新运行分别保存结果和完整诊断，详见实验 MD。

runtime_support.py 复用已回归的进程级记录器，只负责输出捕获、时间、来源
快照及索引；不是科学方法示例，普通阅读无需打开。修改记录设施时才按
运行记录要求查看。该文件来自旧集成示例的独立记录模块，不依赖旧产物工具。
保留外层记录器避免在业务中插入日志包装，也避免重新实现一套监测设施。

可读性工具通过只证明覆盖到的结构和格式；科学行为及错误路径另由测试验证。
本例不说明所有研究都需要有限性检查，是否检查仍按实际触发场景判断。
