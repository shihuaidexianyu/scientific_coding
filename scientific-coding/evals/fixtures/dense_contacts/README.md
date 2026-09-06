# 拆清楚纯内存 contact 分析

`contacts.py` 是其他流水线调用的纯数据模块，没有 CLI、TOML 或文件读写。
保持两个公共函数的签名与行为，不新增运行入口、日志目录或调度器。
可以添加有实际用途的辅助函数。

`build_report(groups, preferred_labels, default_label, minimum_uv)` 的输入已经
由外部入口保证有效：groups 是记录列表的列表；记录包含唯一字符串 contact、
布尔 enabled、字符串或 None 的 label、浮点数或 None 的 samples_uv 列表。
preferred_labels 是 contact 到字符串或 None 的映射；default_label 是字符串。
minimum_uv 是有限浮点数，单位微伏。函数不得修改输入。

行为约定：

- 按 group 顺序及各组原顺序收集 enabled 的记录，不排序或去重。
- accepted_values_uv 按 contact 再按样本的原顺序收集非 None 且 >= minimum_uv
  的值；0 是正常数值，负阈值也允许；total_uv 是这些值之和。
- contact_ids 包含所有启用 contact，包括没有可用数值的 contact。
- reason_by_contact 与 rows 的 reason：没有非 None 值为 missing；
  有数值但最大值低于阈值为 below；否则 retained。peak_uv 是非 None 值的
  最大值，没有可用值则为 None，不能擅自改成绝对值峰值。
- label 按 preferred_labels、记录 label、default_label、contact 依次选择
  第一个非空字符串。这是当前已经约定的 truthy fallback：空字符串会继续
  后备，不能在可读性重构时擅自改成仅 None 才缺失。
- 返回字典保留 contact_ids、accepted_values_uv、total_uv、reason_by_contact、
  rows 五个键。rows 每项保留 contact、label、reason、peak_uv。

`sum_nonmissing(values)` 接收一次性数值迭代器或普通可迭代对象，忽略 None，
保留 0 与负数，并返回总和。保持边消费边相加，不先转成完整列表，也不重复
遍历。输入可以是 float 的子类；不能擅自强制转换而改变其相加行为。

请按照当前 skill 的表达式、80 字符、先命名再传递和循环职责要求完成重构，
完善真实中文说明并实际验证不同输入。保留必要输出结构与惰性/空值语义；
单个循环可以有多个语句，但应能用一个明确操作解释其职责。
