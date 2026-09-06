# Scientific Pipeline Optimization

Read only for an actual performance optimization task. Ordinary delivery estimates use [estimation.md](estimation.md).

## Objective

Optimize **time to scientific answer**, not kernel benchmark score, CPU/GPU utilization, minimum RAM, or minimum lines of code. Preserve scientific meaning and auditability ahead of speed.

Use representative profiling before adding performance complexity. If the target environment is unavailable, use existing measurements or a credible reduced workload and label its limits; do not fabricate a hotspot or speedup. Respect an explicitly requested prototype while distinguishing it from a measured improvement.

## Required Workflow

1. Define a representative end-to-end workload and correctness criteria.
2. Measure reference wall time, CPU time, peak RAM/VRAM when relevant, and key substep times.
3. Profile and identify the dominant bottleneck.
4. Estimate the maximum useful end-to-end speedup before adding complexity.
5. Decide whether the likely gain changes research iteration meaningfully.
6. If not, stop and report `DO NOT OPTIMIZE` with the measurements and bound.
7. Try transparent library/compiler optimization first.
8. Change only the measured hotspot.
9. Preserve a readable reference implementation when the fast path adds cognitive complexity.
10. Verify numerical and scientific equivalence on representative and edge cases.
11. Re-measure the same end-to-end workload.
12. Record peak memory and relevant hardware/environment details.
13. Report actual pipeline speedup and accept or reject the optimization based on material research value.

Never edit first and benchmark later.

When the decision at step 5–6 is to optimize, carry it through: an implemented change and the step 11 end-to-end re-measurement are part of the task. Stopping at a methodology description is an unfinished task, not a conservative one.

## Research Latency

Consider total repeated-run cost as well as single-run latency. A five-minute saving repeated hundreds of times can justify a transparent change. Prefer changes that cross a human-feedback boundary:

| Runtime | Research cadence |
|---|---|
| under 15 minutes | short feedback |
| 15 minutes–2 hours | same session |
| 2–12 hours | same day |
| 12–24 hours | overnight |
| 1–3 days | multi-day |
| over 3 days | research-blocking |

A reduction from three days to seven hours is generally much more valuable than ten minutes to five minutes, even when the relative speedups look similar. Treat these as decision aids, not rigid thresholds.

## Optimization Levels

Use the lowest level that produces a meaningful end-to-end gain.

### Level 0 — No optimization

This is the default when evidence or expected research value is insufficient.

### Level 1 — Transparent

Prefer optimized NumPy/SciPy and BLAS/LAPACK, library-provided kernels, `torch.compile`, Numba, or JAX JIT when the scientific source remains directly readable.

### Level 2 — Mechanical

After profiling, consider batching, vectorization, preallocation, chunking, avoiding copies, memory-layout changes, or a parallel map. Apply these only to the demonstrated hotspot.

### Level 3 — Specialized

Use C++, CUDA, Triton, distributed execution, or specialized kernels only after lower levels are inadequate and the expected pipeline gain earns their maintenance and audit cost. Keep a readable reference implementation.

## End-to-End Evidence

Compute:

```text
pipeline_speedup = reference_end_to_end_s / optimized_end_to_end_s
```

Report the same workload, data, config, seed, environment, and correctness criteria before and after. A local kernel speedup is diagnostic evidence, not the result.

Use [the optimization report template](../templates/optimization_report.json) to record evidence.

## Parallelism

Estimate the upper bound using Amdahl's law before adding workers:

```text
S(N) = 1 / ((1 - p) + p / N)
```

If only 20% is parallelizable, even infinitely many workers cannot exceed 1.25x end-to-end speedup. Reject locks, queues, shared memory, process managers, or worker lifecycle complexity that cannot earn a meaningful pipeline gain.

When the bound rules out the requested mechanism, decline the mechanism and deliver the bottleneck fix or a `DO NOT OPTIMIZE` verdict instead. Analysis that concludes "this cannot pay" and then implements it anyway is a failure: the estimate exists to decide, not to decorate. Explain the measured limit. If the user explicitly values another outcome or requests a prototype despite it, respect that scope and report the tradeoff without claiming unsupported speedup.

Keep scientific computation independent of execution machinery:

```python
def run_one_permutation(...):
    ...

results = parallel_map(run_one_permutation, work_units)
```

Queues, locks, scheduling, and shared state belong at the execution boundary, not inside the mathematical procedure.

## Memory and I/O

Default to **time first, memory feasible**. Do not minimize memory if peak use stays below available RAM/VRAM with a reasonable safety margin.

If profiling shows repeated I/O dominates, prioritize loading once into RAM, memory mapping, a documented local SSD cache, batched reads, or one-time decompression/deserialization. Do not optimize the mathematical kernel while 70% of runtime is data loading.

Optimize memory only when it is a feasibility constraint or when memory behavior causes the measured runtime bottleneck. Record the resulting peak.

## Scientific Equivalence

Execution changes such as interpreted-to-compiled, serial-to-parallel, or repeated-I/O-to-preload are optimizations only while the mathematical meaning stays fixed. Define tolerances from the method and numerical behavior, not convenience:

```text
fast(x) approximately equals reference(x)
```

Changing an exact method to an approximation is a new scientific method or branch, not an ordinary optimization. Route it through `CREATE_BRANCH` and contract review.

## Acceptance

Reject or revert an optimization when its measured end-to-end benefit is not material relative to the added cognitive complexity, unless the user explicitly values another measured constraint. Do not delete the reference implementation merely because a fast version exists.

