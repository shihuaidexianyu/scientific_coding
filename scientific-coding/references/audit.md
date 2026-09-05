# Scientific Pipeline Audit

Contents: Audit Objective · Audit Procedure · Audit Checklist · Deterministic Linter · Scientific Diff · Definition of Done

Read this reference for `AUDIT_STAGE`, completion review, or checking the boundary around `INFRASTRUCTURE` work.

## Audit Objective

Audit the cognitive and semantic path from intended method to source to execution. This is not a conventional style or refactoring review. Do not recommend abstractions, file splitting, generic utilities, performance work, or checkpointing without scientific or measured operational justification.

## Audit Procedure

1. State the scientific purpose and reconstruct the top-level transformation sequence.
2. Identify declared inputs, effective config, code revision, and output contract.
3. Trace stable sample IDs and every change in sample membership.
4. Check stage boundaries and reject stage-to-stage Python imports.
5. Compare scientific branches and look for method differences hidden behind config conditionals.
6. Look for hidden transformations in helpers, views, callbacks, mutation, caches, and fallbacks.
7. Look for hidden inputs from environment, home directories, `latest/`, time, network, or undocumented global files.
8. Locate where representation, units, coordinates, time, sample semantics, and joins are established; check only facts that are new or may have become invalid.
9. Check complete publication, fresh run paths, and necessary integrity verification; human review is required only at user-selected points.
10. Remove each defensive check whose error is already excluded and cannot have been reintroduced. Check that no helper or loop repeats a gate.
11. Check that optimization has representative before/after end-to-end evidence and reference equivalence.
12. Check that resumability has restart-loss justification and resume equivalence.
13. Check result provenance and the documented analysis/rendering boundary, including any explicitly requested combined-file layout.
14. Run the agent-written comment formatter/check over the task's source and configuration languages after editing; verify syntax/meaning is preserved. Run relevant scientific tests and other deterministic checks.

Report findings by scientific risk and evidence. Distinguish a proven violation from a heuristic concern or missing evidence.

## Audit Checklist

- Scientific purpose is explicit.
- Input and output contracts are explicit and semantically complete.
- Code is a readable linear narrative with accurate comments beside every semantic operation. Comment blocks have a blank line before them and touch their code. Every TOML section/key is explained.
- Initial and stage-result data have a concrete structure/meaning/reading guide; in-memory changes are explained inline.
- File overviews have a truthful text flow diagram and an opening quote line of their own. Function hover documentation follows purpose, 参数, 返回, 处理过程, 副作用; names/types occupy separate lines, explanations are indented, items are spaced, nested fields are expanded, and long prose is wrapped. Verify actual language-service hover when available and state when only source/docstring checks were possible.
- No scientific transformation is hidden in infrastructure or plotting.
- No undeclared input affects scientific behavior.
- Mutation does not obscure lineage.
- Materially different procedures use separate stage implementations.
- Abstractions name scientific concepts rather than engineering patterns.
- Each retained check protects a still-unexcluded failure at its owning boundary; guarantees are reused while valid.
- New configuration is annotated TOML; existing formats are preserved with explicit effective values.
- Stable sample identities and exclusion reasons remain traceable.
- Published results are preserved in fresh runs and traceable; optional review decisions bind the exact result.
- Randomness and experiment-design artifacts are reproducible.
- Performance and checkpoint complexity have measured justification.

## Deterministic Linter

Run:

```bash
python <skill-dir>/scripts/scientific_code_lint.py <project-root> --changed-only
```

Use `--base-ref origin/main` in CI to diff against the merge base (a clean PR checkout has no working-tree changes, so plain `--changed-only` would check nothing). Use `--strict-warnings` in CI once existing warnings have been triaged. Use `--format json` for machine-readable output. Static AST checks cannot prove semantic correctness; combine them with contract and scientific-invariant tests.

