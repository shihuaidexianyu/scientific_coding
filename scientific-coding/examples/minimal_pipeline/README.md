# Minimal pipeline example

A complete, runnable example of the scientific-coding model on a toy study:
does trial amplitude differ between two conditions?

```text
acquire_data.py     -> RawTrialsV1        (synthetic stand-in for a download)
preprocess.py       -> ProcessedTrialsV1  (invalid-trial removal + ledger)
analyze.py          -> AnalysisResultV1   (bootstrap confidence interval)
figure_results.py   -> results.svg        (presentation only)
```

Every step follows the rules: declared contracts, TOML config, exclusion
ledger, two-layer hashes, human approval between stages, scientific work
kept out of the figure.

## Run it

From this directory, with Python 3.11+:

```bash
SKILL=../../scripts/scientific_artifact.py

python stages/acquire_data.py
python $SKILL finalize artifacts/raw_trials/run_001
python $SKILL approve artifacts/raw_trials/run_001 --reviewer you

python stages/preprocess.py
python $SKILL finalize artifacts/processed_trials/run_001
python $SKILL approve artifacts/processed_trials/run_001 --reviewer you

python stages/analyze.py
python $SKILL finalize artifacts/analysis_result/run_001
python $SKILL approve artifacts/analysis_result/run_001 --reviewer you

python figures/figure_results.py

python ../../scripts/scientific_code_lint.py . --full-artifact-checks
```

`approve` refuses to run without an interactive terminal — that refusal is
the point: approval is a human action, and the agent must stop at
`finalize` and ask. The committed artifacts were approved by the maintainer
(same reviewer id recorded in each approval.json), so `lint
--full-artifact-checks` passes out of the box; after re-running
`acquire_data.py` (same seed, identical bytes) you can re-finalize and
re-approve to reproduce the same hashes.

## What to notice

- Each stage reads only its declared input artifact (hash-bound), its TOML
  config, and its code — nothing else influences the science.
- `preprocess.py` emits one row per excluded trial, not a count.
- The bootstrap confidence interval lives in `AnalysisResultV1`; the
  figure only formats approved values into SVG.
- `scientific-code.toml` declares which directories are stages, views, and
  infrastructure, so the linter needs no naming guesses.
