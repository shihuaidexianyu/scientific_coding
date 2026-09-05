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
import run_evals

JUDGE_COMMAND = ["claude", "-p", "{prompt}", "--output-format", "json", "--tools", ""]


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
            trajectory_path = rep / "trajectory.txt"
            trajectory = trajectory_path.read_text(encoding="utf-8", errors="replace")

            # Older runs treated any failed tool as an API outage. Recover their
            # assessable evidence using the final CLI result, then refresh the verdict.
            if verdict.get("status") == "smoke" or verdict.get("backend") == "mock":
                continue
            verdict["api_error"] = run_evals.invocation_failed(trajectory, verdict.get("agent_returncode", 0))
            verdict["skill_triggered"] = run_evals.skill_triggered(trajectory)
            graders.decide_verdict(verdict, backend=verdict.get("backend", "claude"), requires_judge=cases[case_id].get("requires_judge", True))
            verdict_path.write_text(json.dumps(verdict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if verdict["api_error"] or verdict.get("harness_error"):
                continue
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
    final_source = None
    produced = rep / "produced"
    if produced.is_dir():
        final_source = graders.source_evidence(produced)
        (rep / "source_evidence.json").write_text(json.dumps(final_source, ensure_ascii=False, indent=2), encoding="utf-8")
        lint = run_evals.run_linter(produced)
        lint_info = graders.linter_summary(lint)
        verdict["linter"] = lint_info
        (rep / "lint.json").write_text(json.dumps(lint, ensure_ascii=False, indent=2), encoding="utf-8")
        snapshot = rep / "initial_artifact_hashes.json"
        before = json.loads(snapshot.read_text(encoding="utf-8")) if snapshot.is_file() else {}
        conversation_path = rep / "conversation.json"
        conversation = json.loads(conversation_path.read_text(encoding="utf-8")) if conversation_path.is_file() else None
        verdict["outcomes"] = graders.outcome_checks(produced, case, before, conversation=conversation)
        verdict["deterministic_violations"] = graders.check_patterns(produced, case.get("fail_if_patterns", []))
        (rep / "outcomes.json").write_text(json.dumps(verdict["outcomes"], ensure_ascii=False, indent=2), encoding="utf-8")
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
        outcomes=verdict.get("outcomes"),
        final_source=final_source,
    )
    verdict["judge"] = judge
    if case.get("layout_spec"):
        verdict["dimensions"] = graders.assessment_dimensions(verdict.get("outcomes", {}), judge)
    graders.decide_verdict(verdict, backend=verdict.get("backend", "claude"), requires_judge=case.get("requires_judge", True))
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
    for raw_root in args.results_dirs:
        root = Path(raw_root)
        records = []
        for path in root.glob("*__*/verdict.json"):
            parts = path.parent.name.split("__")
            if len(parts) == 4:
                records.append({"case": parts[0], "mode": parts[1], "language": parts[2],
                                "repetition": int(parts[3].removeprefix("rep")),
                                "verdict": json.loads(path.read_text(encoding="utf-8"))})
        if records:
            run_evals.summarize(records, root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
