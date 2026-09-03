# Scientific Pipeline Audit

Read this reference for `AUDIT_STAGE`, completion review, or checking the boundary around `INFRASTRUCTURE` work.

## Audit Objective

Audit the cognitive and semantic path from intended method to source to execution. This is not a conventional style or refactoring review. Do not recommend abstractions, file splitting, generic utilities, performance work, or checkpointing without scientific or measured operational justification.

## Audit Procedure

1. State the scientific purpose and reconstruct the top-level transformation sequence.
2. Identify declared inputs, TOML config, code revision, and output contract.
3. Trace stable sample IDs and every change in sample membership.
4. Check stage boundaries and reject stage-to-stage Python imports.
5. Compare scientific branches and look for method differences hidden behind config conditionals.
6. Look for hidden transformations in helpers, views, callbacks, mutation, caches, and fallbacks.
7. Look for hidden inputs from environment, home directories, `latest/`, time, network, or undocumented global files.
8. Verify representation, units, coordinates, time origin, preprocessing, and sample semantics at every artifact boundary.
9. Verify produced/approved/frozen states, content hashes, atomic output, and invalidation behavior.
10. Review abstractions and defensive checks for concrete scientific value.
11. Check that optimization has representative before/after end-to-end evidence and reference equivalence.
12. Check that resumability has restart-loss justification and resume equivalence.
13. Check that figures consume approved artifacts and contain presentation transformations only.
14. Run deterministic checks and relevant scientific tests.

Report findings by scientific risk and evidence. Distinguish a proven violation from a heuristic concern or missing evidence.

## Audit Checklist

- Scientific purpose is explicit.
- Input and output contracts are explicit and semantically complete.
- Top-level code is a readable linear narrative.
- No scientific transformation is hidden in infrastructure or plotting.
- No undeclared input affects scientific behavior.
- Mutation does not obscure lineage.
- Materially different procedures use separate stage implementations.
- Abstractions name scientific concepts rather than engineering patterns.
- Defensive checks protect a trust boundary, scientific invariant, or provenance.
- Human-authored config is readable TOML without inheritance or hidden overrides.
- Stable sample identities and exclusion reasons remain traceable.
- Approved artifacts are immutable and hash-bound.
- Randomness and experiment-design artifacts are reproducible.
- Performance and checkpoint complexity have measured justification.

## Deterministic Linter

Run:

```bash
python <skill-dir>/scripts/scientific_code_lint.py <project-root> --changed-only
```

Use `--strict-warnings` in CI once existing warnings have been triaged. Use `--format json` for machine-readable output. Static AST checks cannot prove semantic correctness; combine them with contract and scientific-invariant tests.

Hard errors:

| Code | Meaning |
|---|---|
| `SC000` | a Python source file cannot be read or parsed, so checks cannot run reliably |
| `SC001` | stage imports another stage implementation |
| `SC002` | stage exposes a large scientific CLI surface |
| `SC003` | approved artifact hash does not match its manifest/content |
| `SC004` | an artifact candidate is missing or has an unreadable manifest |
| `SC005` | a recorded input artifact is not approved or hash-compatible |
| `SC006` | a view imports a scientific stage implementation |
| `SC007` | tracked artifact content changed after approval |
| `SC008` | a formal non-acquisition stage performs a known network call |

Heuristic warnings:

| Code | Meaning |
|---|---|
| `SC101` | scientific branch may be hidden behind config `if/else` |
| `SC102` | factory/registry/manager-style abstraction appeared |
| `SC103` | generic `utils.py`/`helpers.py`-style module appeared |
| `SC104` | checkpoint or resume machinery appeared |
| `SC105` | optimized/specialized implementation lacks an optimization report |
| `SC106` | broad exception fallback may hide failure |
| `SC107` | a scientific function may mutate an input parameter |
| `SC108` | a likely scientific function lacks a semantic contract docstring |

A warning may be suppressed at file scope only with a concrete justification:

```python
# scientific-code: allow SC104 -- 4-day job on preemptible nodes; deterministic shards verified
```

Do not suppress hard errors. Prefer fixing a warning; use a directive only when the flagged construct is deliberate and the justification would help a reviewer.

## Scientific Diff

For any modification that could affect scientific behavior, report:

```text
Scientific behavior changed: yes / no
Input semantics changed: yes / no
Output semantics changed: yes / no
Sample inclusion changed: yes / no
Randomness changed: yes / no
Artifact version changed: yes / no
Runtime materially changed: yes / no
```

Support each `yes` and any non-obvious `no` with evidence. For stage modification, also give before/after behavior and the contract-version rationale.

## Definition of Done

A task is complete only when scientific behavior and contracts are explicit, the stage boundary remains coherent, no unnecessary abstraction or hidden input/transformation was introduced, config and lineage remain readable, semantic changes are reported, optimization/resume complexity has evidence, and relevant deterministic checks pass.
