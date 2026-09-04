#!/usr/bin/env python3
"""Evaluation runner for the scientific-coding skill.

Turns evals/cases.toml from a specification into actual measurements:

    prompt -> captured trajectory + generated diff -> deterministic checks
    (+ optional rubric judge) -> comparable scores

Each case can run in three modes:

- explicit:  the prompt names the skill (tests rule compliance)
- implicit:  the bare prompt (tests whether the skill triggers and helps)
- baseline:  no skill installed (negative control / delta measurement)

Backends:

    --backend mock     no agent; validates the harness plumbing end to end
    --backend claude   `claude -p` in a throwaway fixture repo
    --backend codex    `codex exec --json --full-auto` with CODEX_HOME set

Examples:

    python evals/run_evals.py --backend mock --mode explicit
    python evals/run_evals.py --backend claude --mode explicit --repetitions 3
    python evals/run_evals.py --backend codex --mode implicit --language zh --judge
    python evals/run_evals.py --backend claude --mode baseline --cases bad_parallelism

Results land in evals/results/<timestamp>/ with the full trajectory, diff,
linter output, and verdict per run, plus an aggregate summary.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # Python < 3.11
    print("run_evals.py requires Python 3.11+ (tomllib)", file=sys.stderr)
    raise SystemExit(2)

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import graders

EVALS_DIR = Path(__file__).resolve().parent
SKILL_DIR = EVALS_DIR.parent
FIXTURES_DIR = EVALS_DIR / "fixtures"
LINTER = SKILL_DIR / "scripts" / "scientific_code_lint.py"


def load_cases() -> dict[str, Any]:
    with (EVALS_DIR / "cases.toml").open("rb") as stream:
        return tomllib.load(stream)


def select_prompt(case: dict[str, Any], language: str) -> str:
    if language == "zh" and case.get("prompt_zh"):
        return case["prompt_zh"]
    return case["prompt"]


def build_invocation(
    case: dict[str, Any], mode: str, language: str, backend: str
) -> str:
    prompt = select_prompt(case, language)
    if mode != "explicit":
        return prompt
    if backend == "codex":
        return f"Use $scientific-coding for this task: {prompt}"
    return f"Use the scientific-coding skill for this task: {prompt}"


def materialize_repo(case: dict[str, Any], workdir: Path, mode: str, backend: str) -> None:
    fixture_name = case.get("fixture")
    fixture = FIXTURES_DIR / fixture_name if fixture_name else None
    if fixture and fixture.is_dir():
        for item in fixture.iterdir():
            target = workdir / item.name
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
    else:
        (workdir / "SETUP.md").write_text(
            f"# Task setup\n\n{case.get('setup', '')}\n", encoding="utf-8"
        )

    if mode != "baseline" and backend != "mock":
        if backend == "claude":
            # Claude Code discovers project skills under .claude/skills.
            skill_home = workdir / ".claude" / "skills" / "scientific-coding"
        else:
            # Codex discovers local skills under .agents/skills, searched
            # from the working directory upward.
            skill_home = workdir / ".agents" / "skills" / "scientific-coding"
        shutil.copytree(
            SKILL_DIR,
            skill_home,
            ignore=shutil.ignore_patterns("results", "__pycache__", ".git"),
        )


def git(workdir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(workdir), *args], capture_output=True, text=True
    )


def snapshot_baseline(workdir: Path) -> bool:
    if git(workdir, "init", "-q").returncode != 0:
        return False
    git(workdir, "config", "user.email", "evals@example.com")
    git(workdir, "config", "user.name", "evals")
    git(workdir, "add", "-A")
    return git(workdir, "commit", "-q", "-m", "baseline", "--allow-empty").returncode == 0


def capture_diff(workdir: Path) -> str:
    git(workdir, "add", "-A")
    result = git(workdir, "diff", "--cached")
    return result.stdout


def agent_command(backend: str, prompt: str) -> list[str]:
    if backend == "claude":
        return [
            "claude", "-p", "{prompt}",
            "--output-format", "json",
            "--dangerously-skip-permissions",  # fixture repos are disposable
        ]
    if backend == "codex":
        return ["codex", "exec", "--json", "--full-auto", "{prompt}"]
    raise ValueError(f"no agent command for backend {backend!r}")


def run_agent(
    backend: str,
    prompt: str,
    workdir: Path,
    timeout: int,
) -> tuple[str, int, float]:
    """Return (trajectory text, returncode, seconds)."""
    if backend == "mock":
        return f"MOCK RUN — prompt recorded, no agent executed.\n\n{prompt}\n", 0, 0.0

    command = [part.replace("{prompt}", prompt) for part in agent_command(backend, prompt)]
    env = dict(os.environ)
    if backend == "codex":
        env["CODEX_HOME"] = str(workdir / ".codex")

    started = datetime.now(timezone.utc)
    try:
        result = subprocess.run(
            command,
            cwd=workdir,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + ("\n--- stderr ---\n" + result.stderr if result.stderr else "")
        returncode = result.returncode
    except subprocess.TimeoutExpired:
        output, returncode = f"TIMEOUT after {timeout}s", 124
    except OSError as error:
        output, returncode = f"INVOCATION FAILED: {error}", 127
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    return output, returncode, elapsed


def skill_triggered(trajectory: str) -> bool:
    return "scientific-coding" in trajectory or "scientific_coding" in trajectory


def run_linter(workdir: Path) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(LINTER), str(workdir), "--format", "json"],
        capture_output=True,
        text=True,
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"issues": [], "summary": {"errors": -1}, "raw": result.stdout[:2000]}


def run_single(
    case: dict[str, Any],
    mode: str,
    language: str,
    backend: str,
    repetition: int,
    results_dir: Path,
    timeout: int,
    use_judge: bool,
) -> dict[str, Any]:
    run_name = f"{case['id']}__{mode}__{language}__rep{repetition}"
    run_dir = results_dir / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    prompt = build_invocation(case, mode, language, backend)
    (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        materialize_repo(case, workdir, mode, backend)
        has_git = snapshot_baseline(workdir)

        trajectory, returncode, elapsed = run_agent(backend, prompt, workdir, timeout)
        (run_dir / "trajectory.txt").write_text(trajectory, encoding="utf-8")

        diff_text = capture_diff(workdir) if has_git else "(git unavailable)"
        (run_dir / "diff.txt").write_text(diff_text, encoding="utf-8")

        lint_output = run_linter(workdir)
        (run_dir / "lint.json").write_text(
            json.dumps(lint_output, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        violations = graders.check_patterns(workdir, case.get("fail_if_patterns", []))

    lint_info = graders.linter_summary(lint_output)
    verdict: dict[str, Any] = {
        "deterministic_violations": violations,
        "linter": lint_info,
        "agent_returncode": returncode,
        "elapsed_s": round(elapsed, 1),
        "skill_triggered": skill_triggered(trajectory),
    }

    if use_judge and backend != "mock":
        env = dict(os.environ)
        if backend == "codex":
            # judge outside the fixture: use the ambient CODEX_HOME
            env.pop("CODEX_HOME", None)
        verdict["judge"] = graders.judge_case(
            agent_command(backend, "{prompt}"),
            case,
            diff_text,
            lint_info,
            trajectory,
            cwd=Path.cwd(),
            env=env,
        )

    deterministic_pass = not violations
    judge_pass = verdict.get("judge", {}).get("pass")
    verdict["pass"] = deterministic_pass and (judge_pass in (True, None))
    (run_dir / "verdict.json").write_text(
        json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return verdict


def summarize(records: list[dict[str, Any]], results_dir: Path) -> None:
    by_case: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_case.setdefault(record["case"], []).append(record)

    lines = ["# Evaluation summary", ""]
    lines.append("| case | mode | lang | runs | pass rate | linter errors | triggered |")
    lines.append("|---|---|---|---|---|---|---|")
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        key = (record["case"], record["mode"], record["language"])
        groups.setdefault(key, []).append(record)
    for (case_id, mode, language), group in sorted(groups.items()):
        passes = sum(1 for r in group if r["verdict"].get("pass"))
        errors = sum(r["verdict"]["linter"]["errors"] for r in group)
        triggered = sum(1 for r in group if r["verdict"].get("skill_triggered"))
        lines.append(
            f"| {case_id} | {mode} | {language} | {len(group)} "
            f"| {passes}/{len(group)} | {errors} | {triggered}/{len(group)} |"
        )

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runs": [
            {
                "case": r["case"],
                "mode": r["mode"],
                "language": r["language"],
                "repetition": r["repetition"],
                "pass": r["verdict"].get("pass"),
                "linter": r["verdict"]["linter"],
                "skill_triggered": r["verdict"].get("skill_triggered"),
                "deterministic_violations": r["verdict"]["deterministic_violations"],
            }
            for r in records
        ],
    }
    (results_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (results_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="run_evals")
    parser.add_argument(
        "--backend",
        choices=("mock", "claude", "codex"),
        default="mock",
        help="Agent backend. mock runs no agent and validates the harness.",
    )
    parser.add_argument(
        "--mode",
        choices=("explicit", "implicit", "baseline"),
        default="explicit",
    )
    parser.add_argument("--cases", default=None, help="Comma-separated case ids.")
    parser.add_argument("--repetitions", type=int, default=None)
    parser.add_argument("--language", choices=("en", "zh"), default="en")
    parser.add_argument(
        "--judge",
        action="store_true",
        help="Add an LLM rubric judge (uses the selected backend; costs tokens).",
    )
    parser.add_argument("--timeout", type=int, default=900, help="Per-run seconds.")
    parser.add_argument("--results-dir", default=None)
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Run this many case/repetition jobs concurrently. Each job gets "
        "its own throwaway repo, so runs are independent; watch your API "
        "provider's rate limits before raising this.",
    )
    parser.add_argument("--list", action="store_true", help="List cases and exit.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_cases()
    cases = config["case"]
    if args.cases:
        wanted = set(args.cases.split(","))
        cases = [case for case in cases if case["id"] in wanted]
    if args.list:
        for case in cases:
            fixture = case.get("fixture", "(prose setup)")
            print(f"{case['id']:28s} {case['task_class']:22s} fixture={fixture}")
        return 0
    if not cases:
        print("no cases selected", file=sys.stderr)
        return 2

    repetitions = args.repetitions or config.get("default_repetitions", 1)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    results_dir = (
        Path(args.results_dir)
        if args.results_dir
        else EVALS_DIR / "results" / timestamp
    )
    results_dir.mkdir(parents=True, exist_ok=True)

    def execute(case: dict[str, Any], repetition: int) -> dict[str, Any]:
        verdict = run_single(
            case,
            args.mode,
            args.language,
            args.backend,
            repetition,
            results_dir,
            args.timeout,
            args.judge,
        )
        return {
            "case": case["id"],
            "mode": args.mode,
            "language": args.language,
            "repetition": repetition,
            "verdict": verdict,
        }

    def report(record: dict[str, Any]) -> None:
        verdict = record["verdict"]
        print(
            f"[{record['case']} rep{record['repetition']}/{repetitions} "
            f"{record['mode']}/{record['language']}/{args.backend}] "
            f"-> pass={verdict['pass']} "
            f"lint_errors={verdict['linter']['errors']} "
            f"triggered={verdict['skill_triggered']}",
            flush=True,
        )

    jobs = [(case, rep) for case in cases for rep in range(1, repetitions + 1)]
    records: list[dict[str, Any]] = []
    if args.workers > 1:
        print(f"running {len(jobs)} jobs with {args.workers} workers", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [
                pool.submit(execute, case, rep) for case, rep in jobs
            ]
            for future in concurrent.futures.as_completed(futures):
                record = future.result()
                records.append(record)
                report(record)
    else:
        for case, rep in jobs:
            print(
                f"[{case['id']} rep{rep}/{repetitions} "
                f"{args.mode}/{args.language}/{args.backend}]",
                flush=True,
            )
            record = execute(case, rep)
            records.append(record)
            report(record)

    records.sort(key=lambda r: (r["case"], r["repetition"]))

    summarize(records, results_dir)
    print(f"\nresults: {results_dir}")
    failed = [r for r in records if not r["verdict"]["pass"]]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
