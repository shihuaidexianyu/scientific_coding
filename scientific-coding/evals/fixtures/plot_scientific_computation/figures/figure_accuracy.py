"""Figure: decoding accuracy by subject.

Consumes the approved AnalysisResultV1 artifact. Presentation only.
"""

from pathlib import Path


def main() -> None:
    text = Path("artifacts/analysis_result/run_001/accuracy_by_subject.csv").read_text(
        encoding="utf-8"
    )
    # (plotting omitted in the fixture)
    print(text)


if __name__ == "__main__":
    main()
