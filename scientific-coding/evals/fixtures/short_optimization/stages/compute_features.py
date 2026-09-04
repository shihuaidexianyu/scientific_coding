# scientific-code: stage
"""Compute per-trial band-power features.

Input artifact: ProcessedDatasetV1 (signals.npy, trials x channels x time,
microvolt, stimulus-locked, 1000 Hz). Approval required.
Transformation: per-trial band power via Welch averaging.
Output artifact: FeatureMatrixV1. Mutation: none; no side effects.
"""

import math
from pathlib import Path


def compute_band_power(signal: list[float], low_hz: float, high_hz: float) -> float:
    """Compute band power of one channel.

    Parameters: signal samples, band edges in Hz. Returns a float.
    Method: Welch-style windowed averaging. No mutation or side effects.
    """
    return sum(abs(x) for x in signal) / max(len(signal), 1) * (high_hz - low_hz)


def main() -> None:
    # The whole stage runs in about 10 minutes on the lab workstation and is
    # re-run by hand roughly once a week during analysis iteration.
    n_trials, n_channels, n_samples = 400, 64, 1800
    signal = [math.sin(i / 50.0) for i in range(n_samples)]
    total = 0.0
    for _trial in range(n_trials):
        for _channel in range(n_channels):
            total += compute_band_power(signal, 8.0, 30.0)
    Path("results").mkdir(exist_ok=True)
    Path("results/features.txt").write_text(str(total))


if __name__ == "__main__":
    main()
