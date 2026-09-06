---
name: scientific-coding
description: Create, modify, audit, and optimize readable scientific pipelines with Chinese explanations, explicit data and configuration, and traceable results. Use for study preprocessing, analysis, inference and scientific views; do not impose pipeline architecture on reusable libraries, SDKs or infrastructure.
---

# Scientific Coding

## Purpose and scope

Make the scientific method locally understandable in executable code. Prioritize scientific correctness and human readability, then reproducibility and research iteration time. Work within the user's existing project and decisions; do not migrate configuration or scaffold an artifact framework merely because this skill is active.

Never trade code readability or explanatory completeness for fewer output tokens, lines or characters. Spend the tokens needed for explicit named intermediates, separate logical steps and Chinese documentation. Do not compress work into syntactic sugar, chained calls, lambdas, assignment expressions or short-circuit expressions merely to shorten output. A construct is acceptable only when the operation remains easier to understand and the readability rules below still hold. Reducing repeated skill instructions does not relax the generated-code requirements.

Complete the requested outcome. Stage boundaries do not require human approval. Pause only for an unresolved material scientific decision or a review point explicitly selected by the user. Preserve earlier results and manual edits.

## Write logic first; justify checks afterwards

The first draft contains only the original scientific/business logic: read, transform, compute and produce output. Do not preinstall assertions, defensive validation, preflights, fallback/repair branches or approval gates, including dormant validation scaffolding. Method-defining selection and branching remain part of the algorithm; normal reader/library exceptions propagate.

After the complete logical path exists, consider a runtime check only if a concrete, credible failure in this project makes it necessary. Establish the trigger and its likelihood evidence, the consequence, what upstream construction/contracts already exclude, why ordinary API errors or authoring-time tests are insufficient, and whether effective detection justifies the reading/runtime/maintenance cost. Unknown probability is not permission to add a check; do not invent percentages. Hypothetical rare memory corruption is not a reason for defensive pipeline code.

Reuse guarantees while valid. An external file, a helper call or an undocumented possibility does not automatically justify validation. Retain only justified checks at their owning boundary; do not generate check registries, proof logs or approval forms. For existing code, assess actual checks before removing them; the draft rule does not authorize breaking established behavior blindly. The decision policy and examples live in [checks.md](references/checks.md).

Authoring review/tests and recording actual execution are distinct from runtime validation. The first draft is a writing phase, not permission to publish unverified results. Add the required execution recording at the outer boundary before the delivered program runs; keep it out of numerical logic.

## Readable code and explanations

- All explanatory comments, file/function documentation, TOML descriptions and data guides are Chinese; keep API identifiers intact.
- Each edited/generated source file has an accurate purpose, actual inputs/outputs, associated configuration and a character flow diagram. Python module opening quotes occupy their own line.
- Every function has hover-visible documentation in this order: purpose, 参数, 返回, 处理过程, 副作用. Names/types are separate from indented explanations; separate parameters/returns with blank lines and describe fields, axes and units locally.
- Explain meaningful operations next to their code, one comment per semantic block rather than per punctuation line. Put a blank before each comment block, including after docstrings, and keep its code immediately after it. Explain associated TOML sections and keys.
- Source/config lines, including comments/docstrings, are at most 80 characters. Use one comprehension layer and one `for` with at most one simple filter; expand additional nesting. Keep explicit control flow shallow.
- Name intermediate filtering, mapping, aggregation and constructed data before passing it as an argument. Use explicit branches for multi-step fallback and mixed conditional selection; preserve evaluation order, false-valued data and iterator laziness.
- One loop has one purpose. Separate collecting, determining reasons and constructing output into named steps without trivial wrappers or generic frameworks.
- Inventory initial data and describe each stage result: location/format, fields/axes, types/units, identity/alignment, actual reading method and changes from inputs. Explain important in-memory intermediates locally.

Use [readability.md](references/readability.md) for exact rules and [stage_header.md](templates/stage_header.md) for the single maintained function/header layout. Correct explanations to match intended behavior; do not change science just to make an inaccurate comment true.

## Scientific and execution boundaries

