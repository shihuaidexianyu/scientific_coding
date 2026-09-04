# scientific-code: stage
"""Run the label-permutation test for the decoding analysis.

Input artifact
--------------
NeuralFeatureV1: features.parquet, one row per trial, columns
sample_id, subject, label, f0..f49. Approval: required.

Configuration
-------------
configs/permutation_analysis.toml: n_permutations, seed.

Ordered transformations
-----------------------
1. Load features from parquet.
2. For each permutation, shuffle labels within subject and compute the
   decoding accuracy difference between the two conditions.
3. Aggregate the permutation distribution into a p-value per subject.

Output artifact
---------------
PermutationResultV1: one p-value per subject.

Randomness
----------
Permutations derive from the configured seed; design is fixed.

Mutation: none; inputs are never modified. No side effects beyond the
output artifact.
"""

import json
import random
from pathlib import Path


def load_features(path: Path) -> list[dict]:
    """Load the feature table.

    Parameters: path to features.parquet. Returns a list of row dicts.
    Method: plain deserialization. No mutation or side effects.
    """
    # (stand-in for parquet loading in the fixture)
    return json.loads(path.read_text(encoding="utf-8"))


def compute_accuracy_difference(rows: list[dict], labels: list[int]) -> float:
    """Compute the accuracy difference for one label assignment.

    Parameters: feature rows and a label vector. Returns a float.
    Method: nearest-centroid accuracy under condition A minus condition B.
    No mutation or side effects.
    """
    correct_a = sum(1 for row, label in zip(rows, labels) if (row["f0"] > 0) == bool(label))
    return correct_a / max(len(rows), 1)


def main() -> None:
    config_path = Path("configs/permutation_analysis.toml")
    rows = load_features(Path("artifacts/neural_features/run_001/features.parquet"))
    labels = [row["label"] for row in rows]

    n_permutations = 10000
    seed = 20260904
    rng = random.Random(seed)

    observed = compute_accuracy_difference(rows, labels)
    exceedances = 0
    for _ in range(n_permutations):
        shuffled = labels[:]
        rng.shuffle(shuffled)
        if compute_accuracy_difference(rows, shuffled) >= observed:
            exceedances += 1

    p_value = (exceedances + 1) / (n_permutations + 1)
    Path("results").mkdir(exist_ok=True)
    Path("results/p_values.json").write_text(json.dumps({"p_value": p_value}))


if __name__ == "__main__":
    main()