Which files count as stages or views is decided by, in order: an in-file marker (`# scientific-code: stage` / `view`), the project's `scientific-code.toml` scope roots (see [the template](../templates/scientific-code.toml)), then naming conventions (`stages/` directories, common stage/view file stems). Infrastructure roots declared in the config are exempt from the naming-discipline heuristics. Declare the scope explicitly whenever the project layout does not match the conventions. When the lint root has no `scientific-code.toml` — or one with an empty `[scope]` — the nearest nested project config is used instead (monorepo layout), and its roots apply relative to that project's directory, not to the lint root.

Artifact integrity checks run in two modes. The default metadata mode validates schema, paths, derived hashes, and approval binding without reading payload content, so lint stays cheap on large data. `--full-artifact-checks` additionally re-hashes finalized artifact payloads and recorded input artifact payloads; use it for release verification or scheduled integrity audits, not on every lint run.

Hard errors:

| Code | Meaning |
|---|---|
| `SC000` | source or project configuration cannot be read or parsed, so checks cannot run reliably |
| `SC001` | stage imports another stage implementation, directly or through a chain of local modules |
| `SC003` | finalized artifact hashes or an optional approval binding disagree |
| `SC004` | an artifact candidate is missing or has an unreadable manifest |
| `SC005` | a recorded input is invalid/hash-incompatible or fails an explicitly requested review point; in `--full-artifact-checks` mode also fires when the input payload no longer matches its manifest |
| `SC006` | a view imports a scientific stage implementation, directly or transitively |
| `SC007` | tracked artifact content differs from its finalized manifest (payload comparison requires `--full-artifact-checks`) |
| `SC008` | a formal non-acquisition stage performs a known network call |

CLI structure is an engineering choice, so `SC002` is advisory even when scientific parameter names are detected. A user-selected CLI must still record effective scientific choices.

Heuristic warnings:

| Code | Meaning |
|---|---|
| `SC002` | scientific parameter CLI or more than two operational arguments; prefer explicit configuration unless the project/user chose this interface |
| `SC101` | scientific branch may be hidden behind config `if/else` |
| `SC102` | factory/registry/manager-style abstraction appeared in pipeline scope |
| `SC103` | generic `utils.py`/`helpers.py`-style module appeared in pipeline scope |
| `SC104` | checkpoint or resume machinery appeared |
| `SC105` | optimized/specialized implementation lacks a valid optimization report (missing, placeholder text, or `pipeline_speedup` inconsistent with the recorded end-to-end times) |
| `SC106` | broad exception fallback may hide failure |
| `SC107` | a scientific function may mutate an input parameter |
| `SC108` | a likely scientific function lacks a semantic contract docstring (NumPy, Google, Sphinx, and Chinese conventions are accepted; a module overview does not waive scientific function contracts) |
| `SC109` | a view appears to perform scientific computation (bootstrap, outlier removal, percentile/interval statistics, normalization, fitting); comments, docstrings, and labels are masked, executable identifiers are heuristic evidence, not proof of a calculation |

`SC102`/`SC103` apply only inside pipeline scope (stage/view files); infrastructure code keeps its own conventions, per the scope gate.

A warning may be suppressed at file scope only with a concrete justification:

```python
# scientific-code: allow SC104 -- 任务在可抢占节点运行四天，已核验确定性分片
```

Only warnings can be suppressed, including SC002; hard errors cannot be suppressed. Use a directive when the flagged construct is deliberate and the reason would help a reviewer. Do not override an authorized engineering choice just to silence a style warning.

## Scientific Diff

Report material changes to the method, input/output semantics, sample inclusion or mapping, randomness, artifact version, and runtime. Include before/after behavior and the relevant validation. Use concise prose for the facts that apply; do not require a form of repeated yes/no gates.

## Definition of Done

A task is complete only when scientific behavior and contracts are explicit, the stage boundary remains coherent, no unnecessary abstraction or hidden input/transformation was introduced, config and lineage remain readable, semantic changes are reported, optimization/resume complexity has evidence, and relevant deterministic checks pass.
