# Artifact Contracts and Lineage

Contents: Artifact as the Formal API · Contract Semantics · Lifecycle and Approval · Stable Sample Identity and Exclusions · No Hidden Inputs · Provenance and Randomness · Atomic Production · Manifest Hash Convention · Orchestration

Read this reference whenever a task creates or changes a stage boundary, artifact contract, sample population, approval state, orchestration link, randomness record, or provenance record.

## Artifact as the Formal API

An artifact is the only formal API between stages. A useful artifact is:

- immutable after approval;
- versioned by scientific semantics;
- content-addressable or hashable;
- self-describing;
- traceable to code, inputs, config, environment, and randomness.

A typical directory contains data, an artifact contract, `manifest.json`, `runtime.json`, `run.json`, an optional exclusion ledger, and review previews. Use [the artifact contract template](../templates/artifact_contract.toml), [manifest template](../templates/artifact_manifest.json), and [run manifest template](../templates/run_manifest.json) as starting points.

## Contract Semantics

Do not decide compatibility from shape and dtype alone. Record and compare, as applicable:

- representation and scientific meaning;
- dimensions and axis meanings;
- dtype and missing-value conventions;
- unit and normalization basis;
- coordinate system or frame;
- sampling rate, time origin, and interval convention;
- preprocessing history that affects interpretation;
- sample identity, population, and ordering guarantees.

Version a contract when any of these meanings changes. A new optional presentation field may not need a semantic version change; a different baseline, unit, time origin, exclusion rule, or sample definition does.

### `CHANGE_ARTIFACT_CONTRACT`

1. Describe the current and proposed semantics field by field.
2. Identify every producer and consumer by artifact contract, not Python import.
3. Decide whether old and new artifacts remain scientifically interchangeable.
4. If not, create a new contract version and migrate consumers deliberately.
5. Invalidate approvals tied to changed content or contract hashes.
6. Test producer output and consumer validation against the new contract.
7. Report the semantic change and version decision.

Never overwrite a contract version with new meaning.

## Lifecycle and Approval

Keep execution success separate from scientific acceptance:

```text
producing -> produced -> reviewed -> approved -> frozen
                    \-> rejected
producing -> failed
approved  -> superseded
```

A successful run produces an artifact; it does not approve it. Formal downstream stages consume approved artifacts only. Bind approval to the artifact hash. If any tracked content changes, hash verification must fail and the approval becomes invalid.

Approval is a human action. An agent must never create or modify an approval record; it submits an artifact for review with `scripts/scientific_artifact.py finalize` (which writes a `pending_review` record) and the human approves with `scripts/scientific_artifact.py approve`, which verifies hashes, requires an interactive terminal, and demands typed confirmation. Integrity (hashes match) is not authenticity (a human reviewed); the approval ceremony exists to keep them distinct.

Review previews help a human inspect an artifact but do not become hidden scientific inputs.

## Stable Sample Identity and Exclusions

Use stable, meaningful IDs such as `subject03_session02_trial0017`, not row positions. Preserve them through raw, processed, feature, prediction, and statistics artifacts.

Whenever a transformation changes the sample set, emit an exclusion ledger with at least:

```text
sample_id
reason
stage
```

Record each excluded identity, not only aggregate counts. Validate that retained data, exclusion records, and reported totals reconcile.

## No Hidden Inputs

A formal stage's scientific inputs are exactly:

```text
declared artifact + TOML config + code
```

Do not make scientific behavior depend on home-directory files, arbitrary environment variables, `latest/`, undocumented caches, the internet, the system clock, or hidden globals. Put acquisition in an explicit `acquire_data.py` stage that materializes a frozen raw artifact; later stages consume that artifact.

## Provenance and Randomness

Every execution should answer: which code, input, config, environment, hardware, and seed produced this output? Record at least:

- run ID and stage name;
- Git commit and script path;
- config and input artifact hashes;
- output artifact hash;
- Python and relevant library versions;
- hardware relevant to numerical behavior;
- seed and deterministic mode where relevant.

If splits, folds, permutations, or mappings define the experiment design, materialize them as artifacts instead of regenerating them ad hoc in each analysis.

## Atomic Production

Write all data and metadata to a temporary run directory. Validate the contract, hashes, and required files there. Atomically rename the complete directory into its final artifact location only after successful completion. A failed process must not leave a directory that looks complete.

Do not modify files under an approved artifact. Produce a new version or run instead.

## Manifest Hash Convention

The bundled linter understands this deterministic convention:

- `manifest.json.files` maps paths relative to the artifact directory to `sha256:<hex>` content hashes.
- `manifest.json.identity_files` names the contract and scientific payload files that determine artifact identity. Execution metadata such as `run.json` remains integrity-tracked in `files` but is not an identity file.
- `manifest.json.contract` records the contract identity and hash.
- `manifest.json.artifact_hash` is the SHA-256 of canonical compact JSON containing `schema_version`, `contract`, and the hashes of `identity_files`.
- `manifest.json.manifest_hash` is the SHA-256 of canonical compact JSON containing the entire manifest except `manifest_hash` itself. It binds runtime/provenance file hashes without making `run.json.output_artifact_hash` circular.
- When status is `approved`, `approval.json` must bind both derived hashes.

Do not include `manifest.json` or `approval.json` in `files`, which would create a hash cycle.
Compute `artifact_hash` after writing the identity files; write that value into `run.json`; then hash all metadata files, finalize `manifest_hash`, and create the approval record only after human review.

This ordering is subtle. Never re-implement it by hand in stage code: `scripts/scientific_artifact.py finalize` is the reference implementation, and `verify` re-checks it.

## Orchestration

Keep orchestration small. It may know pipeline topology, script paths, config paths, input/output contracts, artifact locations, and approval state. It must not know filtering, HFB, classification, thresholds, or other scientific semantics.

Prefer only `run`, `status`, and `approve` operations. Define each scientific branch as a complete, readable TOML pipeline; do not use complex config inheritance to assemble it. Start from [the pipeline template](../templates/pipeline.toml).
