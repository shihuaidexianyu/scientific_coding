"""
检查纯 contact 模块的浅层具名表达式，并独立执行语义探针。

源码/配置 --> AST 与 80 字符检查 --> 明确结构缺陷
隔离模块 + 新输入 --> 独立语义 oracle --> 数值、顺序、空值与惰性证据

AST 只判定明确语法结构，不猜测一个循环是否承担多项科学职责；该项交评读。
"""

from __future__ import annotations

import ast
import copy
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import execution_checks


COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
AGGREGATIONS = {
    "sum", "min", "max", "sorted", "list", "set", "tuple", "dict",
    "map", "filter",
}
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "dense_contacts"
EXCLUDED = {
    ".git", ".claude", ".agents", ".codex", "__pycache__", ".venv",
    "venv", "node_modules", "artifacts", "results", "executions",
}


def literal(node: ast.AST) -> bool:
    """判断是否为固定字面值，避免要求每个常量都建立临时变量。"""
    try:
        ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return False
    return True


def inline_transformation(node: ast.AST) -> bool:
    """仅识别明确内联生成、聚合或含变量的复合构造，不推断任意函数语义。"""
    if isinstance(node, ast.Starred):
        node = node.value
    if isinstance(node, COMPREHENSIONS):
        return True
    containers = (ast.List, ast.Set, ast.Dict, ast.Tuple)
    if isinstance(node, containers) and not literal(node):
        return True
    if isinstance(node, ast.Call):
        function = node.func
        if isinstance(function, ast.Name):
            return function.id in AGGREGATIONS
    return False


def loop_control_issues(loop: ast.AST) -> list[tuple[int, str]]:
    """定位循环内再嵌循环或两层 if；elif 保持同一决策层级。"""
    failures = []

    def visit_statements(statements, if_depth):
        for statement in statements:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):
                failures.append((statement.lineno, "循环体内又嵌套循环"))
                continue
            if isinstance(statement, ast.If):
                visit_if(statement, if_depth)
                continue
            for field, value in ast.iter_fields(statement):
                if field in {"body", "orelse", "finalbody"}:
                    if isinstance(value, list):
                        visit_statements(value, if_depth)
                if field in {"handlers", "cases"}:
                    for handler in value:
                        visit_statements(handler.body, if_depth)

    def visit_if(statement, depth):
        if depth >= 1:
            failures.append((statement.lineno, "循环内 if 再嵌套 if"))
        visit_statements(statement.body, depth + 1)
        alternate = statement.orelse
        if len(alternate) == 1 and isinstance(alternate[0], ast.If):
            visit_if(alternate[0], depth)
        else:
            visit_statements(alternate, depth + 1)

    visit_statements(loop.body, 0)
    return failures


def source_structure(root: Path) -> dict:
    """检查实际 Python/TOML 物理行及明确 AST 结构，返回文件行号证据。"""
    failures, inspected = [], []
    for directory, children, names in os.walk(root):
        children[:] = sorted(set(children) - EXCLUDED)
        for name in sorted(names):
            path = Path(directory) / name
            if path.suffix not in {".py", ".toml"}:
                continue
            relative = path.relative_to(root).as_posix()
            inspected.append(relative)
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                failures.append({"file": relative, "rule": "source_read",
                                 "detail": str(error)})
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if len(line) > 80:
                    failures.append({"file": relative, "line": number,
                                     "rule": "line_width", "width": len(line)})
                if "\t" in line:
                    failures.append({"file": relative, "line": number,
                                     "rule": "tab_character"})
            if path.suffix != ".py":
                continue
            try:
                tree = ast.parse(text)
            except SyntaxError as error:
                failures.append({"file": relative, "line": error.lineno,
                                 "rule": "python_syntax", "detail": str(error)})
                continue
            issues = []
            for node in ast.walk(tree):
                if isinstance(node, COMPREHENSIONS):
                    generators = node.generators
                    if len(generators) != 1:
                        issues.append(
                            (node.lineno, "multiple_comprehension_for")
                        )
                    filters = 0
                    for generator in generators:
                        filters += len(generator.ifs)
                    if filters > 1:
                        issues.append(
                            (node.lineno, "multiple_comprehension_if")
                        )
                    for nested in ast.walk(node):
                        if nested is node:
                            continue
                        if isinstance(nested, COMPREHENSIONS):
                            issues.append((node.lineno, "nested_comprehension"))
                        if isinstance(nested, ast.IfExp):
                            issues.append(
                                (node.lineno, "conditional_comprehension")
                            )
                if isinstance(node, ast.Call):
                    arguments = list(node.args)
                    for keyword in node.keywords:
                        arguments.append(keyword.value)
                    for argument in arguments:
                        for nested in ast.walk(argument):
                            if inline_transformation(nested):
                                issues.append((node.lineno,
                                               "inline_call_transformation"))
                                break
                if isinstance(node, ast.BoolOp):
                    if isinstance(node.op, ast.Or) and len(node.values) > 2:
                        issues.append((node.lineno, "multi_level_fallback"))
                    for value in node.values:
                        if isinstance(value, (ast.BoolOp, ast.IfExp)):
                            issues.append((node.lineno, "mixed_short_circuit"))
                if isinstance(node, ast.IfExp):
                    for value in (node.test, node.body, node.orelse):
                        if isinstance(value, (ast.IfExp, ast.BoolOp)):
                            issues.append(
                                (node.lineno, "nested_conditional_choice")
                            )
                if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
                    issues.extend(loop_control_issues(node))
            for number, rule in sorted(set(issues)):
                failure = {"file": relative, "line": number, "rule": rule}
                failures.append(failure)
    return {"pass": not failures, "failures": failures, "files": inspected,
            "scope": "明确 AST 结构与 Unicode 物理行宽；循环职责交由评读"}


