# Reading code and data

Use this reference when producing or changing pipeline code, TOML, or data descriptions.

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
- Wrap prose in the source at a comfortable display width, aiming around 88 columns including indentation (Chinese characters usually occupy two columns). Do not split identifiers, paths or formulas to satisfy a hard character count. The goal is readable source and hover, not a numeric width gate.
- Inspect real hover output at a call when the editor or language service is available. Check that indentation, sections and line breaks remain understandable. A source parse or `inspect.getdoc` proves the docstring is retrievable; it does not prove how the editor displays it. Do not discard required parameter/return/logic details just to fit everything into one hover screen.

Within this layout, explain concrete structure (dictionary keys, table columns, array axis order/shape, nested items), types/units, defaults/path bases and necessary assumptions. `dict`, `array`, or `tuple` alone is insufficient. For a complex object show a compact schema and identify associated TOML paths/keys, without copying the whole project contract. State absent file I/O or config dependency where applicable. Describe existing guarantees without adding runtime rechecks.

Make the hover text sufficient to understand this call without opening another function. For example, `counts` may be `dict[str, int]` with `control` and `treatment` keys, rather than an integer; `means_uv` may be the corresponding dictionary of microvolt floats, rather than a single float. Spell out that nesting. A reference to `summarize` or `load_trials` can explain origin, but cannot replace the current parameter/return schema. Describe group lengths separately when unequal lengths are allowed. A function that calls `Path.open()` uses the caller's working directory for relative paths unless it explicitly resolves another base; do not copy the orchestrator's path convention into a helper that does not implement it.

## 文件头与字符流程图

Begin each source file with a Chinese module/file overview. For Python, use an opening `"""` on its own line, then a short purpose on the next line. Place a text flow diagram near the top, before detailed input/output/config descriptions. Use simple characters such as `|`, `v`, `+-->` and `-->`, with readable Chinese node labels. Keep the closing quotes on their own line too; preserve a preceding shebang, encoding declaration or required tool directive.

The diagram shows **what this file actually does**: its input files or in-memory objects, ordered transformations, outputs, and where the associated TOML enters. A helper collection can show separate short branches for separate public operations; do not falsely connect independent functions into one execution sequence. If a module only transforms an in-memory object, name that input and returned object and explicitly state that it does not read/write files or load a TOML.

The file overview covers the entire file, including its `run` or `main`. If that function reads JSON/TOML or saves results, those are this file's operations. Use “调用方读取/保存” only when the operation actually belongs outside this file; do not copy that wording from a pure-function template into a module with its own I/O entry point.

Follow the diagram with the actual reading methods, fields/axes, units, output paths, config keys and path bases needed to understand the file. A diagram does not replace those descriptions. Keep it synchronized when inputs, outputs or processing change. Use [the annotated header template](../templates/stage_header.md) for the exact presentation pattern.

## Enforce spacing with a script

The agent must write and execute a small formatter for the actual files and languages in the task. Do not rely on remembering this rule while generating text or on visual inspection alone. Cover source, helpers, views, and configuration in the requested scope, whether Python, TOML, R, Julia, MATLAB, shell, or another language; do not stop at `.py` files. A script may call an existing language-aware formatter when its configuration enforces the exact rule.

Identify real standalone comment blocks using the language's tokenizer/parser or a lexer appropriate to the syntax present. Python's `tokenize` distinguishes comments from strings. TOML multiline strings and other languages' string/block-comment syntax also need recognition; a global regex matching lines that start with `#` is insufficient. Preserve shebangs, encoding declarations, tool/compiler directives, comment contents, indentation, and multiline string contents. Keep lines inside one comment block together. Insert a blank before its start when needed, with no empty gap between the explanation and its code; omit a leading blank at file/cell start.

After the last code edit, obtain a clean formatter check over the final affected file list. If the check finds omissions, apply the formatter and check the repaired result; if it is already clean, do not require a no-op repair invocation. Parse/compile the affected languages where applicable to confirm that formatting preserved meaning. Keep this as one authoring-time operation, outside the scientific pipeline; temporary scripts need not become committed infrastructure or per-stage gates. If a file's syntax cannot be handled reliably, extend the task script or use its native tooling before claiming coverage. Formatting success does not establish that an operation is explained or its explanation is true.

Verify the task formatter on tiny examples of the actual languages it handles: it must detect/repair a missing physical blank line before a new comment block, keep consecutive comment lines together, and preserve comment-like text inside strings. For Python, include a missing blank after a docstring: a `NEWLINE` token ends a statement and does not prove an empty source line exists. Use the corresponding comment/string syntax for TOML or other languages in scope; no unrelated language tests are needed. This short authoring-time self-check tests the formatter, not the scientific pipeline; a script that reports clean while missing the deliberate defect is not sufficient evidence.

Read the resulting files for semantic accuracy. For example, more bootstrap replicates reduce Monte Carlo error but do not guarantee a narrower confidence interval; a hash is not a digital signature; an aggregation weight table needs its source values to reconstruct a mean and does not reconstruct a bootstrap interval by itself. Attribute guarantees to the operation that actually establishes them, not a later filter that merely preserves them.

Check implementation claims literally: two list comprehensions are two traversals, even if they partition the same input; grouping does not make the groups equal in length. Prefer a concise true explanation of the scientific operation to invented efficiency claims.

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

## Checks without clutter

A validated config's required keys and numeric types do not need checking inside every scientific function. A known reshape does not need an assertion restating its construction. Removing rows can threaten group availability, but does not invalidate the types already established. Joining tables may threaten key uniqueness, so verify the intended cardinality at the join rather than repeating every input check.

External reads and changed objects can invalidate guarantees; routine function boundaries cannot. Ordinary missing-file/key errors usually need no existence preflight. Keep a check when it catches a new scientific failure, prevents costly partial work, or provides actionable diagnosis that the normal error lacks. Do not replace deleted checks with repetitive reassurance comments.

Simplify individual facts, not whole `if` statements: a combined condition may protect several different facts. At a two-table join, matching ID sets does not prove either table's IDs are unique, and uniqueness in the label table does not prove uniqueness in the measurement table. Preserve every necessary guarantee; remove a condition only when retained code or an applicable parser/API guarantee already establishes its fact, whether at the boundary or downstream. When removing a boundary-related condition, use a small counterexample for the fact that must remain protected.

Review the delivered code by following one sample and the major intermediate variables from input to output. Assess explanation accuracy and necessary checks directly; comment density, keyword matches, and raw check counts are not measures of understanding.
