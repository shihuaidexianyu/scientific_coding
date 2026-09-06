# Reading code and data

Use this reference when producing or changing pipeline code, TOML, or data descriptions.

## 表达式、行宽与循环职责

**不以节省输出 token、行数或字符数为代码优化目标。** 宁可完整写出
有含义的中间变量、顺序步骤和中文说明，也不把多步操作压成语法糖。
不得为缩短回答使用嵌套推导、lambda 套娃、海象运算隐藏赋值、长调用链、
短路副作用或密集解包。某种语法只有在当前语境更清楚、且满足下列规则时
才使用；不是禁止所有简洁写法，而是不允许用 token 成本替代可读性判断。
预算或上下文紧张时保存续接位置，按完整语义单元继续，不把剩余代码挤成
难读表达式，不省略规定的注释、变量或必要步骤，也不把未完工作宣称完成。

以下规则用于本次生成或修改的源码及配置。简化轮处理表达式和职责，
格式轮检查实际行宽，核验轮确认科学行为保持；不向运行流水线添加检查器。

1. **推导式最多一层。** 列表、集合、字典推导和生成器表达式均只允许
   一个 `for`，最多附一个简单筛选条件。出现第二个 `for`、多个筛选
   `if`、嵌套推导式或条件表达式时，拆成显式循环或有明确用途的辅助函数。
   换成多行推导式、`map`、`filter` 或 lambda 不能代替展开逻辑。
   显式代码可保留外层循环中的一个简单条件；再向内嵌套 `for`/`if`
   时，改成顺序步骤、提前 `continue`/`return` 或具名辅助函数。
   `elif` 是同一决策的并列分支，不算新增嵌套。
2. **每个物理行最多 80 个字符。** 包括缩进、代码、中文注释、docstring、
   字符流程图和 TOML；按去掉换行符后的 Unicode 字符计数，不按 UTF-8
   字节计数。使用空格缩进，不用 tab 规避限制。优先在括号、参数或运算
   边界拆行，给中间结果命名；说明文字也要分行。保持可读变量名。
   字符串只能按语言支持且值不变的方式拆分，不能截断路径、标识符，
   或给数据字符串插入换行。无法同时保持内容和行宽时明确说明冲突，
   不能默默豁免后声称全部满足。Markdown 叙述段落不属于源码行宽检查，
   其中作为正例的代码块仍遵守此限制。
3. **先命名，再传递。** 调用前先为筛选、映射、生成、聚合和复合构造
   的结果赋予有含义的名称。禁止将
   `r["contact"] for r in selected_contacts if ...`
   这类表达式直接作为参数，换行或改成列表推导也不例外。
   直接传已有变量、简单字面量和固定关键字选项即可，不为每个常量
   制造临时变量。提取生成器时保持原有惰性、消费次数、求值顺序和副作用，
   不擅自转成列表或额外遍历数据。
4. **短路条件保持简单。** `and`/`or` 只连接容易直接理解的简单条件。
   多级 fallback、嵌套三元表达式，以及 `a or b if c else d` 这样的
   混合选择，必须展开为 `if`/`elif`/`else`；仅拆成多行仍不合格。
   明确每个分支选择的数据来源，不把 `0`、空字符串或空列表自动解释为
   缺失。重构已有代码时保留原选择语义，改变缺失判定需要实际依据。
5. **一个循环只完成一项命名操作。** 收集对象、判定原因和构造输出是
   不同职责，应在顺序清楚的具名步骤中完成。循环中的简单筛选与收集
   可以共同完成“收集符合条件的 ID”；不要求每个循环只有一条语句。
   当整个循环只能概括为“处理所有东西”时，应拆分。辅助函数应命名
   实际操作，保留局部可理解性，不增加通用框架或逐层校验。

例如，已经校验过的 `selected_contacts` 是按输入顺序排列的记录列表，
每项含字符串 `contact` 和布尔值 `enabled`。下面只展示编排片段；
判因和输出构造函数应各自提供实际中文接口说明：

```python
# 收集启用的 contact ID，保留输入顺序，不重复验证已有字段保证。
contact_ids = []
for contact_record in selected_contacts:
    if not contact_record["enabled"]:
        continue
    contact_id = contact_record["contact"]
    contact_ids.append(contact_id)

# 根据既定分析规则判因，返回以 contact ID 为键的原因映射。
reasons_by_contact = determine_reasons(contact_ids, analysis_rules)

# 用已确定的 ID 和原因构造待保存记录，不在写入参数中隐藏筛选。
report_rows = build_report_rows(contact_ids, reasons_by_contact)

# 展开路径选择，保持先判断开关、再选择请求路径或备用路径的顺序。
if not use_requested_path:
    output_path = archive_path
elif requested_path:
    output_path = requested_path
else:
    output_path = fallback_path

# 保存已经具名的记录集合，具体写入由既有输出函数负责。
write_report(report_rows, output_path)
```

语义拆分可能增加遍历或中间内存。选择与数据规模相称的具名步骤，必要时
用只承担一项职责的惰性迭代函数保持流式消费；在成本说明中如实更新影响。
不要为追求单次遍历重新合并判因、统计和输出等不同职责。

