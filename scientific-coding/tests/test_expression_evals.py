"""浅层具名表达式评测的结构与真实语义回归。"""

from pathlib import Path
import shutil
import sys
import tempfile
import unittest


SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "evals"))
import expression_checks


REFERENCE = '''"""
按输入顺序整理 contact 的振幅与原因；无文件或配置读写。

groups --> 启用记录 --> 合格数值、原因和展示行
"""


def sum_nonmissing(values):
    filtered = (value for value in values if value is not None)
    return sum(filtered)


def enabled_group(group):
    selected = [record for record in group if record["enabled"]]
    return selected


def numeric_samples(record):
    samples = record["samples_uv"]
    values = [value for value in samples if value is not None]
    return values


def accepted_samples(values, minimum):
    selected = [value for value in values if value >= minimum]
    return selected


def choose_label(record, preferred_labels, default_label):
    contact = record["contact"]
    preferred = preferred_labels.get(contact)
    label = record["label"]
    if preferred:
        return preferred
    elif label:
        return label
    elif default_label:
        return default_label
    else:
        return contact


def measure_record(record, minimum):
    values = numeric_samples(record)
    if not values:
        return None, "missing"
    peak = max(values)
    if peak < minimum:
        return peak, "below"
    return peak, "retained"


def build_report(groups, preferred_labels, default_label, minimum_uv):
    selected = []
    for group in groups:
        enabled = enabled_group(group)
        selected.extend(enabled)
    accepted = []
    for record in selected:
        numeric = numeric_samples(record)
        group_values = accepted_samples(numeric, minimum_uv)
        accepted.extend(group_values)
    contact_ids = [record["contact"] for record in selected]
    measurements = []
    for record in selected:
        peak, reason = measure_record(record, minimum_uv)
        measurement = {"contact": record["contact"], "peak_uv": peak,
                       "reason": reason}
        measurements.append(measurement)
    reasons = {}
    for measurement in measurements:
        contact = measurement["contact"]
        reasons[contact] = measurement["reason"]
    pairs = zip(selected, measurements)
    rows = []
    for record, measurement in pairs:
        label = choose_label(record, preferred_labels, default_label)
        row = dict(measurement)
        row["label"] = label
        rows.append(row)
    total = sum(accepted)
    return {"contact_ids": contact_ids, "accepted_values_uv": accepted,
            "total_uv": total, "reason_by_contact": reasons, "rows": rows}
'''


