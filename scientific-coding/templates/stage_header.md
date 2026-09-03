# Scientific stage header

Adapt this example to the actual method. Keep the main narrative in execution order and replace every example semantic with the study's real contract.

```python
# scientific-code: stage
"""Produce ExampleOutputV1 from approved ExampleInputV1.

Scientific purpose
------------------
State the single question or transformation this stage implements.

Input artifact
--------------
ExampleInputV1: state representation, dimensions, dtype, units, coordinate/time
reference, sample identity, and required approval state.

Configuration
-------------
configs/example_stage.toml: list parameters that alter scientific behavior and
their units.

Ordered transformations
-----------------------
1. State the first scientific operation.
2. State each subsequent operation in execution order.

Output artifact
---------------
ExampleOutputV1: state representation, dimensions, dtype, units, coordinate/time
reference, sample identity, and exclusion-ledger behavior.

Randomness
----------
None, or state seed semantics and deterministic-mode expectations.
"""


def main() -> None:
    config = load_config_from_toml(...)
    input_artifact = load_approved_input(...)

    transformed_data, exclusions = apply_named_scientific_step(
        input_artifact,
        config,
    )

    write_complete_artifact_atomically(
        transformed_data,
        exclusions,
        config,
        input_artifact,
    )


if __name__ == "__main__":
    main()
```

