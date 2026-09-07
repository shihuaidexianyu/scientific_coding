# Statistical validity

Use when designing inference, resampling, splits, or scientific comparisons. Define the target estimand, population, design, and uncertainty before choosing a computation. Data provenance and reproducibility do not prove inference valid.

## Relevant units

Describe the applicable units in the stage contract/docstring; mark irrelevant ones not applicable rather than inventing a split or resampling scheme. Several units may coincide.

1. Observation: what each measured row/index represents.
2. Sampling: how entities were sampled and the population the claim targets.
3. Dependence: which observations share participants, sites, sessions, time dependence, or other correlation; specify modeled clusters or independent entities.
4. Analysis: what enters the estimator/model, the target parameter, and how that parameter relates to the scientific question. A regression coefficient is not itself a sampling unit.
5. Split: what must remain together across training/test/folds for the intended generalization target; fit learned preprocessing using training data only.
6. Exchangeability: permitted label permutations or sign flips under the actual null, respecting design and dependence.
7. Bootstrap: which entities are resampled and whether resampling is stratified, paired, clustered, hierarchical, or model-based.
8. Aggregation: which entities are combined, their weights, and what reported counts represent.

Do not infer exchangeability solely from participant identity: within-block and whole-block permutation are both valid in appropriate designs. Explain why the chosen transformations preserve the null distribution. See [Winkler et al., 2014](https://pmc.ncbi.nlm.nih.gov/articles/PMC4010955/).

Ignoring clustering can understate uncertainty, but its magnitude is not a universal multiple of the number of clusters. In a simple equal-size exchangeable-cluster setting the variance design effect is `1 + (m - 1) * rho`; applicability depends on the design and estimator. See [CONSORT cluster-trial methods](https://www.bmj.com/content/328/7441/702). State the relevant assumptions instead of copying this formula into unrelated analyses.

## Author review of the actual inference

Report n with its unit and relevant cluster/group counts. Do not confuse row count with independent information or claim every model's effective sample size equals a simple count. Review the split/fit design for leakage and overlap using the actual construction and relevant offline tests. This authoring responsibility does not automatically require runtime assertions: decide those only after the logical path is complete, using [checks.md](checks.md). Necessary checks belong to orchestration before the affected fit/inference, including checks on newly selected data; scientific functions reuse still-valid guarantees.

Account for data-driven selection in inference through valid independent data, nested resampling, or an appropriate selective-inference method. State each test family's multiplicity policy and interpretation; a per-comparison disclaimer does not create familywise control.

Record random seeds for reproducibility. Separate Monte Carlo error from uncertainty due to the sampled data. Increasing bootstrap replicates reduces simulation error in the estimated interval; it does not guarantee that the confidence interval becomes narrower. When resampling precision is inadequate, assess or increase simulation accuracy; do not search for seeds yielding a desired conclusion. Report observed seed sensitivity honestly; agreement across seeds is not proof of scientific validity.

Place scientific calculations in a documented stage, retain experiment-defining mappings where needed, and include the estimand, sample counts, method assumptions, resampling design, and uncertainty in the result summary.
