# Stage Workflows

Contents: Stage Boundary · `CREATE_STAGE` · Scientific Function Contracts · Configuration and CLI · `CREATE_BRANCH` · `MODIFY_STAGE` · Testing

Read this reference for `CREATE_STAGE`, `MODIFY_STAGE`, or `CREATE_BRANCH`.

## Stage Boundary

A stage is one coherent scientific procedure that maps named input datasets and explicit configuration to a declared output artifact:

```text
outputs = stage(named_inputs, effective_config)
```

Create an artifact boundary only when the output is worth independently reviewing, reusing downstream, or retaining as a natural restart point. Do not split a method merely because the source file is long.

Stage code may use stable reusable libraries, but it must not import another stage implementation. If two stages need the same value, carry it through an artifact contract or repeat a small transparent calculation when that better preserves auditability.

### Make the stage recognizable

The deterministic linter and human reviewers both need to recognize stage files. A file counts as a stage when any of these holds, in priority order:

1. it carries the marker comment `# scientific-code: stage` (strongest signal);
2. it lives under a `stage_roots` directory declared in the project's `scientific-code.toml`;
3. it lives in a `stages/` directory or uses a conventional stage file name (`preprocess_*`, `analysis_*`, `permutation_*`, …).

Follow at least one convention. Declare shared execution machinery under `infrastructure_roots` so it is not mistaken for study logic.

## `CREATE_STAGE`

Perform these decisions in order:

1. State the stage's single scientific purpose.
2. Identify the exact input artifact contract, including sample identity and scientific semantics.
3. Define the output artifact contract before implementation.
4. List the scientific transformations in execution order.
5. Decide which outputs deserve retention; add a human pause only if the user requested it.
6. Sketch a linear top-level narrative.
7. Implement the stage in one file by default.
8. Extract only functions named for genuine scientific concepts or clear I/O boundaries.
9. Publish the retained result and required provenance atomically; include runtime/profile metadata when useful.
10. Review local explanation coverage and remove redundant checks as described in [readability.md](readability.md).

A preferred top-level shape is:

```python
def main() -> None:
    """按顺序执行本阶段。

    参数
    ----
    无参数。配置路径和输入位置由项目入口确定。

    返回
    ----
    None
        不返回值；结果写入项目契约声明的位置。

    处理过程
    --------
    1. 读取输入、筛选有效试次并对齐。
    2. 计算特征，发布数据及来源记录。

    副作用
    ------
    读写阶段文件；实际生成时须替换为具体输入、输出和 TOML 路径，
    并在文件头用字符流程图展示对应关系。
    """

    # 在入口读取配置和外部数据，一次建立所需保证。
    config = load_config(...)
    input_artifact = load_input_artifact(...)

    # 保留有效试次，同时记录被排除样本的身份和原因。
    valid_trials, exclusions = remove_invalid_trials(input_artifact, config)

    # 将保留试次对齐到声明的时间和坐标参考。
    aligned_trials = align_trials(valid_trials, config)

    # 计算具有明确科学含义的特征，并说明其数组轴。
    features = compute_features(aligned_trials, config)

    # 将完整数据与来源记录发布到新的运行目录。
    write_artifact_atomically(features, exclusions, ...)
```

The exact functions should follow the method, not this example. Avoid opaque entry points such as `PipelineFactory.create(config).execute()`.

## Scientific Function Contracts

For every defined function, provide real Chinese hover documentation following [the fixed header template](../templates/stage_header.md): purpose, 参数, 返回, 处理过程, 副作用. Give each parameter/return a name-and-type line, indented explanation and separate paragraph; expand actual fields/axes, units, paths and assumptions locally. The Python file header opens with `"""` on its own line and includes a text diagram of real inputs, processing, outputs and associated TOML. Follow [readability.md](readability.md) for layout and hover verification.

Prefer scientific names such as `compute_hfb`, `align_trials`, or `run_permutation_test`. Keep execution helpers visibly separate. Avoid `utils.py`, `helpers.py`, `misc.py`, and `common.py` unless the code is genuinely stable infrastructure rather than study logic.

## Configuration and CLI

For new projects put scientific parameters in an annotated, self-contained TOML file. Preserve an existing configuration system unless migration is requested; capture the effective config and overrides. Explain every section/key with a preceding comment separated from prior code by a blank line. Encode units in keys when practical, such as `window_ms`, `sampling_rate_hz`, and `timeout_s`.

A stage CLI should normally accept only a config path. Status and approval commands belong to a minimal orchestrator. Respect a user-specified CLI while recording effective scientific choices; avoid adding a large CLI surface by default.

## `CREATE_BRANCH`

When a requested procedure differs materially from an existing one:

1. Compare the ordered scientific transformations, not just types or shapes.
2. Create a sibling stage file such as `preprocess_hfb.py` beside `preprocess_raw.py`.
3. Do not add `if config.mode == ...` to hide the scientific fork.
4. Do not introduce a base processor, factory, strategy, or registry merely to remove duplication.
5. Define the branch's output contract independently.
6. Rejoin downstream only after proving semantic equivalence of representation, units, coordinates, time origin, preprocessing, and sample meaning.

Duplicated orchestration or straightforward transformations are acceptable when they keep each method locally auditable. Extract shared code only when it names a stable, independently testable scientific concept and makes both branches easier to understand.

## `MODIFY_STAGE`

Before editing, establish the current behavior from code, config, contract, and tests. Explicitly decide whether the change affects:

- mathematical or statistical procedure;
- preprocessing meaning or defaults;
- sample inclusion or ordering;
- representation, units, coordinates, or time origin;
- randomness, split, fold, permutation, or mapping;
- input or output contract.

If it affects artifact semantics, version the contract rather than silently mutating it. Keep unrelated refactoring out of the patch so the scientific change remains reviewable.

Report the resulting behavior, material scientific changes, contract/version implications, and validation in concise prose. Omit fields that do not apply; no fixed review form is required.

## Testing

Prefer tests that guard scientific meaning:

- train/test subjects do not overlap;
- sample IDs remain aligned through transformations;
- probability or conservation invariants hold;
- coordinate transforms remain valid;
- an optimized implementation agrees with a readable reference;
- artifact contract validation catches semantic incompatibility;
- metamorphic properties hold when no direct oracle exists.

Avoid tests such as “not `None`,” “length greater than zero,” or trivial type checks unless they encode a real historical failure mode.

