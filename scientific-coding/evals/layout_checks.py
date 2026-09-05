"""独立检查新 docstring 案例的可机械判定版式和合成科学数据。

这不是代码生成用格式器；说明是否真实、格式器实际覆盖哪些文件另由评读判定。
"""

from __future__ import annotations

import ast
import json
import math
from pathlib import Path
import re
import subprocess
import sys


HEADINGS = ("参数", "返回", "处理过程", "副作用")
ENTRY = re.compile(r"^(?P<indent>\s*)(?P<bullet>[-*]\s+)?`?(?P<name>['\"]?[A-Za-z_][\w\[\].'\"\-]*)`?\s*[:：]\s*(?P<type>\S.*)$")


def entries(lines: list[str], label: str, failures: list[str]) -> list[dict]:
    """识别独立名称/类型行，检查下一行缩进说明与项间空行。"""
    found = []
    parents = []
    for number, line in enumerate(lines):
        match = ENTRY.match(line)
        if not match:
            continue
        name, kind = match["name"], match["type"]
        indent = len(match["indent"])
        name = re.sub(r"\[['\"]?([^'\"\]]+)['\"]?\]", r".\1", name.strip("'\""))
        while parents and parents[-1][0] >= indent:
            parents.pop()
        parents.append((indent, name))
        found.append({"name": name, "type": kind, "indent": indent, "field": bool(match["bullet"]) or indent > 0,
                      "path": ".".join(item[1] for item in parents)})
        if match["bullet"] or indent > 0:
            continue
        if number and lines[number - 1].strip():
            failures.append(f"{label}: {name} 前缺少独立空段")
        if number + 1 >= len(lines) or not lines[number + 1].strip():
            failures.append(f"{label}: {name} 的说明没有紧随名称/类型行")
        elif len(lines[number + 1]) - len(lines[number + 1].lstrip()) <= indent:
            failures.append(f"{label}: {name} 的下一行说明没有增加缩进")
        if re.search(r"[。；;]|\s(?:表示|用于|包含|来自|返回|对应)", kind):
            failures.append(f"{label}: {name} 的类型行混入说明文字")
    return found


