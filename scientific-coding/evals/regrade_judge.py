#!/usr/bin/env python3
"""Re-grade completed eval runs with the LLM rubric judge, offline.

run_evals.py only invokes the judge when --judge is passed during the run.
This script retroactively grades every completed rep saved in one or more
results directories, using the artifacts each run wrote to disk
(prompt/diff/lint/verdict). Reps whose verdict.json already has a judge
result are skipped unless --regrade is given.

The judge is a plain one-shot `claude -p` call: it needs no tools and no
elevated permissions, unlike the agent runs being graded.

    python evals/regrade_judge.py evals/results/<batch> [--workers 8]
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
import tomllib
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import graders  # noqa: E402

JUDGE_COMMAND = ["claude", "-p", "{prompt}", "--output-format", "json"]


def load_cases(path: Path) -> dict[str, dict[str, Any]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return {case["id"]: case for case in data["case"]}


def rep_jobs(
    results_dirs: list[str], cases: dict[str, dict[str, Any]], skip_graded: bool
) -> Iterator[tuple[Path, dict[str, Any], dict[str, Any], Path]]:
    for raw_dir in results_dirs:
        root = Path(raw_dir)
        if not root.is_dir():
            print(f"warning: {root} not found, skipped", file=sys.stderr)
            continue
        for rep in sorted(root.iterdir()):
            if not rep.is_dir() or "__" not in rep.name:
                continue
            case_id = rep.name.split("__")[0]
            if case_id not in cases:
                continue
            if not (rep / "trajectory.txt").is_file() or not (rep / "diff.txt").is_file():
                continue
            verdict_path = rep / "verdict.json"
            if not verdict_path.is_file():
                continue  # rep still running or crashed mid-run
            verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
            if verdict.get("api_error"):
                continue  # the agent call never executed; nothing to grade
            trajectory_path = rep / "trajectory.txt"
            if "当前已达到" in trajectory_path.read_text(
                encoding="utf-8", errors="replace"
            ):
                continue  # provider quota freeze predates api_error marking
            if skip_graded and verdict.get("judge"):
                continue
            yield rep, cases[case_id], verdict, verdict_path


def grade(
    rep: Path,
    case: dict[str, Any],
    verdict: dict[str, Any],
    verdict_path: Path,
    timeout: int,
) -> tuple[str, dict[str, Any]]:
    lint_info = verdict.get("linter") or {}
    trajectory = (rep / "trajectory.txt").read_text(encoding="utf-8", errors="replace")
    diff_text = (rep / "diff.txt").read_text(encoding="utf-8", errors="replace")
    judge = graders.judge_case(
        JUDGE_COMMAND,
        case,
        diff_text,
        lint_info,
        trajectory,
        cwd=rep,
        timeout=timeout,
    )
    verdict["judge"] = judge
    judge_pass = judge.get("pass")
    verdict["pass"] = (not verdict.get("deterministic_violations")) and (
        judge_pass in (True, None)
    )
    verdict_path.write_text(
        json.dumps(verdict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return rep.name, judge


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_dirs", nargs="+")
    parser.add_argument(
        "--cases-toml",
        default=str(Path(__file__).resolve().parent / "cases.toml"),
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument(
        "--regrade",
        action="store_true",
        help="re-run the judge even where a judge verdict already exists",
    )
    args = parser.parse_args(argv)

    cases = load_cases(Path(args.cases_toml))
    jobs = list(rep_jobs(args.results_dirs, cases, skip_graded=not args.regrade))
    print(f"{len(jobs)} reps to grade with {args.workers} workers", flush=True)

    done = judge_fails = errors = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(grade, *job, args.timeout) for job in jobs]
        for future in concurrent.futures.as_completed(futures):
            name, judge = future.result()
            done += 1
            if judge.get("pass") is False:
                judge_fails += 1
            if judge.get("pass") is None:
                errors += 1
            print(
                f"[{done}/{len(jobs)}] {name} judge_pass={judge.get('pass')} "
                f"err={judge.get('error')}",
                flush=True,
            )
    print(f"graded {done}: judge-fail {judge_fails}, judge-error {errors}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
