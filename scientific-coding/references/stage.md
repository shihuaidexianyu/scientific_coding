# Stage Workflows

Contents: Stage Boundary · `CREATE_STAGE` · Scientific Function Contracts · Configuration and CLI · `CREATE_BRANCH` · `MODIFY_STAGE` · Testing

Read this reference for `CREATE_STAGE`, `MODIFY_STAGE`, or `CREATE_BRANCH`.

## Stage Boundary

A stage is one coherent scientific procedure that maps a declared input artifact and explicit TOML configuration to a declared output artifact:

```text
A(i+1) = S(i)(A(i), C(i))
```

Create an artifact boundary only when the output is worth independently reviewing, approving, reusing downstream, or retaining as a natural restart point. Do not split a method merely because the source file is long.

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
5. Decide whether this output deserves a new artifact and human-approval boundary.
6. Sketch a linear top-level narrative.
7. Implement the stage in one file by default.
8. Extract only functions named for genuine scientific concepts or clear I/O boundaries.
9. Produce artifact, runtime, and run-provenance metadata atomically.
10. Review the result for hidden transformations, hidden inputs, mutation, and semantic jumps.

A preferred top-level shape is:

```python
def main() -> None:
    config = load_config(...)
    input_artifact = load_approved_artifact(...)

    valid_trials, exclusions = remove_invalid_trials(input_artifact, config)
    aligned_trials = align_trials(valid_trials, config)
    features = compute_features(aligned_trials, config)

    write_artifact_atomically(features, exclusions, ...)
```

The exact functions should follow the method, not this example. Avoid opaque entry points such as `PipelineFactory.create(config).execute()`.

## Scientific Function Contracts

For each key scientific function, keep a nearby docstring that states:

- purpose;
- input semantics, shape, dtype, unit, coordinate frame, and time reference where applicable;
- ordered transformation;
- output semantics and shape;
- mutation and side effects.

Prefer scientific names such as `compute_hfb`, `align_trials`, or `run_permutation_test`. Keep execution helpers visibly separate. Avoid `utils.py`, `helpers.py`, `misc.py`, and `common.py` unless the code is genuinely stable infrastructure rather than study logic.

## Configuration and CLI

Put human-authored scientific parameters in a self-contained, flat-ish TOML file. Do not use inheritance, template chains, hidden overrides, or deep resolver behavior. Encode units in keys when practical, such as `window_ms`, `sampling_rate_hz`, and `timeout_s`.

A stage CLI should normally accept only a config path. Status and approval commands belong to a minimal orchestrator. Do not expose the study's parameter space as many CLI flags.

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

Report:

```text
Before
------
<scientific behavior>

After
-----
<scientific behavior>

Scientific semantic change
--------------------------
<what changed and why, or none>

Artifact contract change
------------------------
yes / no

Version bump required
---------------------
yes / no — <reason>
```

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

