# Stage Workflows

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

## Create a stage

Identify the scientific purpose, actual inputs, output meaning and ordered
transformations. A contract can be an adequate existing data description;
do not require a new manifest/schema framework before writing the method.

Write the complete original logical path first, without assertions, defensive
preflights, automatic repair or review gates. Method-defined filtering remains
part of the algorithm. Then simplify, consider only justified checks under
[checks.md](checks.md), and add the required outer execution record before
running the delivered program. Retain outputs at a boundary when useful;
do not turn every intermediate into a persisted artifact.

Keep a transparent sequence such as reading inputs, selecting trials, aligning
them, computing features and writing results. Choose actual operations for the
study instead of copying placeholder stages. Helpers should name a scientific
operation or clear I/O boundary; avoid generic processors, factories and utils.

Source/header/function/TOML layout is maintained in
[readability.md](readability.md) and [stage_header.md](../templates/stage_header.md).
Use those rules rather than a second stage-specific documentation format.

## Configuration and CLI

For new projects put scientific parameters in an annotated, self-contained TOML file. Preserve an existing configuration system unless migration is requested; capture the effective config and overrides. Explain every section/key with a preceding comment separated from prior code by a blank line. Encode units in keys when practical, such as `window_ms`, `sampling_rate_hz`, and `timeout_s`.

A scientific stage CLI should normally accept a config path. Add operational status commands only when needed; add approval controls only for a user-selected pause. Respect a user-specified CLI while recording effective scientific choices; avoid adding a large CLI surface by default.

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

