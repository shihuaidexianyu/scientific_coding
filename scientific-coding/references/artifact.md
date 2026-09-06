# Data contracts, lineage, and results

Use when creating/changing data boundaries, provenance, run handling, or a user-selected review point.

## Data as the stage interface

A stage consumes one or more explicitly named datasets and produces described results. Downstream code uses the data contract, not the upstream scientific implementation. Keep stage code linear even when the overall dependency graph branches or joins.

A result worth retaining has data, an annotated contract or equivalent data description, and actual input/config/code provenance. Use existing project conventions when adequate. In a new hash-bound workflow, the bundled tool uses `artifact_contract.toml`, `run.json`, and `manifest.json`. Ordinary execution logs/timing/resource records are required; detailed profiler traces and review previews are added when useful. Exclusion ledgers and mappings are required when the corresponding sample changes occur. Approval files are optional.

The contract describes representation, fields/axes, types, units, missing values, coordinates/time, preprocessing, sample identity, ordering, and population where applicable. Include formats and loading instructions from [readability.md](readability.md). A data description is not a request to generate a validator for every field. The optional generic verifier handles supported metadata and CSV/JSON schemas; author review establishes domain assumptions and applies checks.md before adding runtime guards.

Version the contract when interpretation changes. A new run/config always gets a new output location. A comments-only edit to a tracked contract may preserve the semantic version but changes an identity file, so a newly produced artifact has a new artifact hash. Source comments recorded only through a code hash in run.json change the manifest hash; they need not change the artifact hash when identity files are unchanged. Do not rewrite historical results to add explanations.

## Multiple inputs and sample transformations

Name each input role and contract, including acquisition data, labels, behavioral tables, splits, masks, and model/design artifacts. For joins declare the keys, expected one-to-one/one-to-many/many-to-one cardinality, order, population, and handling of duplicate or missing matches. Do not silently let a join expand the population.

Preserve sample IDs when identity is unchanged. Emit per-ID reasons for exclusions. For one-to-many splits (trial to windows) and many-to-one aggregation (trials to subject), preserve parent/child mappings with the aggregation/window rule; a retained mapping is not an exclusion. Carry weights when they determine contribution. Report counts with their units and reconcile mappings as appropriate.

## Necessary validation and provenance

Apply [checks.md](checks.md) after the full logical path is written; external origin alone does not justify runtime validation. Keep the actual input/config/version binding for provenance. When the chosen reuse protocol requires exact hash-bound identity, verify that identity once at its owning entry and reuse it while valid. Do not rescan unchanged in-process data. A previous approval is a recorded decision, not evidence about newly read bytes.

Record actual input roles and hashes/versions, effective config (including overrides), code revision or source hash including dirty changes, environment/library versions, and randomness needed to reproduce the computation. Do not substitute placeholder commits or claimed measurements. Distinguish execution inputs (worker count, scheduler, hardware, temporary paths) from scientific choices; never record credentials. Materialize experiment-defining splits or permutations when necessary to preserve their identities across consumers.

## Production and reruns

Every ordinary and failed execution also retains the logs, timing/resource evidence, outcome/exit code and batch-index links required by [execution.md](execution.md). Store these mutable attempt records outside finalized scientific artifacts, reference existing provenance, and keep failure diagnostics even when discarding unpublished payloads. Logging is execution bookkeeping, not an approval or validation gate.

Write a complete result to a staging directory on the same filesystem, then publish it under a fresh final name. Refuse to overwrite an existing run. Clean up only that run's own staging directory on failure. The public directory must contain the contract, payload, and provenance before it appears complete.

Retain requested deliverables at their declared locations after validation. Demonstrate tamper rejection or invalid inputs using a disposable copy separate from the active results directory; do not leave intentionally corrupt examples mixed with completed results or remove the user's deliverables while cleaning up tests.

`scientific_artifact.py finalize <dir>` finalizes a staging directory: validates the declared contract metadata, writes hashes and manifest, and returns without waiting for review. The producer owns data invariants; finalization does not repeat row/schema scans or certify scientific validity. `verify --full` checks supported payload schemas when independently auditing or loading external data. Finalization never creates an approval record by default. Stage I/O owns directory publication; finalization alone is not an atomic whole-directory publish. Use the example's narrow I/O boundary instead of duplicating hash machinery in each stage.

## Optional human review

Default: a complete, valid result may flow directly downstream. Users inspect data descriptions, exclusions, diagnostics, and summaries as needed; entering a new stage is not a reason to ask again.

Only when the user explicitly selects a pause point, finalize that result with `--request-review`. This records `review_required = true` in its manifest and creates a pending review record. Stop at that selected boundary and present the concrete result to inspect. The optional `approve` command records the human's review against exact hashes; do not pretend that a terminal prompt authenticates a human or that automated verification is scientific acceptance. Never invent a reviewer or claim that the user inspected something they did not inspect.

Preserve an existing explicit review requirement until the user changes it. Ordinary results without a review requirement do not need an approval file. Integrity verification works identically with or without approval; reading a review-required result additionally checks its decision once at the consuming boundary. A new input version does not inherit an old decision. Do not introduce review state checks inside scientific functions.

## Hash convention

The tool retains two hashes for compatibility with existing artifacts:

- `manifest.json.files`: relative paths to SHA-256 bytes for every tracked file.
- `identity_files`: contract and scientific data determining scientific identity. Explicitly select identity files when other metadata mixes scientific content with timestamps; `run.json`/`runtime.json` are execution metadata and excluded by default.
- `artifact_hash`: canonical JSON of schema version, contract descriptor, and identity file hashes.
- `manifest_hash`: canonical JSON of the manifest except its own hash, binding remaining provenance too.
- Optional approval binds both hashes. Manifest and approval themselves are excluded from `files` to avoid cycles.

Compute identity hashes, then output artifact hash, then put that hash in run.json, hash remaining metadata, and compute manifest hash. Use the tool rather than reimplementing this order. Metadata verification checks paths, canonical recorded hashes, and any approval binding; `--full` additionally rehashes content **regardless of review status**. Content integrity and requested review are separate concerns.