class ExpressionEvalTests(unittest.TestCase):
    """结构判定和语义判定分别验证，避免漂亮源码掩盖行为改变。"""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="expression-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "project"
        shutil.copytree(expression_checks.FIXTURE, self.root)

    def reference(self, before=None, after=None):
        """写入可执行的浅层正例，或定点注入一种语义错误。"""
        text = REFERENCE
        if before is not None:
            self.assertIn(before, text)
            text = text.replace(before, after)
        (self.root / "contacts.py").write_text(text, encoding="utf-8")

    def assess(self):
        """调用远端评分使用的同一入口。"""
        return expression_checks.expression_outcome(self.root, {})

    def test_dense_fixture_has_correct_science_but_fails_structure(self):
        outcome = self.assess()
        self.assertFalse(outcome["pass"])
        science = outcome["dimensions"]["science"]
        self.assertTrue(science["pass"], science["failures"])
        failures = outcome["dimensions"]["expression_structure"]["failures"]
        rules = set()
        for item in failures:
            rules.add(item["rule"])
        self.assertIn("multiple_comprehension_for", rules)
        self.assertIn("inline_call_transformation", rules)
        self.assertIn("multi_level_fallback", rules)
        self.assertIn("nested_conditional_choice", rules)
        self.assertIn("line_width", rules)

    def test_named_reference_preserves_all_semantics_and_original_files(self):
        self.reference()
        outcome = self.assess()
        self.assertTrue(outcome["pass"], outcome)
        science = outcome["dimensions"]["science"]
        self.assertTrue(science["original_files_unchanged"])

    def test_strict_threshold_fails_independent_boundary_oracle(self):
        self.reference("value >= minimum", "value > minimum")
        outcome = self.assess()
        self.assertTrue(outcome["dimensions"]["expression_structure"]["pass"])
        self.assertFalse(outcome["dimensions"]["science"]["pass"])

    def test_zero_is_a_value_instead_of_missing(self):
        self.reference("if value is not None", "if value")
        outcome = self.assess()
        self.assertFalse(outcome["dimensions"]["science"]["pass"])

    def test_empty_string_fallback_semantics_must_not_change(self):
        self.reference("if preferred:", "if preferred is not None:")
        outcome = self.assess()
        self.assertFalse(outcome["dimensions"]["science"]["pass"])

    def test_sorting_output_changes_observed_contact_order(self):
        self.reference("total = sum(accepted)",
                       "contact_ids.sort()\n    total = sum(accepted)")
        outcome = self.assess()
        self.assertFalse(outcome["dimensions"]["science"]["pass"])

    def test_shallow_eager_list_still_loses_lazy_consumption(self):
        original = "(value for value in values if value is not None)"
        replacement = "[value for value in values if value is not None]"
        self.reference(original, replacement)
        outcome = self.assess()
        self.assertTrue(outcome["dimensions"]["expression_structure"]["pass"])
        failures = outcome["dimensions"]["science"]["failures"]
        self.assertTrue(any("惰性" in item for item in failures), failures)

    def test_public_keyword_parameter_names_are_preserved(self):
        self.reference("preferred_labels", "label_options")
        outcome = self.assess()
        failures = outcome["dimensions"]["science"]["failures"]
        self.assertIn("build_report 公共调用约定改变", failures)

    def test_moving_dense_expression_to_another_module_does_not_hide_it(self):
        self.reference()
        path = self.root / "extra.py"
        dense = (
            "def hidden(groups):\n"
            "    return [x for g in groups for x in g]\n"
        )
        path.write_text(dense, encoding="utf-8")
        outcome = self.assess()
        failures = outcome["dimensions"]["expression_structure"]["failures"]
        self.assertTrue(any(item["file"] == "extra.py" for item in failures))

    def test_unicode_width_tabs_and_explicit_structures_are_checked(self):
        self.reference()
        lines = [
            "#" + "中" * 79,
            "#" + "中" * 80,
            'value = "\\t"',
            "\t# tab indentation",
            "def bad(rows, f):",
            "    out = f(*(x for x in rows))",
            "    nested = [[x for x in rows] for row in rows]",
            "    selected = [x for x in rows if x if x > 0]",
            "    choices = [1 if x else 0 for x in rows]",
            "    for row in rows:",
            "        if row:",
            "            if row > 0:",
            "                pass",
        ]
        path = self.root / "checks.py"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        structure = expression_checks.source_structure(self.root)
        rules = set()
        for item in structure["failures"]:
            rules.add(item["rule"])
        self.assertIn("inline_call_transformation", rules)
        self.assertIn("nested_comprehension", rules)
        self.assertIn("multiple_comprehension_if", rules)
        self.assertIn("conditional_comprehension", rules)
        self.assertIn("循环内 if 再嵌套 if", rules)
        widths = []
        for item in structure["failures"]:
            if item["rule"] == "line_width":
                widths.append(item)
        self.assertEqual(len(widths), 1)
        self.assertEqual(widths[0]["width"], 81)

    def test_simple_conditions_elif_and_literal_options_are_allowed(self):
        self.reference()
        text = '''def acceptable(rows, f, a, b, c):
    options = f(1, "fixed", (1, 2), enabled=True)
    okay = a and b and c
    for row in rows:
        if not row:
            continue
        elif row > 1:
            options = row
        else:
            options = None
    return options, okay
'''
        (self.root / "options.py").write_text(text, encoding="utf-8")
        structure = expression_checks.source_structure(self.root)
        self.assertTrue(structure["pass"], structure["failures"])


if __name__ == "__main__":
    unittest.main()
