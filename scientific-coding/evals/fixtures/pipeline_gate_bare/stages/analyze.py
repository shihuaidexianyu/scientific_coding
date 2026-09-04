# scientific-code: stage
"""Produce AnalysisResultV1.

Input artifact: ProcessedTrialsV1 (hash-bound). Transformation: compute the
difference of condition amplitude means and a percentile bootstrap
confidence interval over trials. Output artifact: AnalysisResultV1 (JSON
result plus a human-readable summary). Mutation: none; no side effects.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from common import REPO_ROOT, load_toml_config, sha256_file

RUN_DIR = REPO_ROOT / "artifacts" / "analysis_result" / "run_001"
INPUT_DIR = REPO_ROOT / "artifacts" / "processed_trials" / "run_001"
CONFIG_PATH = REPO_ROOT / "configs" / "analyze.toml"
CODE_PATH = REPO_ROOT / "stages" / "analyze.py"


def load_input_binding() -> dict[str, str]:
    """Read the approved input artifact's recorded hashes.

    Parameters: none. Returns the dict {path, artifact_hash, manifest_hash}
    of the input artifact directory. Method: read the input approval.json,
    require status "approved" (a pending_review artifact must stop the
    pipeline, not flow through it), then take artifact_hash and
    manifest_hash from the approval record and report the input path as a
    repo-relative POSIX string. No mutation or side effects.
    """
    approval = json.loads((INPUT_DIR / "approval.json").read_text(encoding="utf-8"))
    if approval.get("status") != "approved":
        raise ValueError(
            "input artifact is not approved; run `scientific_artifact.py approve` first"
        )
    return {
        "path": "artifacts/processed_trials/run_001",
        "artifact_hash": approval["artifact_hash"],
        "manifest_hash": approval["manifest_hash"],
    }


def mean_amplitudes(rows: list[dict[str, str]]) -> dict[str, float]:
    """Compute per-condition mean amplitude.

    Parameters: processed trial rows. Returns {condition: mean amplitude
    in microvolts}. Method: arithmetic mean over each condition's
    amplitude_uv values. No mutation or side effects.
    """
    totals: dict[str, list[float]] = {}
    for row in rows:
        totals.setdefault(row["condition"], []).append(float(row["amplitude_uv"]))
    return {condition: sum(values) / len(values) for condition, values in totals.items()}


def bootstrap_mean_difference_ci(
    control: list[float], treatment: list[float], n_bootstrap: int, seed: int, level: float
) -> tuple[float, float]:
    """Estimate a percentile bootstrap CI for the mean difference.

    Parameters: control amplitudes, treatment amplitudes, resample count,
    RNG seed, and confidence level. Returns (ci_low, ci_high) in
    microvolts. Method: for n_bootstrap iterations, resample each condition
    with replacement (rng = random.Random(seed)), record the difference of
    resampled means, then take the ((1 - level) / 2, 1 - (1 - level) / 2)
    empirical quantiles. No mutation or side effects.
    """
    import random

    rng = random.Random(seed)
    differences: list[float] = []
    for _ in range(n_bootstrap):
        resampled_control = [control[rng.randrange(len(control))] for _ in control]
        resampled_treatment = [treatment[rng.randrange(len(treatment))] for _ in treatment]
        differences.append(
            sum(resampled_treatment) / len(resampled_treatment)
            - sum(resampled_control) / len(resampled_control)
        )
    differences.sort()
    low_index = max(0, int(((1.0 - level) / 2.0) * n_bootstrap))
    high_index = min(n_bootstrap - 1, int((1.0 - (1.0 - level) / 2.0) * n_bootstrap))
    return differences[low_index], differences[high_index]


def write_analysis_artifact(result: dict, run_dir: Path) -> None:
    """Materialize the analysis payload.

    Parameters: the result dict and run directory. Returns nothing.
    Method: write result.json (machine-readable) and summary.md
    (human-readable, same numbers). No mutation or side effects.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Analysis result",
        "",
        f"- control mean amplitude: {result['control_mean_uv']} uV "
        f"(n = {result['n_control']})",
        f"- treatment mean amplitude: {result['treatment_mean_uv']} uV "
        f"(n = {result['n_treatment']})",
        f"- difference (treatment - control): {result['difference_uv']} uV",
        f"- bootstrap {int(result['confidence_level'] * 100)}% CI: "
        f"[{result['ci_low_uv']}, {result['ci_high_uv']}] uV "
        f"({result['n_bootstrap']} resamples, seed {result['seed']})",
        "",
    ]
    (run_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def write_run_record(binding: dict[str, str], run_dir: Path) -> None:
    """Write the execution record binding input and output hashes.

    Parameters: input binding dict and run directory. Returns nothing.
    Method: run.json records command, config and code paths plus sha256,
    the input artifact path with its approved artifact_hash and
    manifest_hash, and produced_artifact.path. output_artifact_hash is
    patched in by `scientific_artifact.py finalize`. No mutation or side
    effects.
    """
    record = {
        "command": "python stages/analyze.py",
        "config": {
            "path": "configs/analyze.toml",
            "sha256": sha256_file(CONFIG_PATH),
        },
        "code": {"path": "stages/analyze.py", "sha256": sha256_file(CODE_PATH)},
        "input_artifacts": [
            {
                "path": binding["path"],
                "artifact_hash": binding["artifact_hash"],
                "manifest_hash": binding["manifest_hash"],
            }
        ],
        "produced_artifact": {"path": "artifacts/analysis_result/run_001"},
        "started_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (run_dir / "run.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    binding = load_input_binding()
    config = load_toml_config(CONFIG_PATH)
    with (INPUT_DIR / "data" / "processed_trials.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    means = mean_amplitudes(rows)
    control = [float(row["amplitude_uv"]) for row in rows if row["condition"] == "control"]
    treatment = [
        float(row["amplitude_uv"]) for row in rows if row["condition"] == "treatment"
    ]
    ci_low, ci_high = bootstrap_mean_difference_ci(
        control,
        treatment,
        int(config["n_bootstrap"]),
        int(config["seed"]),
        float(config["confidence_level"]),
    )
    result = {
        "contract": "AnalysisResult@1",
        "n_control": len(control),
        "n_treatment": len(treatment),
        "control_mean_uv": round(means["control"], 4),
        "treatment_mean_uv": round(means["treatment"], 4),
        "difference_uv": round(means["treatment"] - means["control"], 4),
        "ci_low_uv": round(ci_low, 4),
        "ci_high_uv": round(ci_high, 4),
        "confidence_level": float(config["confidence_level"]),
        "n_bootstrap": int(config["n_bootstrap"]),
        "seed": int(config["seed"]),
        "method": "percentile bootstrap over trials, difference of condition means",
    }
    write_analysis_artifact(result, RUN_DIR)
    write_run_record(binding, RUN_DIR)
    print(f"analysis result -> {RUN_DIR} (difference {result['difference_uv']} uV)")


if __name__ == "__main__":
    main()
