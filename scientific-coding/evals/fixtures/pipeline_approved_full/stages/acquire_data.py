# scientific-code: acquisition-stage
"""Produce RawTrialsV1.

Input artifact: none (seeded synthetic stand-in for an instrument export).
Transformation: draw one trial amplitude per trial per condition from a
fixed normal mixture model; the draw is fully determined by config/seed so
the bytes are reproducible offline. Output artifact: RawTrialsV1 (CSV,
untouched acquisition content plus an acquisition provenance file).
Mutation: none; no side effects.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from common import REPO_ROOT, load_toml_config, sha256_file

AMPLITUDE_MEANS_UV = {"control": 1.0, "treatment": 1.4}
AMPLITUDE_STDS_UV = {"control": 0.4, "treatment": 0.4}
RUN_DIR = REPO_ROOT / "artifacts" / "raw_trials" / "run_001"
CONFIG_PATH = REPO_ROOT / "configs" / "acquire_data.toml"
CODE_PATH = REPO_ROOT / "stages" / "acquire_data.py"


def generate_trial_rows(config: dict) -> list[dict[str, object]]:
    """Draw every trial row of RawTrialsV1.

    Parameters: the parsed acquisition TOML config (n_trials_per_condition,
    seed). Returns one dict per trial with trial_id, condition, and
    amplitude_uv. Method: RNG = random.Random(seed); per condition, first
    sample the trial's latent standard-deviation multiplier from
    {0.7, 1.0, 1.3} (weights 1:8:1) with RNG.gauss(0, 1) helpers consumed in
    a fixed order, then amplitude_uv = RNG.gauss(mean, std * multiplier).
    No mutation or side effects.
    """
    import random

    n_per_condition = int(config["n_trials_per_condition"])
    rng = random.Random(int(config["seed"]))
    rows: list[dict[str, object]] = []
    for condition in ("control", "treatment"):
        for index in range(n_per_condition):
            weight_draw = rng.random()
            if weight_draw < 0.1:
                multiplier = 0.7
            elif weight_draw < 0.9:
                multiplier = 1.0
            else:
                multiplier = 1.3
            amplitude = rng.gauss(
                AMPLITUDE_MEANS_UV[condition], AMPLITUDE_STDS_UV[condition] * multiplier
            )
            rows.append(
                {
                    "trial_id": f"{condition}-{index + 1:03d}",
                    "condition": condition,
                    "amplitude_uv": f"{amplitude:.4f}",
                }
            )
    return rows


def write_raw_artifact(rows: list[dict[str, object]], run_dir: Path) -> None:
    """Materialize the raw acquisition payload and its provenance record.

    Parameters: trial rows and the run directory. Returns nothing.
    Method: write data/raw_trials.csv (one row per trial) and
    acquisition.json (config copy, generation model description, UTC
    timestamp). No mutation or side effects.
    """
    (run_dir / "data").mkdir(parents=True, exist_ok=True)
    with (run_dir / "data" / "raw_trials.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["trial_id", "condition", "amplitude_uv"])
        writer.writeheader()
        writer.writerows(rows)
    provenance = {
        "source": "synthetic seeded generation (stand-in for instrument export)",
        "generation_model": (
            "per trial: multiplier ~ {0.7:0.1, 1.0:0.8, 1.3:0.1}, "
            "amplitude_uv ~ normal(condition_mean, condition_std * multiplier)"
        ),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (run_dir / "acquisition.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_run_record(run_dir: Path) -> None:
    """Write the execution record for this acquisition run.

    Parameters: run directory. Returns nothing. Method: run.json records the
    executed command, config path plus sha256, code path plus sha256, zero
    input artifacts (this is the pipeline entry point), and UTC time.
    No mutation or side effects.
    """
    record = {
        "command": "python stages/acquire_data.py",
        "config": {
            "path": "configs/acquire_data.toml",
            "sha256": sha256_file(CONFIG_PATH),
        },
        "code": {"path": "stages/acquire_data.py", "sha256": sha256_file(CODE_PATH)},
        "input_artifacts": [],
        "started_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (run_dir / "run.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    config = load_toml_config(CONFIG_PATH)
    rows = generate_trial_rows(config)
    write_raw_artifact(rows, RUN_DIR)
    write_run_record(RUN_DIR)
    print(f"wrote {len(rows)} trial rows to {RUN_DIR}")


if __name__ == "__main__":
    main()