def signature_shape(arguments: ast.arguments) -> dict:
    """比较调用约定而不限制新增类型注解。"""
    positional, positional_only, keyword_only = [], [], []
    for item in arguments.args:
        positional.append(item.arg)
    for item in arguments.posonlyargs:
        positional_only.append(item.arg)
    for item in arguments.kwonlyargs:
        keyword_only.append(item.arg)
    defaults = []
    for item in arguments.defaults:
        defaults.append(ast.dump(item))
    keyword_defaults = []
    for item in arguments.kw_defaults:
        if item is None:
            keyword_defaults.append(None)
        else:
            keyword_defaults.append(ast.dump(item))
    return {
        "positional": positional, "positional_only": positional_only,
        "keyword_only": keyword_only, "defaults": defaults,
        "keyword_defaults": keyword_defaults,
        "vararg": arguments.vararg.arg if arguments.vararg else None,
        "kwarg": arguments.kwarg.arg if arguments.kwarg else None,
    }


def check_public_signatures(root: Path) -> list[str]:
    """保留两个原有纯函数的参数名、位置与默认值。"""
    expected = ast.parse((FIXTURE / "contacts.py").read_text(encoding="utf-8"))
    actual = ast.parse((root / "contacts.py").read_text(encoding="utf-8"))
    functions = {}
    for node in actual.body:
        if isinstance(node, ast.FunctionDef):
            functions[node.name] = node
    failures = []
    for node in expected.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        target = functions.get(node.name)
        if target is None:
            failures.append(node.name + " 公共函数缺失")
            continue
        if signature_shape(node.args) != signature_shape(target.args):
            failures.append(node.name + " 公共调用约定改变")
    return failures


def oracle(arguments: list) -> dict:
    """使用显式顺序步骤独立定义原接口语义，不导入被测函数。"""
    groups, preferred, default, minimum = arguments
    selected = []
    for group in groups:
        selected.extend(group)
    enabled = []
    for row in selected:
        if not row["enabled"]:
            continue
        enabled.append(row)
    contacts, accepted, reasons, rows = [], [], {}, []
    for row in enabled:
        contact = row["contact"]
        values = []
        for value in row["samples_uv"]:
            if value is not None:
                values.append(value)
        peak = None
        if values:
            peak = max(values)
        if peak is None:
            reason = "missing"
        elif peak < minimum:
            reason = "below"
        else:
            reason = "retained"
        label = preferred.get(contact)
        if not label:
            label = row["label"]
        if not label:
            label = default
        if not label:
            label = contact
        contacts.append(contact)
        reasons[contact] = reason
        rows.append({"contact": contact, "label": label, "reason": reason,
                     "peak_uv": peak})
        for value in values:
            if value >= minimum:
                accepted.append(value)
    total = 0
    for value in accepted:
        total += value
    return {"contact_ids": contacts, "accepted_values_uv": accepted,
            "total_uv": total, "reason_by_contact": reasons, "rows": rows}


def probe_inputs() -> list[list]:
    """构造空输入、混合组和零/负阈值，区分顺序与缺失判定错误。"""
    first = [
        {"contact": "z", "enabled": True, "label": "row-z",
         "samples_uv": [None, 0.0, 0.5, -1.0]},
        {"contact": "off", "enabled": False, "label": "disabled",
         "samples_uv": [900.0]},
        {"contact": "a", "enabled": True, "label": None,
         "samples_uv": [None, None]},
    ]
    second = [
        {"contact": "m", "enabled": True, "label": "",
         "samples_uv": [-3.0, -0.5]},
        {"contact": "b", "enabled": True, "label": "row-b",
         "samples_uv": [2.0, 0.5, None, 1.25]},
    ]
    groups = [first, [], second]
    labels = {"z": "", "a": None, "m": "override-m", "b": "preferred-b"}
    return [
        [copy.deepcopy(groups), dict(labels), "default", 0.5],
        [copy.deepcopy(groups), dict(labels), "", 0.0],
        [[copy.deepcopy(second), copy.deepcopy(first)], {}, "", -0.5],
        [[], {}, "", 0.0],
        [[[], []], {}, "fallback", -1.0],
    ]