- Keep coherent scientific operations visible and ordered. Formal stages exchange described data, not imports of other stages' implementation. Create persisted boundaries only when retention, reuse or restart warrants them.
- Keep materially different methods visible in sibling implementations. Preserve IDs and record actual exclusions, splits, joins and aggregations. Choose statistical units and resampling from the study design.
- Use self-contained annotated TOML for new scientific configuration; preserve an existing format. Runtime options must not silently change the method.
- Views normally present retained calculations. Respect a requested combined-file layout while making analysis and rendering distinct.
- Every runnable scientific entry point retains actual provenance, full stdout/stderr/tracebacks, UTC lifecycle, real status/exit code, stage times and available CPU/RAM/VRAM with measurement scope. One outer attempt record suffices; batch indexes link all attempts, including failures and retries. Preserve old results and failed diagnostics; reuse existing infrastructure.
- After scientific code or computational configuration changes, give a Chinese workload/time/memory estimate with hardware/workers, bottlenecks and evidence. Distinguish measurements, extrapolation and unknowns. Do not invent runtime numbers or automatically start optimization.

## Authoring workflow

1. **Implement:** complete the original logical path, without defensive checks. Keep essential scientific intent beside the computation.
2. **Simplify and decide:** remove needless indirection, simplify expressions/loops, and apply the check-necessity policy to actual candidates. No default quota of checks.
3. **Explain:** complete accurate Chinese code, interface, data and associated configuration descriptions against the current source.
4. **Format:** write and run a task-specific, language-aware script for comment spacing and the 80-character limit. Verify string/parse meaning is preserved and obtain a clean final check.
5. **Verify:** review final code and explanations together; run checks relevant to the change. For complete plans or substantial multi-function work, use a permitted independent read-only agent when available. Fix concrete findings through only the affected passes, then verify the changed result.

These are authoring responsibilities, not five approvals or runtime stages. Small changes need only applicable work. Do not repeat successful checks without a new change, failure or unresolved concern. Details and intervention handling: [workflow.md](references/workflow.md).

When the user intervenes, answer promptly and continue unless they pause or replace the task. Reread affected files before editing, preserve manual changes, and invalidate only evidence dependent on changed code/config. Ask only about material unresolved conflicts; no new state machine or mandatory working log.

## Load only what the task needs

Do not open every reference or copy all templates/examples. The entrypoint supplies shared constraints; load a reference only when making the decision it covers. Previously read, unchanged instructions need not be reread every pass.

| Current decision | Reference |
|---|---|
| Add/remove/retain runtime checks | [checks.md](references/checks.md) |
| Write explanations, format, simplify expressions | [readability.md](references/readability.md) |
| Create/change a stage or scientific branch | [stage.md](references/stage.md) |
| Define data boundaries, lineage or retained artifacts | [artifact.md](references/artifact.md) |
| Design inference, splits or resampling | [statistical_validity.md](references/statistical_validity.md) |
| Build scientific views | [view.md](references/view.md) |
| Add/change runnable entry points and records | [execution.md](references/execution.md) |
| Give an ordinary cost estimate | [estimation.md](references/estimation.md) |
| Actually optimize performance | [optimization.md](references/optimization.md) |
| Decide/implement resumability | [resumability.md](references/resumability.md) |
| Perform a substantive final or requested audit | [audit.md](references/audit.md) |
| Interpret linter findings or configure its scope | [lint.md](references/lint.md) |

The integrated [example](examples/minimal_pipeline/README.md) demonstrates optional artifact/review/resume facilities together; it is not a default scaffold. Use only needed parts.

## Verification and delivery

Run the relevant changed-code linter where applicable:

    python <skill-dir>/scripts/scientific_code_lint.py <project-root> --changed-only

For a whole-project audit omit `--changed-only`; for committed changes use `--base-ref`. Fix errors and assess heuristic warnings from actual evidence. This linter does not enforce the new expression/80-character/comment-spacing rules or prove scientific/documentation truth; use the task script and semantic review. Keep authoring tools outside the runtime pipeline.

Lead delivery with the outcome, actual validation and limits. Report material method/data/population/randomness changes when applicable, the formatter's coverage and final result, actual log/record/index locations for runnable work, and the Chinese cost estimate. A zero exit code does not mean statistical significance. Explain a non-obvious retained check briefly when useful; do not attach a mandatory check ledger or approval form.
