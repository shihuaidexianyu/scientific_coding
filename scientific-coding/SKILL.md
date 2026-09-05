---
name: scientific-coding
description: Create, modify, audit, and optimize readable scientific pipelines with annotated linear code, explicit configuration, self-describing data, and traceable results. Use for study preprocessing, analysis, inference, experiment scripts, and scientific views; do not impose this architecture on reusable libraries, dataset SDKs, or infrastructure.
---

# Scientific Coding

## Objective and scope

Make a scientific pipeline an executable, locally understandable description of the method. Prioritize scientific correctness, human readability, explicit lineage, reproducibility, and research iteration time before runtime performance, memory economy, reuse, or compactness.

Apply this skill to study-specific pipelines. Preserve reusable numerical libraries, parsers, dataset SDKs, simulation engines, and infrastructure as reusable software. In existing projects, make the narrowest coherent change: using this skill does not authorize migrating the configuration system or scaffolding an artifact framework. User instructions determine the task and may override this skill's engineering defaults.

## Default workflow

```text
declared input data + explicit configuration + scientific code
                              |
                              v
                    one readable stage
                              |
                              v
                 complete, described result -> next stage
```

Run through the requested outcome when inputs and scientific choices are established. A stage or intermediate file does not create a human approval gate. Pause only for an unresolved material scientific choice or at a review point the user explicitly requested. Reuse decisions already made in the conversation. Never represent automated execution or verification as a human review.

Preserve prior results when rerunning: write a new run, with its actual config and inputs. Versioning and provenance do not require approval records. Use the bundled artifact tool when hash-bound artifacts are useful; adapt an existing project's equivalent mechanism instead of adding a second one.

## Readability requirements

- **All explanatory comments and documentation are in Chinese.** This includes file headers, hover-visible function documentation, parameter/result descriptions, inline semantic-block comments, TOML comments, and data guides. Keep API identifiers, field names, and required tool directives intact; explain their meaning in Chinese.
- Begin every generated/edited source file with a readable Chinese purpose overview: which data/files it reads, which files/results it produces, its ordered processing logic, and the associated TOML paths and relevant sections/keys. State how relative paths resolve; explain when a file has no direct input/output or TOML dependency. Use the language's file/module documentation format while preserving required first-line directives.
- Document every defined function with the language's IDE-recognized documentation format, so hovering over a call can show its purpose, each parameter's content and concrete structure, its ordered logic, its return products/structures, and file writes or input mutation. In Python put a real docstring as the function's first statement. Give each parameter and each return value its own paragraph, with blank lines between sections and entries. Include the actual nested fields/axes locally; a link to another function is supplementary, not a substitute for this call's structure. Do not pack these into one line or rely on ordinary comments that hover cannot expose.
- Keep one coherent scientific purpose in one stage file by default. Its main computation follows execution order with meaningful intermediate names. Internal functions should name real scientific operations or clear I/O boundaries, and keep important calculations easy to find.
- Explain every meaningful operation next to its code. A comment may cover one statement or several consecutive statements accomplishing one operation. State purpose and relevant changes in values, shape, axes, units, or sample membership; do not merely translate syntax.
- Put one blank line **before each comment block**, then the explained code immediately after it. Consecutive lines of one comment block stay together. The first `#` block inside a function, including one immediately after its docstring, also needs this blank line. No leading blank is necessary at the start of a file or code cell; shebangs and encoding/tool directives retain required positions. Prefer preceding comments to trailing explanations. Function/file docstrings use blank lines internally to separate their readable sections.
- **Enforce comment spacing with code.** Write and run a small task-specific formatting script for all source/config languages you create or edit, not just Python or TOML. Use the relevant language's comment syntax/tokenizer so strings and required directives are preserved. Obtain a clean check on the final files; fix any reported spacing omissions and recheck. A clean check after the last edit needs no redundant no-op repair run. This is a temporary authoring tool, not a runtime validation step or a new project framework. See [readability.md](references/readability.md).
- Every generated or edited TOML file has descriptions for its sections and each key, including units, boundary conventions, and scientific effects where relevant. Use the same blank-before-comment layout, including array entries that need distinct explanations.
- Begin the pipeline with a data inventory and reading guide. Describe each stage result in the same way: location/format, fields or axes, types, units, sample meaning/identity, missing values, alignment, and how to load and use it. Explain important in-memory intermediate changes inline without requiring extra files.
- Keep comments, configs, contracts, and reading guides consistent with actual code. Check claimed effects and guarantees against the implementation; do not add plausible-sounding scientific or provenance claims. Mark unknown properties instead of inventing them. Substantial examples and data-description fields are in [references/readability.md](references/readability.md).

## Checks and established guarantees

Internal code relies on upstream guarantees that remain valid. Add a runtime check only for a concrete error that has not already been ruled out. A guarantee may come from a completed boundary check, an applicable API contract, or construction by the current code. A claim in an unverified external file is not a guarantee.

Before retaining a check, identify the error it detects, where that error was already excluded, and what intervening operation could reintroduce it. Remove the check if there is no such operation. Function calls, loops, and helper layers do not create new trust boundaries. Do not recheck the same keys, types, fields, IDs, shapes, file existence, hashes, or review decisions at each layer.