PROBE = r'''
import copy
import importlib.util
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
import contacts

data = json.loads(sys.stdin.read())
answers = []
for arguments in data:
    original = copy.deepcopy(arguments)
    result = contacts.build_report(*arguments)
    answer = {"result": result, "inputs_unchanged": arguments == original}
    answers.append(answer)

events = []
class Number(float):
    def __add__(self, other):
        events.append("add:" + str(float(other)))
        return Number(float(self) + float(other))

    def __radd__(self, other):
        events.append("add:" + str(float(self)))
        return Number(float(other) + float(self))

class Once:
    def __init__(self):
        self.iterator = iter([Number(1), None, Number(0), Number(-2)])
        self.started = False
        self.position = 0

    def __iter__(self):
        if self.started:
            raise RuntimeError("one-shot iterator consumed twice")
        self.started = True
        return self

    def __next__(self):
        events.append("next:" + str(self.position))
        self.position += 1
        return next(self.iterator)

lazy_sum = contacts.sum_nonmissing(Once())
ordinary = [contacts.sum_nonmissing(iter(values)) for values in (
    [], [None, None], [0.0, None, -2.0, 3.5]
)]
print(json.dumps({"answers": answers, "lazy_sum": lazy_sum,
                  "events": events, "ordinary_sums": ordinary}))
'''


def same_values(actual, expected) -> bool:
    """递归对照容器结构和顺序，数值仅允许浮点舍入误差。"""
    if type(expected) in (int, float):
        if type(actual) not in (int, float):
            return False
        return math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12)
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or actual.keys() != expected.keys():
            return False
        for key, value in expected.items():
            if not same_values(actual[key], value):
                return False
        return True
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return False
        for observed, wanted in zip(actual, expected):
            if not same_values(observed, wanted):
                return False
        return True
    return type(actual) is type(expected) and actual == expected


def expression_outcome(workdir: Path, case: dict) -> dict:
    """组合机械结构与隔离语义探针，保留原代码和作者已有产物。"""
    structure = source_structure(workdir)
    failures, invocation = [], None
    before = execution_checks.fingerprint(workdir)
    arguments = probe_inputs()
    expected = []
    for values in arguments:
        expected.append(oracle(values))
    try:
        failures.extend(check_public_signatures(workdir))
        with tempfile.TemporaryDirectory(prefix="expr-eval-") as temporary:
            project = Path(temporary) / "project"
            ignored = shutil.ignore_patterns(*EXCLUDED)
            shutil.copytree(workdir, project, ignore=ignored)
            environment = dict(os.environ)
            environment["PYTHONIOENCODING"] = "utf-8"
            command = [sys.executable, "-I", "-c", PROBE, str(project)]
            result = subprocess.run(
                command, cwd=project, env=environment,
                input=json.dumps(arguments), capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=20,
            )
            invocation = {"exit_code": result.returncode,
                          "stdout": result.stdout, "stderr": result.stderr}
            if result.returncode:
                raise ValueError("纯函数探针异常退出")
            observed = json.loads(result.stdout)
            answers = observed["answers"]
            if len(answers) != len(expected):
                failures.append("独立输入结果数量不一致")
            for index, wanted in enumerate(expected):
                if index >= len(answers):
                    break
                answer = answers[index]
                if not same_values(answer.get("result"), wanted):
                    failures.append(f"第 {index} 组的数值/顺序/空值/标签选择不符")
                if answer.get("inputs_unchanged") is not True:
                    failures.append(f"第 {index} 组修改了输入")
            expected_events = [
                "next:0", "add:1.0", "next:1", "next:2", "add:0.0",
                "next:3", "add:-2.0", "next:4",
            ]
            if observed.get("events") != expected_events:
                failures.append("sum_nonmissing 改变了惰性求值或相加顺序")
            if not same_values(observed.get("lazy_sum"), -1.0):
                failures.append("一次性迭代器求和结果不符")
            if not same_values(observed.get("ordinary_sums"), [0, 0, 1.5]):
                failures.append("空值、零值或负数求和结果不符")
    except subprocess.TimeoutExpired as error:
        invocation = {"timed_out": True, "stdout": str(error.stdout),
                      "stderr": str(error.stderr)}
        failures.append("纯函数探针超过 20 秒")
    except (
        OSError, ValueError, TypeError, KeyError, SyntaxError, AttributeError
    ) as error:
        failures.append(type(error).__name__ + ": " + str(error))
    unchanged = before == execution_checks.fingerprint(workdir)
    if not unchanged:
        failures.append("原源码或已有产物在探针期间被修改")
    science = {"pass": not failures, "failures": failures,
               "inputs": arguments, "expected": expected,
               "invocation": invocation, "original_files_unchanged": unchanged}
    return {"pass": structure["pass"] and science["pass"],
            "probe_version": "shallow-expressions-v1",
            "dimensions": {"expression_structure": structure,
                           "science": science},
            "semantic_review_required": ["循环单职责", "具名步骤的实际用途",
                                         "中文说明真实且完备"]}
