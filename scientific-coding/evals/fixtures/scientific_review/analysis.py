"""A small two-source amplitude analysis."""
import csv
import json
import math
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parent


def load_trials(raw_path: Path, labels_path: Path) -> list[dict]:
    """Read and join the two CSV inputs."""
    with raw_path.open(newline="", encoding="utf-8") as stream:
        raw = list(csv.DictReader(stream))
    with labels_path.open(newline="", encoding="utf-8") as stream:
        label_rows = list(csv.DictReader(stream))
    labels = {row["trial_id"]: row["condition"] for row in label_rows}
    if len(labels) != len(label_rows) or len({row["trial_id"] for row in raw}) != len(raw):
        raise ValueError("Input trial IDs must be unique")
    if set(labels) != {row["trial_id"] for row in raw}:
        raise ValueError("The two sources must cover the same trial IDs")
    rows = [{"trial_id": row["trial_id"], "condition": labels[row["trial_id"]],
             "amplitude_uv": float(row["amplitude_uv"])} for row in raw]
    if any(not math.isfinite(row["amplitude_uv"]) or row["condition"] not in {"control", "treatment"} for row in rows):
        raise ValueError("Input amplitudes must be finite and labels declared")
    return rows


def filter_trials(rows: list[dict], floor_uv: float) -> tuple[list[dict], list[dict]]:
    """Split trials at the amplitude floor."""
    if len({row["trial_id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate trial IDs")
    if any(not math.isfinite(row["amplitude_uv"]) or row["condition"] not in {"control", "treatment"} for row in rows):
        raise ValueError("Invalid trusted row")
    retained = [row for row in rows if row["amplitude_uv"] >= floor_uv]
    excluded = [row for row in rows if row["amplitude_uv"] < floor_uv]
    return retained, excluded


def summarize(rows: list[dict]) -> dict:
    """Calculate counts, means and treatment minus control."""
    if len({row["trial_id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate trial IDs")
    if any(not math.isfinite(row["amplitude_uv"]) or row["condition"] not in {"control", "treatment"} for row in rows):
        raise ValueError("Invalid trusted row")
    groups = {name: [row["amplitude_uv"] for row in rows if row["condition"] == name]
              for name in ("control", "treatment")}
    if any(not values for values in groups.values()):
        raise ValueError("Filtering left an empty condition")
    counts = {name: len(values) for name, values in groups.items()}
    means = {name: sum(values) / len(values) for name, values in groups.items()}
    return {"counts": counts, "means_uv": means, "difference_uv": means["treatment"] - means["control"]}


def run(config_path: Path) -> dict:
    """Run the study and persist its result."""
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    floor = config["analysis"]["floor_uv"]
    if not isinstance(floor, (int, float)) or not math.isfinite(floor):
        raise ValueError("The scientific floor must be finite")
    rows = load_trials(ROOT / "raw.csv", ROOT / "conditions.csv")
    retained, excluded = filter_trials(rows, floor)
    result = summarize(retained)
    output = ROOT / "results"
    output.mkdir(exist_ok=True)
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    with (output / "exclusions.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["trial_id", "condition", "amplitude_uv"])
        writer.writeheader()
        writer.writerows(excluded)
    return result


if __name__ == "__main__":
    print(json.dumps(run(ROOT / "configs/analysis.toml")))
