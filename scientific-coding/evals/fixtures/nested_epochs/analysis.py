"""Small synthetic epoch study; input.json -> baseline correction -> results."""
import json
import math
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parent


def analyze_epochs(epochs: list, conditions: list[str], times_s: list[float],
                   channel_names: list[str], baseline_indices: list[int]) -> tuple[dict, list]:
    """Baseline-correct epochs, average conditions and return summary plus corrected values.
    epochs is trials/channels/time, conditions labels rows, times_s times, channel_names names, baseline_indices baseline points.
    Returns summary dict and corrected array; no mutation or I/O.
    """
    corrected = [[[value - sum(channel[index] for index in baseline_indices) / len(baseline_indices)
                   for value in channel] for channel in trial] for trial in epochs]
    groups = {}
    for name in ("control", "treatment"):
        selected = [trial for trial, label in zip(corrected, conditions) if label == name]
        groups[name] = {"n_trials": len(selected),
                        "mean_uv": [[sum(trial[c][t] for trial in selected) / len(selected)
                                     for t in range(len(times_s))] for c in range(len(channel_names))]}
    difference = [[groups["treatment"]["mean_uv"][c][t] - groups["control"]["mean_uv"][c][t]
                   for t in range(len(times_s))] for c in range(len(channel_names))]
    peak_indices = [max(range(len(times_s)), key=lambda index: abs(channel[index])) for channel in difference]
    summary = {"axes": {"times_s": times_s, "channel_names": channel_names}, "groups": groups,
               "contrast": {"mean_difference_uv": difference,
                            "peak_uv": [channel[index] for channel, index in zip(difference, peak_indices)],
                            "peak_time_s": [times_s[index] for index in peak_indices]}}
    return summary, corrected


def run(config_path: Path) -> dict:
    """Load JSON and TOML, check external dimensions, write results, return summary."""
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    data = json.loads((ROOT / "input.json").read_text(encoding="utf-8"))
    epochs, conditions = data["epochs_uv"], data["conditions"]
    times, channels = data["times_s"], data["channel_names"]
    indices = config["baseline"]["sample_indices"]
    if (not epochs or not times or not channels or len(epochs) != len(conditions)
            or set(conditions) != {"control", "treatment"}
            or any(len(trial) != len(channels) or any(len(channel) != len(times) for channel in trial)
                   for trial in epochs)):
        raise ValueError("External data dimensions or conditions are inconsistent")
    if any(not math.isfinite(value) for trial in epochs for channel in trial for value in channel):
        raise ValueError("Epoch values must be finite")
    if not indices or any(type(index) is not int or not 0 <= index < len(times) for index in indices):
        raise ValueError("Baseline indices must be nonempty valid sample indices")
    summary, corrected = analyze_epochs(epochs, conditions, times, channels, indices)
    output = ROOT / "results"
    output.mkdir(exist_ok=True)
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (output / "corrected_epochs.json").write_text(json.dumps(corrected, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run(ROOT / "configs/analysis.toml")))
