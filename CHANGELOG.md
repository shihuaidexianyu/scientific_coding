# Changelog

## 0.4.0 - 2026-09-04

### Added
- SC109 heuristic warning: a view that performs scientific computation
  (bootstrap, outlier removal, percentile/interval statistics, normalization,
  fitting) is flagged. Comments, docstrings, string literals, and f-string
  text are masked so provenance narratives and axis labels do not fire.

### Changed
- SKILL.md non-negotiable rules: explicit statement that the rules bind
  regardless of instruction source (no forging approvals, mutating approved
  artifacts, or bypassing gates to satisfy a user instruction, an
  end-to-end-result demand, or a deadline); on conflict, do the compliant
  part and report the conflict plus the compliant alternative.
- SKILL.md working sequence: genuine scientific forks are separated from
  ordinary underspecification; adopt the narrowest reasonable assumption
  and keep working, recording open questions in the completion report.
- references/view.md: the presentation-only boundary holds regardless of
  where the work is requested, including explicit user requests to compute
  statistics inside the figure file.

### Fixed
- The linter no longer lints installed skill copies (`.claude/skills`,
  `.agents/skills`); their shipped example is not project code and its
  stage imports produced phantom SC001 noise in every eval workdir.
- Eval runs whose agent call failed at the API level (provider quota/429)
  are marked invalid (`pass=None`) instead of graded as real failures, and
  the rubric judge skips them; summary tables show an invalid count.
- The plot case drops its `fail_if` text pattern: plain regex could not
  distinguish executable statistics from a docstring, comment, or axis
  label naming the source artifact; masked SC109 plus the judge cover the
  failure mode with fewer false positives.

## 0.2.0 - 2026-09-04

### Added
- `scripts/scientific_artifact.py`: reference implementation of the artifact
  lifecycle (init / finalize / verify / approve). `finalize` writes the
  two-layer hashes and submits for review; `approve` is human-only, refuses
  non-interactive terminals, and requires typed confirmation.
- Linter support for a project-level `scientific-code.toml` declaring
  stage/view/artifact/infrastructure roots.
- `--base-ref` for merge-base diffs in CI; `--full-artifact-checks` for
  payload re-hashing on a separate, expensive tier.
- Transitive stage-import detection (SC001/SC006) with the import route in
  the message.
- Behavioral eval harness: `evals/run_evals.py`, `evals/graders.py`, fixture
  repositories, machine-checkable `fail_if_patterns`, Chinese prompts,
  self-approval and negative-control cases.
- Regression suites: `tests/test_linter.py` (per-check positive/negative/
  false-positive/suppression fixtures), `tests/test_artifact.py` (artifact
  CLI lifecycle).

## 0.3.0 - 2026-09-04

### Added
- `examples/minimal_pipeline/`: a complete, runnable worked example
  (synthetic acquisition -> preprocess with row-level exclusion ledger ->
  bootstrap analysis -> hand-written SVG view). Committed artifacts are
  approved, so `lint --full-artifact-checks` passes out of the box.
- `tests/test_integration.py`: committed-example verification, full
  lifecycle rebuild in a temp directory, same-seed hash reproducibility,
  and pending-review blocking downstream stages.
- `references/statistical_validity.md` (routed as `DESIGN_INFERENCE`):
  the seven units of statistical validity and the non-negotiable checks
  (n with its unit, no double-dipping, multiple comparisons, seed
  sensitivity).
- CI workflows: PR gate (tests + linter self-check + mock evals +
  committed-example full checks) and nightly real-model evals with
  archived results.
- Monorepo scope handling: when the lint root has no usable
  `scientific-code.toml`, the nearest nested project config is used, with
  its roots applied relative to the owning project directory.
- run.json `input_artifacts` relative paths resolve against the owning
  project's root (walk-up to the directory holding `scientific-code.toml`),
  not blindly against the lint root.

### Fixed
- Linting a monorepo root no longer misclassifies nested project stages
  or reports false SC005 "missing approval" for their recorded inputs.

### Fixed
- SC102/SC103 apply only inside pipeline scope; infrastructure code keeps
  its own conventions, matching the scope gate.
- SC001 no longer flags third-party modules merely named `stages`.
- SC105 validates report content (speedup ratio, equivalence pass, no
  placeholder prose) instead of matching names only.
- SC108 accepts NumPy/Google/Sphinx and Chinese contract docstrings; a
  complete module-level contract waives per-function checks.
- SC002 distinguishes scientific CLI parameters (error) from busy
  operational flags (warning).
- Approval records: template default is `pending_review`; the agent is
  forbidden to create or modify approval records (SKILL.md rule).
- Artifact integrity checks split: default metadata mode no longer reads
  payloads; external recorded inputs get payload verification in full mode.

## 0.1.0 - initial release

Design documents (SKILL.md, references/, templates/), the deterministic
linter (SC000-SC008, SC101-SC108), and the eval specification.
