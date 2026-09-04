# scientific-code: stage
"""Main analysis driven by the project's existing Hydra configuration.

Input artifact: ProcessedDatasetV1 (approved). Transformation: group-level
statistics over the configured time window with the configured
normalization. Output artifact: AnalysisResultV1.
Mutation: none; no side effects.

Note: this project predates the skill and keeps its Hydra/YAML setup.
"""

from pathlib import Path

import yaml  # type: ignore


def load_config() -> dict:
    """Load the Hydra-composed configuration.

    Parameters: none (Hydra composes conf/config.yaml). Returns the resolved
    config dict. Method: Hydra composition. No mutation or side effects.
    """
    return yaml.safe_load(Path("conf/config.yaml").read_text(encoding="utf-8"))


def main() -> None:
    config = load_config()
    Path("results").mkdir(exist_ok=True)
    Path("results/statistics.txt").write_text(str(config["analysis"]["alpha"]))


if __name__ == "__main__":
    main()
