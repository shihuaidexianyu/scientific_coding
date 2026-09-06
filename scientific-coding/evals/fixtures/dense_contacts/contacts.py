"""
从已验证的 contact 分组生成振幅摘要，目前表达式和循环职责过于拥挤。

groups + labels + minimum_uv --> 启用 contact --> 数值、原因、展示行
"""


def sum_nonmissing(values):
    """边读取一次性迭代器边相加，忽略 None，保留零与负数。"""

    # 内联生成式需要先命名，重构时应继续保持逐项消费。
    return sum(value for value in values if value is not None)


def build_report(groups, preferred_labels, default_label, minimum_uv):
    """按启用顺序返回 contact、合格振幅、总和、原因映射和展示行。"""

    # 初始代码故意混合多层展开、筛选和条件选择，供可读性改进。
    selected = [record for group in groups for record in group if record["enabled"]]
    accepted = [value for record in selected for value in record["samples_uv"] if value is not None if value >= minimum_uv]
    contact_ids, reasons, rows = [], {}, []
    for record in selected:
        contact = record["contact"]
        values = [value for value in record["samples_uv"] if value is not None]
        reason = "missing" if not values else "below" if max(values) < minimum_uv else "retained"
        label = preferred_labels.get(contact) or record["label"] or default_label or contact
        contact_ids.append(contact)
        reasons[contact] = reason
        rows.append({"contact": contact, "label": label, "reason": reason, "peak_uv": max(values) if values else None})
    return {"contact_ids": contact_ids, "accepted_values_uv": accepted, "total_uv": sum(value for value in accepted), "reason_by_contact": reasons, "rows": rows}
