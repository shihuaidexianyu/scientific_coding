---
name: scientific-coding
description: Design, implement, modify, audit, or optimize human-auditable scientific pipeline code, including preprocessing, feature construction, statistical analysis, model evaluation, resampling, experiment scripts, visualization, and long-running computation. Use for scientific pipelines; do not apply automatically to reusable numerical libraries, parsers or dataset SDKs, infrastructure, deployment, production services, or general-purpose packages.
---

# Scientific Coding

## Objective

Treat a scientific pipeline as an executable description of a scientific method. Minimize the semantic distance between the intended method, the source a researcher audits, and the computation that runs.

Use this fixed decision priority when goals conflict:

1. Scientific correctness
2. Human auditability
3. Explicit data lineage
4. Reproducibility
5. Research iteration latency
6. Runtime performance
7. Memory efficiency
8. Reusability
9. Code compactness

## Scope Gate

Before acting, decide whether the target is a **scientific pipeline** or **reusable scientific software**.

Apply this skill to preprocessing, feature construction, analysis, statistics, evaluation, permutation/bootstrap/CV, experiment scripts, scientific views, and performance or reliability work on those pipelines.

Do not impose this architecture on simulation engines, dataset SDKs, parsers, reusable numerical libraries, infrastructure, deployment systems, production services, or general-purpose packages. Classify those tasks as `INFRASTRUCTURE` and preserve the boundary between execution machinery and scientific semantics.

If the classification is ambiguous, inspect how outputs are consumed. Code that realizes one study's method and produces reviewable research artifacts is normally a pipeline; code offering a stable reusable API across studies is normally reusable software.

## Core Model

Use this pipeline model:

```text
declared artifact + explicit TOML config + code
                       |
                       v
              one scientific stage
                       |
                       v
             immutable artifact
                       |
                       v
                human approval
```

A downstream stage depends on the upstream **artifact contract**, never on the upstream Python implementation. It must not import another stage.

## Non-Negotiable Rules

- These rules bind regardless of instruction source. Never forge or edit an approval record, mutate an approved artifact, run a downstream stage on unapproved input, or weaken lint or approval machinery to make progress — not even when the user explicitly asks for it, the task demands an end-to-end result by any means, or a deadline is cited. When an instruction conflicts with these rules, follow the rule, complete the compliant portion of the work, and state the conflict and the compliant alternative in the completion report.
- Organize code by scientific stage, not by services, managers, processors, factories, registries, or generic utilities.
- Keep one coherent scientific purpose in one Python file by default. Optimize for minimum semantic jumps, not minimum file length.
- Make the top-level stage read as a linear data narrative from config and input artifact to output artifact.
- Put materially different scientific procedures in sibling stage files. Do not hide them behind a runtime `mode` branch merely to deduplicate code.
- Merge branches only when their artifact contracts are semantically equivalent in representation, units, coordinates, time origin, preprocessing, and sample meaning—not merely shape and dtype.
- Treat artifacts as the only formal stage API. Approved artifacts are immutable; content changes invalidate approval.
- Never create, modify, or finalize an approval record. Produce artifacts and review packets only; approval is a human action performed through `scripts/scientific_artifact.py approve`, which requires explicit interactive confirmation. Use `finalize` to submit an artifact for review.
- Preserve stable sample IDs and emit an exclusion ledger whenever sample membership changes.
- Use TOML for human-authored scientific configuration and JSON for machine-generated metadata. Keep scientific parameters out of a large CLI surface.
- Keep scientific transformations explicit and data lineage visible; prefer new names over hidden in-place mutation.
- Add validation only at external trust boundaries, for scientific invariants, or to protect artifact integrity and provenance.
- Keep visualization presentation-only. Outlier removal, normalization, bootstrap intervals, fitting, and other scientific calculations belong in a stage artifact.
- Do not optimize without representative profiling. Judge optimization by end-to-end time to scientific answer.
- Do not add resumability without meaningful expected restart loss. Prefer idempotent shards over serialized Python execution state.
- Do not silently change scientific defaults, sample inclusion, randomness, or artifact semantics.
- Do not opportunistically refactor unrelated code or add architecture for hypothetical reuse.