最终检查同时覆盖行宽和结构：用任务脚本报告超过 80 字符的实际文件与行号，
用语法树或对应语言的结构化检查定位推导式层数、调用参数中的内联推导、
复杂条件选择及过深控制流；再阅读每个循环是否只承担一个职责。
不能仅凭“格式器成功”宣称语义检查完成。改写后核对结果、顺序、阈值边界、
惰性消费及输入不变性中实际受影响的部分；不重复无关检查。

## Local explanations

Cover semantic operations, not physical punctuation. Imports for one purpose, a multiline call, or a small loop implementing one operation can share a comment. Important branches, scientific parameters, axis changes, and sample changes need their own explanations. An entire long function headed only “process data” is not covered. A module overview never substitutes for explanations near the computation.

Write every explanatory comment in Chinese. Place one empty line before a comment block, no empty line between the block and its code, and keep the block's comment lines consecutive. At file/cell start omit the initial empty line; do not displace shebangs, encoding declarations, or required directives. Avoid inline explanatory comments. Inside bracketed expressions, put a blank line before a new explanatory comment as well.

The first explanatory comment inside a function has the same rule. In particular, leave a blank line between a closing docstring and the following `#` block. Do not invent a “first comment after docstring” exemption in the formatter. Docstrings are string statements, not adjacent `#` lines of that comment block.

```python
# signal 的轴依次为试次、通道、时间，数值单位为微伏。
# 保留长度为 1 的时间轴，使各试次、各通道的基线可以广播相减。
baseline_mean = signal[:, :, baseline_mask].mean(
    axis=2,
    keepdims=True,
)

# 从各试次、各通道的完整时间序列中减去对应基线。
# 数组形状、单位、样本身份及其顺序保持不变。
baseline_corrected_signal = signal - baseline_mean
```

The real file must explain how its baseline mask and time reference were established. Do not copy a methodological assumption from this illustration.

## 函数文档的固定版式

Every defined function needs Chinese documentation available through the editor's hover at a call site. Use a real Python docstring as the first statement, JSDoc in JavaScript/TypeScript, or the equivalent supported by the language service. Plain comments above a function are not sufficient. Keep headings and explanations in Chinese; preserve parameter and field identifiers.

Use the layout in [stage_header.md](../templates/stage_header.md): a short purpose followed by **参数 → 返回 → 处理过程 → 副作用**. In Python use the Chinese headings with underline separators shown in the template. Put the interface before the longer explanation of the algorithm so the hover is easier to scan.

- Each parameter starts with `name : type` on a line of its own. Indent the explanation by four more spaces on following lines. Leave a blank line before the next parameter; do not repeat `参数` on every entry.
- Each return member uses the same layout and its own paragraph, in actual return order. For a dictionary, list its fields separately with their types, nested keys and units. Do not compress multiple return members or fields into a semicolon-separated sentence.
- Put constraints about the whole object before its field list, or separate a following paragraph with a blank line. Otherwise Markdown hover can incorrectly attach that paragraph to the last field. Keep nested field indentation consistent with the actual structure.
- Number the processing steps on separate lines; keep side effects in their own final section. For no parameters or no returned value, state `无参数` or `None` briefly instead of inventing an item.
- Wrap source prose within the mandatory 80-character line limit above, including indentation. Preserve complete parameter/result explanations across lines and keep string values unchanged; do not shorten documentation to fit the hover window.
- Inspect real hover output at a call when the editor or language service is available. Check that indentation, sections and line breaks remain understandable. A source parse or `inspect.getdoc` proves the docstring is retrievable; it does not prove how the editor displays it. Do not discard required parameter/return/logic details just to fit everything into one hover screen.

Within this layout, explain concrete structure (dictionary keys, table columns, array axis order/shape, nested items), types/units, defaults/path bases and necessary assumptions. `dict`, `array`, or `tuple` alone is insufficient. For a complex object show a compact schema and identify associated TOML paths/keys, without copying the whole project contract. State absent file I/O or config dependency where applicable. Describe existing guarantees without adding runtime rechecks.

Make the hover text sufficient to understand this call without opening another function. For example, `counts` may be `dict[str, int]` with `control` and `treatment` keys, rather than an integer; `means_uv` may be the corresponding dictionary of microvolt floats, rather than a single float. Spell out that nesting. A reference to `summarize` or `load_trials` can explain origin, but cannot replace the current parameter/return schema. Describe group lengths separately when unequal lengths are allowed. A function that calls `Path.open()` uses the caller's working directory for relative paths unless it explicitly resolves another base; do not copy the orchestrator's path convention into a helper that does not implement it.

When review finds such a wrong path description, correct the description; do not add `ROOT / path` merely to make the mistaken prose true. Preserve intended existing behavior during documentation work. Change implementation only for a demonstrated bug or an authorized behavior change, and validate that specific change.

## 文件头与字符流程图

