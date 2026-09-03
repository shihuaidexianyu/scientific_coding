# Resumability and Long-Running Work

Read this reference for `ADD_RESUMABILITY`.

## First Decision

Estimate expected restart loss before writing checkpoint code. Consider stage runtime, observed or credible failure probability, queue delay, scarce-resource cost, and the amount of human research time lost. A stage artifact is already a natural checkpoint between stages.

Use this heuristic as context, not a hard threshold:

| Single-stage runtime | Default decision |
|---|---|
| under 1 hour | do not add intra-stage checkpointing |
| 1–6 hours | usually do not add it |
| 6–24 hours | decide from stability and rerun loss |
| over 24 hours | strongly consider resumability |
| multi-day with intermittent nodes | normally add it |

A request to checkpoint a 20-minute stable stage should normally be declined with the restart-cost rationale.

## Workflow

1. Quantify expected restart loss.
2. Use the existing stage artifact boundary if it is sufficient.
3. If not, divide work into independently reproducible, idempotent units.
4. Write each unit atomically with its identity, config/input hashes, seed, and completion metadata.
5. On resume, validate completed units and run only missing or invalid ones.
6. Keep discovery, scheduling, retry, and resume logic outside the scientific function.
7. Aggregate deterministically and record shard ordering/reduction behavior.
8. Verify uninterrupted and interrupted-plus-resumed equivalence.

## Prefer Idempotent Shards

For example, split 10,000 permutations into 100 deterministic shards of 100 permutations. Each shard writes a complete artifact such as `shard_000.parquet`. Resume by validating completed shard hashes, skipping them, and recomputing missing shards.

Prefer this to serializing arbitrary Python stack, iterator, queue, or process state. A shard should be safe to rerun and replace before approval.

Keep the scientific unit simple:

```python
def run_one_permutation(permutation_spec, data):
    ...
```

The function should not know whether the overall run is fresh or resumed.

## Correctness

Verify:

```text
uninterrupted run approximately equals interrupted + resumed run
```

Audit RNG seed derivation, optimizer and scheduler state, work ordering, accumulators, reduction order, and floating-point differences. If splits or permutations define the experiment, materialize their identities so resumption cannot silently draw a different design.

For training that genuinely requires internal state, keep checkpoint save/load at the training execution boundary and record model, optimizer, scheduler, RNG, step/epoch, data-order, config, input, code, and framework/hardware provenance. Do not scatter checkpoint conditions through model or loss code.

## Acceptance

Resumability is complete only when stale or incompatible shards are rejected, partial writes cannot masquerade as complete, scientific functions remain independent of resume state, and an interruption test demonstrates equivalence.

