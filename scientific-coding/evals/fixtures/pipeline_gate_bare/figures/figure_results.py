# scientific-code: view
"""Render results.svg from the approved AnalysisResultV1.

Input artifact: AnalysisResultV1 (approved; hash-bound by its manifest).
View: read the approved result.json, format its already-computed numbers
into a standalone SVG bar figure. Scientific content (means, bootstrap CI)
was computed in the analyze stage; this view contains presentation only.
Deletion test: deleting this file loses no scientific content.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULT_PATH = REPO_ROOT / "artifacts" / "analysis_result" / "run_001" / "result.json"
OUTPUT_PATH = REPO_ROOT / "figures" / "results.svg"


def load_approved_result(path: Path) -> dict:
    """Read the approved analysis result.

    Parameters: path to the result artifact's result.json. Returns the
    parsed result dict. Method: JSON parse only; this view never recomputes
    statistics. No mutation or side effects.
    """
    return json.loads(path.read_text(encoding="utf-8"))


def render_svg(result: dict) -> str:
    """Format approved numbers into a standalone SVG bar figure.

    Parameters: the AnalysisResultV1 dict. Returns the SVG document text.
    Method: map control/treatment means to bar heights, draw a 640x400 SVG
    with axes, bars, value labels, and a caption carrying the bootstrap CI
    and method note; no statistics are computed here. No mutation or side
    effects.
    """
    width, height = 640, 400
    plot_left, plot_bottom = 80, 320
    plot_top, plot_right = 40, 600
    max_bar_uv = 2.0
    bar_width = 120
    gap = 140
    x_control = plot_left + 90
    x_treatment = x_control + gap
    scale = (plot_bottom - plot_top) / max_bar_uv
    control_height = result["control_mean_uv"] * scale
    treatment_height = result["treatment_mean_uv"] * scale
    ci_text = (
        f"{int(result['confidence_level'] * 100)}% bootstrap CI of difference: "
        f"[{result['ci_low_uv']}, {result['ci_high_uv']}] uV "
        f"({result['n_bootstrap']} resamples, seed {result['seed']})"
    )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'  <rect x="0" y="0" width="{width}" height="{height}" fill="white"/>',
        f'  <text x="{width / 2}" y="24" text-anchor="middle" font-size="18" '
        f'font-family="sans-serif">Mean trial amplitude by condition</text>',
        f'  <line x1="{plot_left}" y1="{plot_bottom}" x2="{plot_right}" y2="{plot_bottom}" '
        f'stroke="black"/>',
        f'  <line x1="{plot_left}" y1="{plot_top}" x2="{plot_left}" y2="{plot_bottom}" '
        f'stroke="black"/>',
        f'  <text x="20" y="{(plot_top + plot_bottom) / 2}" font-size="13" '
        f'font-family="sans-serif" transform="rotate(-90 20 {(plot_top + plot_bottom) / 2})" '
        f'text-anchor="middle">amplitude (uV)</text>',
        f'  <rect x="{x_control}" y="{plot_bottom - control_height}" width="{bar_width}" '
        f'height="{control_height}" fill="#4c78a8"/>',
        f'  <rect x="{x_treatment}" y="{plot_bottom - treatment_height}" width="{bar_width}" '
        f'height="{treatment_height}" fill="#f58518"/>',
        f'  <text x="{x_control + bar_width / 2}" y="{plot_bottom - control_height - 8}" '
        f'text-anchor="middle" font-size="13" font-family="sans-serif">'
        f'{result["control_mean_uv"]}</text>',
        f'  <text x="{x_treatment + bar_width / 2}" y="{plot_bottom - treatment_height - 8}" '
        f'text-anchor="middle" font-size="13" font-family="sans-serif">'
        f'{result["treatment_mean_uv"]}</text>',
        f'  <text x="{x_control + bar_width / 2}" y="{plot_bottom + 20}" '
        f'text-anchor="middle" font-size="13" font-family="sans-serif">control '
        f'(n={result["n_control"]})</text>',
        f'  <text x="{x_treatment + bar_width / 2}" y="{plot_bottom + 20}" '
        f'text-anchor="middle" font-size="13" font-family="sans-serif">treatment '
        f'(n={result["n_treatment"]})</text>',
        f'  <text x="{width / 2}" y="{height - 24}" text-anchor="middle" font-size="12" '
        f'font-family="sans-serif">{ci_text}</text>',
        "</svg>",
    ]
    return "\n".join(parts) + "\n"


def main() -> None:
    result = load_approved_result(RESULT_PATH)
    OUTPUT_PATH.write_text(render_svg(result), encoding="utf-8")
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