Begin each source file with a Chinese module/file overview. For Python, use an opening `"""` on its own line, then a short purpose on the next line. Place a text flow diagram near the top, before detailed input/output/config descriptions. Use simple characters such as `|`, `v`, `+-->` and `-->`, with readable Chinese node labels. Keep the closing quotes on their own line too; preserve a preceding shebang, encoding declaration or required tool directive.

The diagram shows **what this file actually does**: its input files or in-memory objects, ordered transformations, outputs, and where the associated TOML enters. A helper collection can show separate short branches for separate public operations; do not falsely connect independent functions into one execution sequence. If a module only transforms an in-memory object, name that input and returned object and explicitly state that it does not read/write files or load a TOML.

The file overview covers the entire file, including its `run` or `main`. If that function reads JSON/TOML or saves results, those are this file's operations. Use “调用方读取/保存” only when the operation actually belongs outside this file; do not copy that wording from a pure-function template into a module with its own I/O entry point.

Follow the diagram with the actual reading methods, fields/axes, units, output paths, config keys and path bases needed to understand the file. A diagram does not replace those descriptions. Keep it synchronized when inputs, outputs or processing change. Use [the annotated header template](../templates/stage_header.md) for the exact presentation pattern.

## 用任务脚本落实格式

为本次实际修改的语言编写并运行小型格式脚本。覆盖源码及相关配置，
识别真实注释块，用语言 tokenizer/parser 或适用词法扫描保护字符串、
多行字符串和必要指令；不能全局用井号正则替代词法识别。
修正块前空行、块后与代码的贴合关系，并检查最终源码每行不超过 80 字符。
复杂表达式与文字拆分由作者按语义处理，不机械改写字符串值。

用很小的语言对应反例验证脚本：缺失块前空行必须检出，连续注释不拆散，
字符串中的注释符号不改变；Python 还需覆盖 docstring 后缺空行，
因为 NEWLINE token 不证明实际存在空白行。行宽反例区分 80 和 81 字符。

最后一次编辑后检查最终文件。发现问题才修复并复查，已 clean 不要求
无变化再跑修复。用解析树/配置值及适用测试核对含义和字符串值保持。
临时脚本无需进入提交或运行流水线，格式通过也不能证明注释准确。

语义阅读另核对字面事实：两次列表推导是两次遍历；分组不保证组长相等；
增加 bootstrap 次数减少模拟误差，但不保证区间更窄；哈希不是数字签名。
错误说明应改成真实含义，不能通过添加检查或改变科学方法来凑齐注释。

## TOML

Describe each table and key immediately above it. Explain units, inclusive/exclusive endpoints, option meanings, path resolution, and the affected step as applicable. For scientific choices give the actual rationale when known; do not invent one. Small consecutive entries in an array may share a description if their meaning is identical. Strings containing `#` are data, not comments.

When improving a stage's readability, inspect its directly associated scientific TOML as part of the explanation pass even if no parameter value changes. Translate or complete its explanations too. Restrict this to the task's associated files, preserving values, existing configuration systems, and any content the user explicitly requires to remain untouched.

```toml
# 相对事件起点进行基线校正；这里仅示范配置说明格式。
[baseline]

# 基线窗口起点，单位毫秒；估计基线时包含该时刻。
start_ms = -200

# 基线窗口终点，单位毫秒；不包含该时刻，窗口为 [-200, 0)。
end_ms = 0
```

## Data descriptions

Keep one maintained description for each dataset/result and link to it from producers and consumers. Pipeline entry documentation inventories **all initial inputs**, including acquisition sources, annotation tables, masks, and experiment-design files. Place descriptions with stage artifacts (the annotated contract plus a short data guide is sufficient); a compact contract may contain the entire guide.

Record only applicable facts, explicitly marking unknowns and not-applicable fields:

| Field | Content |
|---|---|
| Inventory and origin | Files/objects, their roles, source/version, producer and consumers |
| Storage | Path base, format, encoding/compression, table/dataset names |
| Structure | Row meaning or array axis order, fields, types, units, missing-value conventions |
| Identity and alignment | IDs, join keys, ordering, coordinate/time reference, companion-file correspondence |
| Reading | A concrete reader call, object obtained in memory, relevant parsing/conversion, chunking or memory mapping when needed |
| Processing | Required assumptions/conversions, supported use, and actual pitfalls |
| Stage change | Added/removed/transformed information, exclusions or lineage mappings, downstream interpretation |

Include a small real schema or representative record when it helps reading. Distinguish declared variable dimensions from observed sizes; update run-specific counts from the produced data. For internal intermediates, explain local changes without making them formal artifacts.

## 检查与说明不能互相制造负担

运行检查的初稿禁入、事后必要性论证和已有保证复用统一见
[checks.md](checks.md)。写数据契约或解释函数假设，不意味着必须为每个字段
添加 assert；也不把声明的假设描述成已完成的验证。

沿一个样本和主要中间变量阅读代码，核对真实数据变化、说明和实际保留的检查。
注释数量、关键字匹配、原始检查数量不能证明可理解性或科学正确性。