Validate an external input at its owning entry point; after a transformation, check only a newly at-risk scientific invariant. Prefer normal API errors for ordinary failures unless an early check prevents costly/partial work or materially improves diagnosis. Explain a guarantee once where established. Do not add validation managers, verified flags, proof logs, or wrappers merely to enforce this rule.

## Scientific structure

- Connect stages by described data contracts, not imports of another stage's scientific implementation. A small orchestrator may call stages but does not perform their science.
- Keep materially different methods visible, usually in sibling files. Share stable named scientific operations where doing so improves understanding. A user-requested alternative layout must still expose the scientific differences.
- Define multi-input roles and join rules explicitly. Preserve IDs; record exclusions when samples are removed and mappings when samples are split, joined, or aggregated.
- Use annotated, self-contained TOML for new scientific configs. Preserve an existing project's configuration format; capture the effective config and meaningful overrides. Runtime paths, hardware selection, workers, and credentials are execution inputs: they must not silently alter the scientific method, and credentials must not be copied into provenance.
- Keep formal views presentation-only by default. Scientific transformations must be explicit, documented, and retained as results; when the user requests a combined file, visibly separate analysis from rendering and document the deliberate boundary.
- Profile before adding performance complexity; consider repeated-run cost as well as single-run latency. Add resumability only when restart loss justifies it. Preserve a readable reference and scientific equivalence where applicable.

## Route and work

Read only the references needed for the task:

| Task | Reference |
|---|---|
| Create, modify, or branch a stage | [stage.md](references/stage.md), [readability.md](references/readability.md) |
| Create/change inputs, outputs, lineage, contracts, or review points | [artifact.md](references/artifact.md) |
| Compute statistics, comparisons, intervals, splits, or resampling | [statistical_validity.md](references/statistical_validity.md) |
| Create or change a scientific view | [view.md](references/view.md), [readability.md](references/readability.md) |
| Optimize | [optimization.md](references/optimization.md) |
| Add resume/checkpoint behavior | [resumability.md](references/resumability.md) |
| Audit or perform final review | [audit.md](references/audit.md) |

Inspect code, data descriptions, configs, and local instructions first. Establish the current scientific behavior and make the requested change. For any source/config generation or editing task, carry out this authoring sequence:

1. **Implement:** follow the plan through the requested outcome, keeping essential scientific intent and data assumptions beside the code.
2. **Simplify:** review scientific correctness and readability; remove redundant checks, dead code, needless indirection, and repeated gates before polishing explanations. Preserve user edits and established behavior unless a change is authorized.
3. **Explain:** inspect the affected source and its directly associated scientific configuration/data guides, including TOML whose parameter values did not change. Complete accurate Chinese file headers, hover-visible function documentation, semantic-block comments, TOML explanations, and data guides against the current implementation. Do not limit this pass to the source files edited during simplification; leave unrelated files and user-protected content alone.
4. **Format:** write and execute the task-specific comment formatter across every involved language, obtain a clean check on the final files, and verify parsing/meaning is preserved. Run repairs only when needed; a final clean check is sufficient after a later edit. Manual blank-line edits or a statement that formatting looks correct do not satisfy this operation.
5. **Verify:** review the final code and explanations together and run relevant scientific tests and the linter below. Stop when the requested outcome and relevant checks are satisfied; more tokens are justified by identified uncertainty, not by repeating successful checks.

These are authoring passes, not runtime pipeline stages or approval gates. One agent can perform them; do not require a multi-agent controller. Repair concrete findings through only the affected passes, then verify the changed result. Small edits need only the applicable work. See [workflow.md](references/workflow.md) for completion conditions and local repair examples.

**Handle intervention without losing the task.** Answer mid-review questions promptly, incorporate new instructions, and continue the main task unless the user pauses or replaces it. Before editing, reread the current affected files and compare them with the version last inspected; preserve manual changes and reconcile overlapping edits instead of overwriting them. A question alone does not invalidate prior checks. A code/config change invalidates only conclusions that depend on it; update affected explanations and rerun relevant validation. Never present checks on an older version as evidence for newer code. Ask only when a material conflict cannot be resolved from the conversation, and continue independent work meanwhile. Keep a brief working note when needed, not a new state machine or mandatory progress log.

The bundled linter does **not** enforce comment spacing and is **not** a substitute for the agent-written formatter. Do not insert the formatter into normal pipeline execution.

```bash
python <skill-dir>/scripts/scientific_code_lint.py <project-root> --changed-only
```

For a full audit, omit `--changed-only`; for committed changes use `--base-ref`. Fix errors, and resolve heuristic warnings or justify a deliberate exception. Passing lint does not prove that comments are true or the science is valid. Templates and [the runnable example](examples/minimal_pipeline/README.md) demonstrate the intended result.

## Completion report

Lead with the implemented outcome and validation, including any untested limits. When science may change, report before/after behavior, input/output semantics, sample inclusion or mapping, randomness, contract/run version, and material runtime effects. Explain assumptions and unresolved scientific questions. Do not bury the answer in a fixed boilerplate form or add a review gate at delivery.

For code/config edits, briefly state the languages covered by the executed formatter and its final check result; report actual execution, not intent.