def check_layout(workdir: Path, specification: dict) -> dict:
    """检查声明源码中的真实文档字符串，返回版式缺陷和逐函数证据。"""
    failures = []
    evidence = {}
    semantic_review_required = []
    for relative, functions in specification.items():
        path = workdir / relative
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError) as error:
            failures.append(f"{relative}: 无法解析 {error}")
            continue
        module = ast.get_docstring(tree) or ""
        first = tree.body[0] if tree.body else None
        opener = source.splitlines()[first.lineno - 1].strip() if first else ""
        if not module or not re.fullmatch(r'(?:[rRuU])?(?:"""|\'\'\')', opener):
            failures.append(f"{relative}: 文件头需真实 module docstring 且三引号独占开头行")
        if not re.search(r"[\u4e00-\u9fff]", module):
            failures.append(f"{relative}: 文件头缺少中文用途说明")
        horizontal = re.search(r"(?:--?>|<--?|==?>|→|↓|\+[-─]+\+)", module)
        vertical = re.search(r"(?m)^\s*[|│]\s*$\s*^[ \t]*[vV↓][ \t]*$", module)
        if not horizontal and not vertical:
            failures.append(f"{relative}: 文件头缺少字符流程图的结构证据")
        nodes = {node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for name, expected in functions.items():
            node = nodes.get(name)
            if node is None:
                failures.append(f"{relative}: 缺少公共函数 {name}")
                continue
            doc = ast.get_docstring(node) or ""
            lines = doc.splitlines()
            label = f"{relative}:{name}"
            positions = [(i, line.strip().rstrip(":：")) for i, line in enumerate(lines)
                         if line.strip().rstrip(":：") in HEADINGS]
            evidence[label] = {"headings": [text for _, text in positions], "docstring": doc}
            if [text for _, text in positions] != list(HEADINGS):
                failures.append(f"{label}: 分节必须依次为参数、返回、处理过程、副作用")
                continue
            if not positions[0][0] or not re.search(r"[\u4e00-\u9fff]", "\n".join(lines[:positions[0][0]])):
                failures.append(f"{label}: 参数节之前缺少简短中文摘要")
            sections = {}
            for index, (start, heading) in enumerate(positions):
                end = positions[index + 1][0] if index + 1 < len(positions) else len(lines)
                block = lines[start + 1:end]
                while block and (not block[0].strip() or re.fullmatch(r"[-─=]+", block[0].strip())):
                    block.pop(0)
                sections[heading] = block
            parameters = entries(sections["参数"], label + ":参数", failures)
            names = {item["name"] for item in parameters if not item["field"]}
            actual_args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            for argument in actual_args:
                if argument.arg not in names:
                    failures.append(f"{label}: 参数 {argument.arg} 缺少独立名称和类型行")
            returned = entries(sections["返回"], label + ":返回", failures)
            if len([item for item in returned if not item["field"]]) < expected.get("return_items", 1):
                failures.append(f"{label}: 返回项未分别展开名称、类型和说明")
            for section, required in expected.get("fields", {}).items():
                listed = parameters if section == "参数" else returned
                for field in required:
                    if not any(item["path"] == field or item["path"].endswith("." + field) for item in listed):
                        top = field.split(".")[0]
                        if "." in field and any(item["path"] == top or item["path"].endswith("." + top) for item in listed):
                            semantic_review_required.append(f"{label}:{section}:{field}: 已列顶层字段；需评读同型映射说明是否完整表达实际键、类型、单位和嵌套")
                        else:
                            failures.append(f"{label}:{section}: 字典字段 {field} 未逐项展开")
            steps = [line.strip() for line in sections["处理过程"] if re.match(r"\s*\d+[.、)]\s*", line)]
            if not steps:
                failures.append(f"{label}: 处理过程缺少单独编号行")
            if any(len(re.findall(r"\d+[.、)]\s+", line)) > 1 for line in steps):
                failures.append(f"{label}: 多个处理步骤挤在同一行")
            if not any(re.search(r"[\u4e00-\u9fff]", line) for line in sections["副作用"]):
                failures.append(f"{label}: 副作用节缺少中文说明")
            long_lines = [i + 1 for i, line in enumerate(lines) if len(line) > 100]
            evidence[label]["lines_over_100_characters"] = long_lines
    return {"pass": not failures, "failures": failures, "evidence": evidence,
            "version": "typed-interface-v2-shared-mapping-aware",
            "semantic_review_required": semantic_review_required,
            "limits": "机械检查不证明类型、形状、单位、流程图或说明事实正确；同型映射允许共享结构说明，未匹配的叶路径必须独立语义评读；100 字符仅为明显长行诊断阈值。"}


def nested_science(workdir: Path) -> dict:
    """使用固定小数据的手算结果和第二组真实函数调用核验三维科学处理。"""
    failures = []
    evidence = {}
    try:
        summary = json.loads((workdir / "results/summary.json").read_text(encoding="utf-8"))
        corrected = json.loads((workdir / "results/corrected_epochs.json").read_text(encoding="utf-8"))
        expected = [[[0, 1, 2], [0, 2, 4]], [[0, 2, 4], [0, 3, 6]],
                    [[0, 3, 6], [0, 4, 8]], [[0, 4, 8], [0, 5, 10]]]
        if corrected != expected:
            failures.append("基线校正后的逐试次、通道、时间数值不正确")
        groups = summary["groups"]
        if groups["control"] != {"n_trials": 1, "mean_uv": [[0, 1, 2], [0, 2, 4]]}:
            failures.append("control 的数量或二维均值错误")
        if groups["treatment"] != {"n_trials": 3, "mean_uv": [[0, 3, 6], [0, 4, 8]]}:
            failures.append("treatment 的数量或二维均值错误")
        if summary["axes"] != {"times_s": [-0.1, 0.0, 0.1], "channel_names": ["Cz", "Pz"]}:
            failures.append("输出轴及通道次序错误")
        if summary["contrast"] != {"mean_difference_uv": [[0, 2, 4], [0, 2, 4]],
                                   "peak_uv": [4, 4], "peak_time_s": [0.1, 0.1]}:
            failures.append("处理减对照的逐通道差或峰值错误")
        probe = '''from analysis import analyze_epochs
epochs = [[[2, 4, 8]], [[10, 12, 18]], [[20, 24, 30]]]
summary, corrected = analyze_epochs(epochs, ["control", "treatment", "treatment"], [-1., 0., 1.], ["X"], [0, 1])
assert corrected == [[[-1., 1., 5.]], [[-1., 1., 7.]], [[-2., 2., 8.]]]
assert summary["groups"]["control"]["n_trials"] == 1
assert summary["groups"]["treatment"]["n_trials"] == 2
assert summary["contrast"]["mean_difference_uv"] == [[-0.5, 0.5, 2.5]]
assert summary["contrast"]["peak_uv"] == [2.5]
assert summary["contrast"]["peak_time_s"] == [1.]
assert epochs[0] == [[2, 4, 8]]
tie, _ = analyze_epochs([[[0, 4, 4]], [[0, 1, 7]]], ["control", "treatment"], [-0.1, 0., 0.1], ["X"], [0])
assert tie["contrast"]["peak_uv"] == [-3.]
assert tie["contrast"]["peak_time_s"] == [0.]
print("independent shape/baseline/nonmutation probe passed")
'''
        checked = subprocess.run([sys.executable, "-c", probe], cwd=workdir, capture_output=True,
                                 text=True, encoding="utf-8", timeout=30)
        evidence.update(summary=summary, independent_probe_returncode=checked.returncode,
                        independent_probe_output=checked.stdout + checked.stderr)
        if checked.returncode:
            failures.append("真实函数在不同形状、双点基线或不原地修改输入的独立探针上失败")
    except (OSError, KeyError, ValueError, TypeError) as error:
        failures.append(f"合成三维研究交付不完整：{error}")
    return {"pass": not failures, "failures": failures, "evidence": evidence}


def duplicate_raw_probe(workdir: Path) -> dict:
    """对明确修复任务复现外部 raw ID 重复反例，不重复扫描真实流水线内部数据。"""
    code = '''from pathlib import Path
import tempfile
from analysis import load_trials
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    raw = root / "raw.csv"
    labels = root / "conditions.csv"
    raw.write_text("trial_id,amplitude_uv\\na,1.0\\na,1.2\\nb,1.3\\n", encoding="utf-8")
    labels.write_text("trial_id,condition\\na,control\\nb,treatment\\n", encoding="utf-8")
    try:
        load_trials(raw, labels)
    except ValueError:
        print("duplicate raw IDs rejected at external entry")
    else:
        raise SystemExit("duplicate raw IDs incorrectly accepted")
'''
    checked = subprocess.run([sys.executable, "-c", code], cwd=workdir, capture_output=True,
                             text=True, encoding="utf-8", timeout=30)
    return {"pass": checked.returncode == 0, "returncode": checked.returncode,
            "output": checked.stdout + checked.stderr}
