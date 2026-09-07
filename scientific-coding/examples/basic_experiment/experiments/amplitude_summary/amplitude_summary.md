# 振幅下限筛选后的描述性汇总

## 目的与设计

演示同一试次表经过阈值筛选后，保留数量与平均振幅如何变化。这是描述性
教学实验，不检验总体假设、不提供显著性或置信区间。四行合成数据不代表
真实人群；每行是一个试次，ID 为 trial_id，振幅单位为微伏。

初始输入是 UTF-8 的 data/trials.csv，字段为 trial_id、amplitude_uv。
编排按 CSV 列名读取，振幅转为 float，顺序不变。参数来自同目录唯一的
amplitude_summary.toml，preprocess.floor_uv 是演示阈值，不声称有生理依据。
具体数值以 TOML 为准；本实验无随机过程或可调并行策略。

```text
统一 TOML + CSV --> 编排读取/有限性检查 --> 筛选 stage
    --> 保留行 + 排除原因 --> 汇总 stage --> 编排保存结果
```

人工修改 CSV/TOML 可写入 nan/inf，float 和 TOML 解析会接受它们，可能
静默改变筛选或均值，因此编排核对实际数值的有限性一次。其他字段由原生
读取/解析错误处理。保留集为空时 mean 自然报错，不重复增加空集检查。

## 中间数据与产物

筛选返回两份内存列表：retained 保留 trial_id/amplitude_uv，exclusions
保存被排除 trial_id 和中文 reason。汇总返回 count 整数和 mean_uv 浮点数。
编排在 runs/<尝试编号>/result.json 中保存这三个具名产物；JSON 按字段读取。
只解释被保留的试次，不能将筛选后的均值当作原始数据或总体的无偏估计。

从 basic_experiment 目录执行：

```sh
python experiments/amplitude_summary/run_amplitude_summary.py
```

其他工作目录可用脚本绝对路径启动，默认配置仍取脚本同目录 TOML。
也可以显式传入 TOML 路径，配置内部路径仍相对选中 TOML。
完整日志、状态、配置/源码/输入快照和时间资源记录在
executions/attempts/<编号>/，索引在 executions/index/，包含失败尝试。

算法时间 O(N)，额外内存 O(N)。这个小例由启动和文件记录开销主导；
没有目标机器测量时不预填秒数，实际耗时以运行记录为准。