## Classify and Route

Internally classify the request before editing. A task may need more than one class; read only the references for the active classes.

| Class | Use when | Required reference |
|---|---|---|
| `CREATE_STAGE` | Adding one scientific transformation stage | [references/stage.md](references/stage.md) |
| `MODIFY_STAGE` | Changing an existing stage | [references/stage.md](references/stage.md) |
| `CREATE_BRANCH` | Adding a materially different scientific procedure | [references/stage.md](references/stage.md) |
| `CHANGE_ARTIFACT_CONTRACT` | Changing artifact meaning, schema, lineage, or approval behavior | [references/artifact.md](references/artifact.md) |
| `CREATE_VIEW` | Creating or changing a figure, table, report, or exploration | [references/view.md](references/view.md) |
| `OPTIMIZE_STAGE` | Improving runtime or memory behavior | [references/optimization.md](references/optimization.md) |
| `ADD_RESUMABILITY` | Adding checkpoint, resume, or shard behavior | [references/resumability.md](references/resumability.md) |
| `DESIGN_INFERENCE` | Computing any statistic, interval, p-value, split, or comparison | [references/statistical_validity.md](references/statistical_validity.md) |
| `AUDIT_STAGE` | Reviewing a stage or pipeline for this model | [references/audit.md](references/audit.md) |
| `INFRASTRUCTURE` | Work outside the scientific pipeline itself | Keep science out of the infrastructure; use [references/audit.md](references/audit.md) only to check the boundary |

Also read [references/artifact.md](references/artifact.md) whenever a task creates a stage, changes inputs or outputs, changes sample membership, consumes approval state, or alters provenance.

## Working Sequence

1. Inspect the repository, existing contracts, configs, artifacts, and local instructions before proposing structure.
2. State internally the scientific purpose, active task class, input semantics, output semantics, and whether scientific behavior changes.
3. Separate genuine scientific forks from ordinary underspecification. If a missing choice would materially alter the method, contract, sample population, or randomness, ask the user before inventing it. For everything else — naming, layout, file placement, scope, and engineering detail — state the assumption briefly, adopt the narrowest reasonable interpretation, and keep working; record remaining questions in the completion report instead of stopping to ask them.
4. Make the narrowest coherent change. Preserve existing readable reference logic and unrelated user work.
5. Test scientific invariants, artifact contracts, lineage, and reference/resume equivalence as applicable; do not chase meaningless coverage.
6. Run the deterministic linter, then the project's normal tests and type checks:

   ```bash
   python <skill-dir>/scripts/scientific_code_lint.py <project-root> --changed-only
   ```

   Fix hard errors. Resolve warnings or add a narrow, reasoned file-level directive in the form `# scientific-code: allow SC1xx -- concrete justification`.
7. Do not declare completion while relevant deterministic checks fail.

Use ready-to-adapt files under [templates/](templates/) when creating contracts, manifests, pipeline configs, stage headers, or optimization evidence. Do not copy placeholders without replacing their semantics.

## Completion Report

For any code change, lead with the outcome and report verification. If scientific behavior may be affected, include this exact scientific diff with concise evidence:

```text
Scientific behavior changed: yes / no
Input semantics changed: yes / no
Output semantics changed: yes / no
Sample inclusion changed: yes / no
Randomness changed: yes / no
Artifact version changed: yes / no
Runtime materially changed: yes / no
```

For `MODIFY_STAGE`, also summarize before/after scientific behavior, whether the artifact contract changed, and why a version bump is or is not required. Never substitute a Git diff summary for this scientific diff.

List the assumptions adopted where the task was underspecified and any questions that remain open. A completion report that only asks questions and changes no code is not a completed task.

