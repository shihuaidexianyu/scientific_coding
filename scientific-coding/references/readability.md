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

Every defined function needs Chinese documentation available through the editor's hover at a call site. Use a real Python docstring as the first statement, JSDoc in JavaScript/TypeScript, or the equivalent supported by the language service. Plain comments above a function are not sufficient for this requirement. Keep explanatory headings, descriptions and sentences in Chinese; preserve real parameter and field identifiers.

Use separate, visibly spaced sections for purpose, parameters, processing logic, products/returns, and side effects. Give **each parameter** its own paragraph: name, content, concrete structure (dictionary keys, table columns, array axis order/shape, nested items), types/units, applicable defaults/path base and necessary assumptions. Give each member of a multi-value return its own paragraph with the same structural specificity; `dict`, `array`, or `tuple` alone is not a description. If an object is complex, show a compact schema/example and identify associated TOML paths/keys instead of copying the whole project contract. Explain logic as ordered steps. Say when there are no parameters, no return value, no direct file I/O, or no config dependency. Describe existing guarantees once, without adding runtime rechecks.

Make the hover text sufficient to understand this call without opening another function. For example, `counts` may be `dict[str, int]` with `control` and `treatment` keys, rather than an integer; `means_uv` may be the corresponding dictionary of microvolt floats, rather than a single float. Spell out that nesting. A reference to `summarize` or `load_trials` can explain origin, but cannot replace the current parameter/return schema. Describe group lengths separately when unequal lengths are allowed. A function that calls `Path.open()` uses the caller's working directory for relative paths unless it explicitly resolves another base; do not copy the orchestrator's path convention into a helper that does not implement it.

Begin each source file with a Chinese module/file overview. State its purpose, concrete input files and how to read them, output paths and structures, ordered processing, and the associated TOML files plus relevant sections/keys. Describe path resolution. A helper module should explain which files its callers provide; do not claim it has no I/O if its functions read or write files. Keep file-level context distinct from the function-specific contract and local operation comments. See [the annotated header template](../templates/stage_header.md).

## Enforce spacing with a script

The agent must write and execute a small formatter for the actual files and languages in the task. Do not rely on remembering this rule while generating text or on visual inspection alone. Cover source, helpers, views, and configuration in the requested scope, whether Python, TOML, R, Julia, MATLAB, shell, or another language; do not stop at `.py` files. A script may call an existing language-aware formatter when its configuration enforces the exact rule.

Identify real standalone comment blocks using the language's tokenizer/parser or a lexer appropriate to the syntax present. Python's `tokenize` distinguishes comments from strings. TOML multiline strings and other languages' string/block-comment syntax also need recognition; a global regex matching lines that start with `#` is insufficient. Preserve shebangs, encoding declarations, tool/compiler directives, comment contents, indentation, and multiline string contents. Keep lines inside one comment block together. Insert a blank before its start when needed, with no empty gap between the explanation and its code; omit a leading blank at file/cell start.

After the last code edit, obtain a clean formatter check over the final affected file list. If the check finds omissions, apply the formatter and check the repaired result; if it is already clean, do not require a no-op repair invocation. Parse/compile the affected languages where applicable to confirm that formatting preserved meaning. Keep this as one authoring-time operation, outside the scientific pipeline; temporary scripts need not become committed infrastructure or per-stage gates. If a file's syntax cannot be handled reliably, extend the task script or use its native tooling before claiming coverage. Formatting success does not establish that an operation is explained or its explanation is true.

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

Review the delivered code by following one sample and the major intermediate variables from input to output. Assess explanation accuracy and necessary checks directly; comment density, keyword matches, and raw check counts are not measures of understanding.
