"""Calculate a retained-amplitude mean for one tiny recorded signal example."""
import json
from pathlib import Path
import tomllib
# Read the threshold and display label from the study configuration.
config = tomllib.loads(Path("parameters.toml").read_text(encoding="utf-8"))
note = """Recorded signal
# This line is string data, not a Python comment.
End of record"""
# Exclude values below the floor; the equality boundary is retained.
amplitudes_uv = [0.2, 0.8, 1.2]
retained = [value for value in amplitudes_uv if value >= config["analysis"]["floor_uv"]]
# Serialize the retained count and mean with the unchanged descriptive strings.
result = {"label": config["analysis"]["label"], "note": note, "count": len(retained), "mean_uv": sum(retained) / len(retained)}
Path("result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(f"retained={result['count']} mean_uv={result['mean_uv']:.3f}")
