# Statistical validity

The artifact contract tracks what each number means and where it came
from; this reference tracks whether the number can bear the weight of the
conclusion drawn from it. These questions are decided when a stage is
written, not after a reviewer asks.

Contents: observation unit — sampling unit — independence — statistical
unit — split unit — permutation/exchangeability unit — bootstrap unit —
aggregation unit

## The seven units

Answer all seven explicitly in the stage docstring or artifact contract.
"Unit" always means "the thing a single index runs over"; confusing two of
these is the most common quiet way a pipeline produces an impressive,
invalid number.

1. **Observation unit** — one measured entity (one trial, one cell, one
   survey response). Row count of the raw artifact.
2. **Sampling unit** — the entity drawn from the population the claim is
   about (one participant, one animal, one site). Inference generalizes
   only over resampled sampling units.
3. **Independent unit** — the entity whose errors do not correlate; the
   effective sample size of any p-value or interval. Repeated measurements
   of one sampling unit are not independent units.
4. **Statistical unit** — the entity one fitted parameter describes.
5. **Split unit** — the entity kept whole when partitioning into train,
   test, or folds. Rows sharing a split unit must land in the same split
   or the evaluation leaks.
6. **Permutation/exchangeability unit** — the entity shuffled under the
   null. Swapping labels within a non-exchangeable block (e.g. within one
   participant) produces a null that does not match the hypothesis.
7. **Bootstrap unit** — the entity resampled. Bootstrapping observations
   when the sampling unit is participants produces intervals that are too
   narrow by roughly the cluster count.
8. **Aggregation unit** — the entity collapsed before reporting (per
   participant, per session, per run). Reported n after aggregation must
   match the independent unit or the precision is overstated.

## Non-negotiable checks

- **n in every claim**: any reported effect, interval, or p-value states
  which unit its n counts, and that unit is the independent unit.
- **No double-dipping**: data used to select an analysis step (features,
  regions, thresholds) is not also the data whose outcome is tested on
  that step, unless the selection step is nested inside the resampling
  loop.
- **Multiple comparisons**: every family of tests or intervals states its
  correction or carries an explicit per-comparison disclaimer in the
  artifact summary.
- **Random seeds are lineage, not validity**: a seed makes an artifact
  reproducible. It does not make a small-n result stable; report seed
  sensitivity (different seeds, same conclusion) when n is small.
- **Deterministic ≠ valid**: a fully seeded, fully approved artifact can
  still rest on shuffled blocks or leaked splits. The approval record
  covers provenance; these checks cover inference.

## Where each check lives

- The stage docstring names the seven units for its transformation.
- The artifact contract's `[sample]` section records the sampling unit,
  identity, and ordering.
- The analysis artifact's summary states n with its unit and the
  resampling scheme (n_bootstrap, seed, level, and what was resampled).
