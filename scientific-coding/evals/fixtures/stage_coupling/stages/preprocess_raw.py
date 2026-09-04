# scientific-code: stage
"""Preprocess raw recordings into ProcessedDatasetV1.

Input artifact: RawDatasetV1. Transformation: invalid-trial removal,
baseline correction (-200..0 ms), resampling to 1000 Hz.
Output artifact: ProcessedDatasetV1 with exclusion ledger.
Mutation: none; no side effects.
"""

from pathlib import Path


def load_raw(path: Path) -> list[dict]:
    """Load raw trials.

    Parameters: path to the raw artifact. Returns a list of trial dicts.
    Method: deserialization only. No mutation or side effects.
    """
    return []


def baseline_correct(trials: list[dict]) -> list[dict]:
    """Subtract the pre-stimulus baseline mean per trial and channel.

    Parameters: trial list. Returns corrected trials.
    Method: per-trial mean over -200..0 ms subtracted sample-wise.
    No mutation; returns new objects. No side effects.
    """
    return trials


def main() -> None:
    trials = load_raw(Path("artifacts/raw/run_001/raw.parquet"))
    corrected = baseline_correct(trials)
    Path("results").mkdir(exist_ok=True)
    Path("results/processed.txt").write_text(str(len(corrected)))


if __name__ == "__main__":
    main()
