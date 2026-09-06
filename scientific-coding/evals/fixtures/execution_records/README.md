# 小型振幅分析的运行记录改进

当前 `analysis.py` 的科学计算可用，但运行记录缺失，且结果会被重跑覆盖。
请按当前 scientific-coding skill 改进运行记录、失败诊断及中文说明，保持科学规则。
只使用 Python 标准库；不建立新调度器。`diagnostic_child.py` 是已有外部程序，
逐字保留它，并继续实际调用它，使其标准输出和标准错误进入本次日志。

数据是 UTF-8 CSV，每行一个试次：`trial_id` 为唯一字符串，
`condition` 为 control/treatment，`amplitude_uv` 为有限浮点数，单位微伏。
配置 `input.path` 相对配置文件所在目录解析；`analysis.minimum_uv` 是包含等号的下限。
分别取保留试次的条件均值，输出处理组减对照组的均值差；过滤后两组都必须非空。

保留以下运行接口，记录内部实现可以自由组织：

```text
python analysis.py --config PATH --records DIR --event-token TOKEN
python analysis.py --config PATH --records DIR --event-token TOKEN --fail-after-read
python analysis.py --list-runs --records DIR
```

前两条每调用一次创建新的尝试。第二条在读取数据后故意抛出带 TOKEN 的异常，
用于验证诊断；该执行选项不属于科学 TOML。坏 TOML 也必须留下失败记录。
最后一条只查询，不创建尝试；stdout 是一个 JSON 数组，每项必须有：

- `attempt_id`：唯一字符串；`status`：succeeded/failed；`exit_code`：真实整数退出码。
- `record_path`、`log_path`：执行 JSON 和完整合并日志的路径。
- `result_path`：成功的结果 JSON 路径，失败时可为 null。

这些路径使用绝对路径或相对 `--records` 的路径。执行 JSON 至少含对应 attempt_id、
status、exit_code、started_at_utc、finished_at_utc、wall_time_s；资源及阶段信息可在
顶层或 `progress` 内，CPU 秒数字段为 `cpu_time_s`，峰值 RAM 为 `peak_ram_bytes`。
资源缺失时用 null 并给原因；`stages` 条目含 name、wall_time_s、status。
来源结构自由，但应保留实际源码、配置和已读取 CSV 的 SHA-256，以及 Python 环境版本；
可使用相邻 JSON 来源索引或快照。来源记录也必须覆盖解析/计算失败。

结果 JSON 保持五个数值字段：`n_control`、`n_treatment`、`control_mean_uv`、
`treatment_mean_uv`、`difference_uv`。并发调用共享 DIR 时，所有尝试均能查询，
先前的日志、执行记录和结果不能被改动或清理。请实际运行改进后的入口验证，
保留验证产物；交付后用中文说明耗时、内存及批量效率估计的依据和局限。
