# scientific-code: stage
"""Produce ProcessedTrialsV1.

Input artifact: RawTrialsV1 (hash-bound). Transformation: reject trials whose
amplitude falls below the config floor as presumed artifacts; every rejected
trial is listed with its reason in the exclusion ledger. Output artifact:
ProcessedTrialsV1 (CSV of retained trials plus exclusions.csv ledger).
Mutation: none; no side effects.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from common import REPO_ROOT, load_toml_config, sha256_file

RUN_DIR = REPO_ROOT / "artifacts" / "processed_trials" / "run_001"
INPUT_DIR = REPO_ROOT / "artifacts" / "raw_trials" / "run_001"
CONFIG_PATH = REPO_ROOT / "configs" / "preprocess.toml"
CODE_PATH = REPO_ROOT / "stages" / "preprocess.py"


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
        "path": "artifacts/raw_trials/run_001",
        "artifact_hash": approval["artifact_hash"],
        "manifest_hash": approval["manifest_hash"],
    }


def select_valid_trials(
    rows: list[dict[str, str]], floor_uv: float
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Split raw rows into retained trials and ledger exclusions.

    Parameters: raw trial rows and the amplitude floor in microvolts.
    Returns (retained_rows, exclusion_rows); each exclusion row carries
    trial_id, condition, amplitude_uv, and reason. Method: one pass,
    amplitude < floor -> excluded with reason "below amplitude floor
    {floor} uV". No mutation or side effects.
    """
    retained: list[dict[str, str]] = []
    excluded: list[dict[str, str]] = []
    for row in rows:
        if float(row["amplitude_uv"]) < floor_uv:
            excluded.append(
                {
                    "trial_id": row["trial_id"],
                    "condition": row["condition"],
                    "amplitude_uv": row["amplitude_uv"],
                    "reason": f"below amplitude floor {floor_uv} uV",
                }
            )
        else:
            retained.append(row)
    return retained, excluded


def write_processed_artifact(
    retained: list[dict[str, str]], excluded: list[dict[str, str]], run_dir: Path
) -> None:
    """Materialize the processed payload and the exclusion ledger.

    Parameters: retained rows, exclusion rows, run directory. Returns
    nothing. Method: write data/processed_trials.csv (one row per retained
    trial) and exclusions.csv (one row per excluded trial, with reason).
    No mutation or side effects.
    """
    (run_dir / "data").mkdir(parents=True, exist_ok=True)
    with (run_dir / "data" / "processed_trials.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=["trial_id", "condition", "amplitude_uv"])
        writer.writeheader()
        writer.writerows(retained)
    with (run_dir / "exclusions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["trial_id", "condition", "amplitude_uv", "reason"]
        )
        writer.writeheader()
        writer.writerows(excluded)


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
        "command": "python stages/preprocess.py",
        "config": {
            "path": "configs/preprocess.toml",
            "sha256": sha256_file(CONFIG_PATH),
        },
        "code": {"path": "stages/preprocess.py", "sha256": sha256_file(CODE_PATH)},
        "input_artifacts": [
            {
                "path": binding["path"],
                "artifact_hash": binding["artifact_hash"],
                "manifest_hash": binding["manifest_hash"],
            }
        ],
        "produced_artifact": {"path": "artifacts/processed_trials/run_001"},
        "started_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (run_dir / "run.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    binding = load_input_binding()
    config = load_toml_config(CONFIG_PATH)
    with (INPUT_DIR / "data" / "raw_trials.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    retained, excluded = select_valid_trials(rows, float(config["amplitude_floor_uv"]))
    write_processed_artifact(retained, excluded, RUN_DIR)
    write_run_record(binding, RUN_DIR)
    print(f"retained {len(retained)} trials, excluded {len(excluded)} -> {RUN_DIR}")


if __name__ == "__main__":
    main()
