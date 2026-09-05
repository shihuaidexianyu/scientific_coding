#!/usr/bin/env python3
"""Evaluation runner for the scientific-coding skill.

Turns evals/cases.toml from a specification into actual measurements:

    prompt -> captured trajectory + generated diff -> deterministic checks
    (+ optional rubric judge) -> comparable scores

Each case can run in three modes:

- explicit:  the prompt names the skill (tests rule compliance)
- implicit:  the bare prompt (tests whether the skill triggers and helps)
- baseline:  no project skill installed; ambient global skills are not isolated

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
import ast
import difflib
import concurrent.futures
import json
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
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
INSTALLED_SKILL_DIR = SKILL_DIR
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
    fixture = (SKILL_DIR / "examples/minimal_pipeline" if fixture_name == "minimal_pipeline"
               else FIXTURES_DIR / fixture_name if fixture_name else None)
    if fixture and fixture.is_dir():
        for item in fixture.iterdir():
            target = workdir / item.name
            if item.is_dir():
                if item.name != "__pycache__" and not (fixture_name == "minimal_pipeline" and item.name == "artifacts"):
                    shutil.copytree(item, target, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy2(item, target)
    else:
        (workdir / "SETUP.md").write_text(
            f"# Task setup\n\n{case.get('setup', '')}\n", encoding="utf-8"
        )

    if fixture_name == "scientific_review" and case.get("variant") == "packed_docs":
        path = workdir / "analysis.py"
        source = path.read_text(encoding="utf-8")
        packed = {
            "load_trials": "读取两张 CSV 并按 ID 连接。参数：raw_path : Path，振幅表；labels_path : Path，条件表。返回：rows : list[dict]，每行含 trial_id、condition、amplitude_uv。处理过程：1. 读取；2. 校验；3. 连接。副作用：读取文件。",
            "filter_trials": "根据阈值分组。参数：rows : list[dict]，已加载行；floor_uv : float，微伏阈值。返回：retained : list[dict]，大于等于阈值；excluded : list[dict]，小于阈值。处理过程：两次列表推导分别筛选。副作用：不修改输入。",
            "summarize": "按条件汇总。参数：rows : list[dict]，保留行。返回：result : dict，counts 是计数字典，means_uv 是均值字典，difference_uv 是 treatment 减 control。处理过程：分组、检查非空、求均值。副作用：不写文件。",
            "run": "运行研究。参数：config_path : Path，含 analysis.floor_uv 的 TOML 路径。返回：result : dict，包含 counts、means_uv、difference_uv。处理过程：读取配置，加载数据，筛选，汇总，写出。副作用：创建或覆盖 results 中两份结果。",
        }
        for node in reversed([item for item in ast.parse(source).body if isinstance(item, ast.FunctionDef)]):
            statement = node.body[0]
            lines = source.splitlines(keepends=True)
            lines[statement.lineno - 1:statement.end_lineno] = ['    """' + packed[node.name] + '"""\n']
            source = "".join(lines)
        path.write_text(source, encoding="utf-8")

    if mode != "baseline" and backend != "mock":
        if backend == "claude":

            # Claude Code discovers project skills under .claude/skills.
            skill_home = workdir / ".claude" / "skills" / "scientific-coding"
        else:

            # Codex discovers local skills under .agents/skills, searched
            # from the working directory upward.
            skill_home = workdir / ".agents" / "skills" / "scientific-coding"
        shutil.copytree(
            INSTALLED_SKILL_DIR,
            skill_home,
            ignore=shutil.ignore_patterns("results", "__pycache__", ".git", "artifacts"),
        )

    # A maintained source example replaces independent, drifting pipeline copies.
    if fixture_name == "minimal_pipeline":
        variant = case.get("variant")
        if variant == "unannotated":
            for path in [*workdir.glob("stages/*.py"), *workdir.glob("configs/*.toml")]:
                lines = path.read_text(encoding="utf-8").splitlines()
                path.write_text("\n".join(line for line in lines if not line.lstrip().startswith("#") or "scientific-code:" in line) + "\n", encoding="utf-8")
            (workdir / "README.md").write_text("Run: python pipeline.py\n", encoding="utf-8")
        elif variant == "redundant_checks":
            path = workdir / "stages/preprocess.py"
            source = path.read_text(encoding="utf-8")
            duplicate = '''    # Legacy defensive checks: acquisition or external entry already established these facts.
    if len({row["trial_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate trial identity")
    for row in rows:
        if not isinstance(row["amplitude_uv"], (int, float)) or not math.isfinite(row["amplitude_uv"]):
            raise ValueError("invalid amplitude")
        if row["condition"] not in ("control", "treatment"):
            raise ValueError("unknown condition")

'''
            source = source.replace("    # Partition the established", duplicate + "    # Partition the established")
            path.write_text(source, encoding="utf-8")
        if case.get("initial_run"):
            result = subprocess.run([sys.executable, "pipeline.py"], cwd=workdir,
                                    env=execution_env(), capture_output=True, text=True, encoding="utf-8")
            if result.returncode:
                raise RuntimeError("Fixture initial run failed: " + result.stdout + result.stderr)


def execution_env() -> dict[str, str]:
    """Expose the maintained artifact tools without copying execution secrets into evidence."""
    return {**os.environ, "SCIENTIFIC_CODING_SCRIPTS": str(SKILL_DIR / "scripts"),
            "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}


def artifact_snapshot(workdir: Path) -> dict[str, str]:
    return {p.relative_to(workdir).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (workdir / "artifacts").rglob("*") if p.is_file()}


def git(workdir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(workdir), *args], capture_output=True, text=True, encoding="utf-8"
    )


def snapshot_baseline(workdir: Path) -> bool:
    if git(workdir, "init", "-q").returncode != 0:
        return False
    git(workdir, "config", "user.email", "evals@example.com")
    git(workdir, "config", "user.name", "evals")

    # Running example stages writes bytecode into the workdir; keep it out
    # of the captured diff so the judge does not read it as agent output.
    ignore = workdir / ".gitignore"
    existing = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
    for entry in ("__pycache__/", "*.pyc"):
        if entry not in existing:
            existing += ("" if existing.endswith("\n") or not existing else "\n") + entry + "\n"
    ignore.write_text(existing, encoding="utf-8")
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
            "--output-format", "stream-json", "--verbose",
            "--dangerously-skip-permissions",  # fixture repos are disposable
        ]
    if backend == "codex":
        return ["codex", "exec", "--json", "--full-auto", "{prompt}"]
    raise ValueError(f"no agent command for backend {backend!r}")


def judge_command(backend: str) -> list[str]:
    """The judge receives evidence only; no tool execution or permission bypass."""
    if backend == "claude":
        return ["claude", "-p", "{prompt}", "--output-format", "json", "--tools", ""]
    if backend == "codex":
        return ["claude", "-p", "{prompt}", "--output-format", "json", "--tools", ""]
    raise ValueError("mock has no judge")


def run_agent(
    backend: str,
    prompt: str,
    workdir: Path,
    timeout: int,
    *, session_id: str | None = None, resume: bool = False,
) -> tuple[str, int, float]:
    """Return (trajectory text, returncode, seconds)."""
    if backend == "mock":
        return f"MOCK RUN — prompt recorded, no agent executed.\n\n{prompt}\n", 0, 0.0

    command = [part.replace("{prompt}", prompt) for part in agent_command(backend, prompt)]
    if session_id is not None:
        if backend != "claude":
            raise ValueError("These real resumed-session cases currently require the claude backend")
        command.extend(["--resume" if resume else "--session-id", session_id])
    env = execution_env()
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
            encoding="utf-8",
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        output = result.stdout + ("\n--- stderr ---\n" + result.stderr if result.stderr else "")
        returncode = result.returncode
    except subprocess.TimeoutExpired as error:
        partial = error.stdout or ""
        output = (partial.decode("utf-8", errors="replace") if isinstance(partial, bytes) else partial)
        partial_error = error.stderr or ""
        output += (partial_error.decode("utf-8", errors="replace") if isinstance(partial_error, bytes) else partial_error)
        output += f"\nTIMEOUT after {timeout}s"
        returncode = 124
    except OSError as error:
        output, returncode = f"INVOCATION FAILED: {error}", 127
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    return output, returncode, elapsed


def apply_review_update(workdir: Path) -> dict[str, Any]:
    """在两次真实用户轮次之间加入独立人工代码，并记录不可覆盖的精确内容。"""
    content = '''"""人工增加的结果注记模块。

接收主分析生成的摘要字典，不读取文件或 TOML。
返回带人工注记的新字典，调用者负责写入 results/summary.json。
"""

# 人工确定的注记原文需要保留。
USER_NOTE = "人工确认：阈值复核"


def annotate_summary(result: dict) -> dict:
    """为摘要添加人工注记，保留科学统计值。

    参数 result：包含 counts、means_uv 和 difference_uv 的摘要字典。

    处理逻辑：复制摘要，再加入 user_note 字段，不修改输入。

    返回：包含原有统计字段及字符串 user_note 的新字典；不写文件。
    """

    # 保持原摘要值并添加人工注记。
    return {**result, "user_note": USER_NOTE}
'''
    path = workdir / "manual_note.py"
    path.write_text(content, encoding="utf-8")
    analysis_path = workdir / "analysis.py"
    original = analysis_path.read_bytes()
    tree = ast.parse(original)
    function = next((node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "filter_trials"), None)
    if function is None:
        raise RuntimeError("Cannot inject the human boundary edit: public filter_trials function is absent")
    lines = original.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    replacements = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Compare) or len(node.ops) != 1:
            continue
        left_floor = isinstance(node.left, ast.Name) and node.left.id == "floor_uv"
        right_floor = isinstance(node.comparators[0], ast.Name) and node.comparators[0].id == "floor_uv"
        mapping = {ast.GtE: (b">=", b">"), ast.Lt: (b"<", b"<=")} if right_floor else {ast.LtE: (b"<=", b"<"), ast.Gt: (b">", b">=")}
        if not (left_floor or right_floor) or type(node.ops[0]) not in mapping:
            continue
        start = offsets[node.lineno - 1] + node.col_offset
        stop = offsets[node.end_lineno - 1] + node.end_col_offset
        segment = original[start:stop]
        old, new = mapping[type(node.ops[0])]
        if segment.count(old) != 1:
            raise RuntimeError("Cannot reliably identify the human comparison edit")
        replacements.append((start, stop, segment.replace(old, new, 1)))
    if not replacements:
        raise RuntimeError("No original inclusive comparison was found for the real human edit")
    updated = original
    for start, stop, content in sorted(replacements, reverse=True):
        updated = updated[:start] + content + updated[stop:]
    ast.parse(updated)
    analysis_path.write_bytes(updated)
    change = {"path": "analysis.py", "before_sha256": hashlib.sha256(original).hexdigest(),
              "after_sha256": hashlib.sha256(updated).hexdigest(), "comparison_edits": len(replacements),
              "diff": "".join(difflib.unified_diff(original.decode("utf-8").splitlines(keepends=True),
                                                  updated.decode("utf-8").splitlines(keepends=True),
                                                  fromfile="analysis.py before human edit", tofile="analysis.py after human edit"))}
    return {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "expected_user_note": "人工确认：阈值复核", "analysis_change": change}


def skill_triggered(trajectory: str) -> bool | None:
    """Report observed successful skill reads; prose mentions provide no evidence."""
    reads: set[str] = set()
    for line in trajectory.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        item = event.get("item", {})
        if (event.get("type") == "item.completed" and item.get("type") == "command_execution"
                and item.get("exit_code") == 0 and graders.is_skill_read(item.get("command", ""))):
            return True
        for block in event.get("message", {}).get("content", []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                args = block.get("input", {})
                requested = (block.get("name") == "Read" and "scientific-coding" in str(args.get("file_path", ""))
                             and str(args.get("file_path", "")).endswith("SKILL.md"))
                requested = requested or (block.get("name") == "Bash" and graders.is_skill_read(args.get("command", "")))
                requested = requested or (block.get("name") == "Skill" and args.get("skill") == "scientific-coding")
                if requested:
                    reads.add(block.get("id", ""))
            if block.get("type") == "tool_result" and block.get("tool_use_id") in reads and not block.get("is_error", False):
                return True
    return None


def invocation_failed(trajectory: str, returncode: int) -> bool:
    """A recoverable tool error is behavior evidence, not a provider outage."""
    if returncode != 0:
        return True
    for line in trajectory.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "result" and event.get("is_error") is True:
            return True
    return False


def observed_models(trajectory: str) -> list[str]:
    models: set[str] = set()
    for line in trajectory.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        model = event.get("model") or event.get("message", {}).get("model")
        if isinstance(model, str):
            models.add(model)
        if isinstance(event.get("modelUsage"), dict):
            models.update(event["modelUsage"])
    return sorted(models)


def observed_session_ids(trajectory: str) -> list[str]:
    """从 CLI 初始化和最终结果读取会话 ID，不以提示词里的 ID 充当续接证据。"""
    identities = set()
    for line in trajectory.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") in {"system", "result"} and isinstance(event.get("session_id"), str):
            identities.add(event["session_id"])
    return sorted(identities)


def run_linter(workdir: Path) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(LINTER), str(workdir), "--format", "json", "--full-artifact-checks"],
        capture_output=True,
        text=True,
        encoding="utf-8",
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
        before = artifact_snapshot(workdir)

        session_id = str(uuid.uuid4()) if case.get("followup_prompt") else None
        trajectory, returncode, elapsed = run_agent(backend, prompt, workdir, timeout, session_id=session_id)
        conversation = None
        if case.get("followup_prompt") and not invocation_failed(trajectory, returncode):
            first = run_dir / "turn1"
            first.mkdir()
            (first / "prompt.txt").write_text(prompt, encoding="utf-8")
            (first / "trajectory.txt").write_text(trajectory, encoding="utf-8")
            (first / "diff.txt").write_text(capture_diff(workdir), encoding="utf-8")
            shutil.copytree(workdir, first / "produced", ignore=shutil.ignore_patterns(".git", ".claude", ".agents", ".codex", "__pycache__"))
            first_outcomes = graders.review_study_outcome(workdir, strict=False, require_docs=False)
            old_test_code = first_outcomes["evidence"].get("independent_tests_returncode", -1)
            (first / "independent_tests.txt").write_text(first_outcomes["evidence"].get("independent_tests_output", "No successful first-round test evidence"), encoding="utf-8")
            first_ready = first_outcomes["pass"] and old_test_code == 0
            if case.get("require_successful_first_round") and not first_ready:
                conversation = {"kind": "first round incomplete; user change not injected",
                                "session_id": session_id, "first_outcomes": first_outcomes,
                                "first_tests_returncode": old_test_code,
                                "observed_first_session_ids": observed_session_ids(trajectory),
                                "turn_returncodes": [returncode]}
                (run_dir / "conversation.json").write_text(json.dumps(conversation, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                prior = workdir / "results_before_user_change"
                if (workdir / "results").is_dir():
                    shutil.copytree(workdir / "results", prior)
                previous_results = {path.relative_to(workdir).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                    for path in prior.rglob("*") if path.is_file()}
                manual = apply_review_update(workdir)
                (run_dir / "injected_human_diff.txt").write_text(manual["analysis_change"]["diff"], encoding="utf-8")
                followup = case.get("followup_prompt_zh", case["followup_prompt"]) if language == "zh" else case["followup_prompt"]
                (run_dir / "followup_prompt.txt").write_text(followup, encoding="utf-8")
                resumed, resumed_code, resumed_elapsed = run_agent(backend, followup, workdir, timeout, session_id=session_id, resume=True)
                (run_dir / "turn2_trajectory.txt").write_text(resumed, encoding="utf-8")
                conversation = {"kind": "real resumed CLI conversation" if backend != "mock" else "mock plumbing only",
                                "session_id": session_id, "first_outcomes": first_outcomes,
                                "first_tests_returncode": old_test_code, "manual_file": manual,
                                "previous_results": previous_results,
                                "followup_prompt": followup, "turn_returncodes": [returncode, resumed_code],
                                "observed_first_session_ids": observed_session_ids(trajectory),
                                "observed_second_session_ids": observed_session_ids(resumed),
                                "sequence": ["first agent turn", "first independent result checks", "first independent regression tests",
                                             "save previous results", "inject human-owned code", "send resumed user request", "second agent turn"]}
                (run_dir / "conversation.json").write_text(json.dumps(conversation, ensure_ascii=False, indent=2), encoding="utf-8")
                trajectory += "\n" + json.dumps({"type": "eval_user_followup", "text": followup}, ensure_ascii=False) + "\n" + resumed
                returncode = resumed_code
                elapsed += resumed_elapsed
        (run_dir / "trajectory.txt").write_text(trajectory, encoding="utf-8")

        diff_text = capture_diff(workdir) if has_git else "(git unavailable)"
        (run_dir / "diff.txt").write_text(diff_text, encoding="utf-8")

        lint_output = run_linter(workdir)
        (run_dir / "lint.json").write_text(
            json.dumps(lint_output, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        violations = graders.check_patterns(workdir, case.get("fail_if_patterns", []))
        outcomes = graders.outcome_checks(workdir, case, before, conversation=conversation)
        final_source = graders.source_evidence(workdir)
        if case.get("layout_spec"):
            execution = graders.execution_evidence(trajectory)
            (run_dir / "execution_evidence.json").write_text(json.dumps(execution, ensure_ascii=False, indent=2), encoding="utf-8")
        (run_dir / "source_evidence.json").write_text(json.dumps(final_source, ensure_ascii=False, indent=2), encoding="utf-8")
        (run_dir / "outcomes.json").write_text(json.dumps(outcomes, ensure_ascii=False, indent=2), encoding="utf-8")
        (run_dir / "initial_artifact_hashes.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
        shutil.copytree(workdir, run_dir / "produced", ignore=shutil.ignore_patterns(".git", ".claude", ".agents", ".codex", "__pycache__"))

    lint_info = graders.linter_summary(lint_output)

    # A run whose agent call failed at the API level (quota exhaustion,
    # provider 429/5xx) never executed the model; grading it as a real
    # failure pollutes every rate. Mark it invalid (pass=None) and skip
    # the rubric judge entirely.
    api_error = backend != "mock" and invocation_failed(trajectory, returncode)
    verdict: dict[str, Any] = {
        "deterministic_violations": violations,
        "linter": lint_info,
        "agent_returncode": returncode,
        "elapsed_s": round(elapsed, 1),
        "skill_triggered": skill_triggered(trajectory),
        "api_error": api_error,
        "outcomes": outcomes,
        "backend": backend,
        "requires_judge": case.get("requires_judge", True),
        "installed_skill": str(INSTALLED_SKILL_DIR) if mode != "baseline" else None,
        "observed_models": observed_models(trajectory),
        "baseline_isolation": "project skill omitted; ambient global skills and instructions are not isolated" if mode == "baseline" else None,
    }

    if use_judge and backend != "mock" and not api_error:
        env = dict(os.environ)
        if backend == "codex":

            # judge outside the fixture: use the ambient CODEX_HOME
            env.pop("CODEX_HOME", None)
        verdict["judge"] = graders.judge_case(
            judge_command(backend),
            case,
            diff_text,
            lint_info,
            trajectory,
            cwd=run_dir,
            env=env,
            outcomes=outcomes,
            final_source=final_source,
        )

    if case.get("layout_spec"):
        verdict["dimensions"] = graders.assessment_dimensions(outcomes, verdict.get("judge", {}))

    graders.decide_verdict(verdict, backend=backend, requires_judge=case.get("requires_judge", True))
    (run_dir / "verdict.json").write_text(
        json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return verdict


def summarize(records: list[dict[str, Any]], results_dir: Path) -> None:
    by_case: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_case.setdefault(record["case"], []).append(record)

    lines = ["# Evaluation summary", ""]
    lines.append("Only pass/fail runs enter the pass-rate denominator; unknown, invalid and mock smoke are separate. Triggered means an observed successful skill read, not a mention or proof of adoption.")
    limitations = []
    if any(record["mode"] == "baseline" for record in records):
        limitations.append("Baseline omits the project skill copy but does not isolate global skills or ambient instructions; it is not a proven no-skill control.")
        lines.extend(["", limitations[0]])
    lines.append("")
    lines.append("| case | mode | lang | runs | pass / assessed | unknown | invalid | smoke | linter errors | observed reads |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        key = (record["case"], record["mode"], record["language"])
        groups.setdefault(key, []).append(record)
    for (case_id, mode, language), group in sorted(groups.items()):
        passes = sum(1 for r in group if r["verdict"].get("pass"))
        invalid = sum(1 for r in group if r["verdict"].get("api_error"))
        invalid = sum(r["verdict"].get("status") == "invalid" for r in group)
        unknown = sum(r["verdict"].get("status") == "unknown" for r in group)
        smoke = sum(r["verdict"].get("status") == "smoke" for r in group)
        assessed = sum(type(r["verdict"].get("pass")) is bool for r in group)
        errors = sum(max(0, r["verdict"]["linter"]["errors"]) for r in group)
        triggered = sum(1 for r in group if r["verdict"].get("skill_triggered"))
        lines.append(
            f"| {case_id} | {mode} | {language} | {len(group)} "
            f"| {passes}/{assessed} | {unknown} | {invalid} | {smoke} | {errors} | {triggered} |"
        )

    # 新版式案例分开报告机械版式、科学结果、语义和格式器执行；历史组不追加标准。
    dimensions = ("layout", "science", "semantic_accuracy", "formatter_execution")

    def dimension_status(record: dict, name: str) -> str:
        verdict = record["verdict"]
        if verdict.get("status") in {"invalid", "smoke"}:
            return "unknown"
        value = verdict.get("dimensions", {}).get(name, {})
        if type(value.get("pass")) is bool:
            return "met" if value["pass"] else "unmet"
        return value.get("status", "unknown")

    if any(record["verdict"].get("dimensions") for record in records):
        lines += ["", "Dimension cells show met / assessed (unknown excluded); semantic and execution ratings remain model judgments.", "",
                  "| case | layout | science | semantic accuracy | formatter execution |",
                  "|---|---|---|---|---|"]
        for (case_id, mode, language), group in sorted(groups.items()):
            if not any(record["verdict"].get("dimensions") for record in group):
                continue
            cells = []
            for name in dimensions:
                statuses = [dimension_status(record, name) for record in group]
                cells.append(f"{statuses.count('met')}/{sum(status in {'met', 'unmet'} for status in statuses)} (unknown {statuses.count('unknown')})")
            lines.append(f"| {case_id} | " + " | ".join(cells) + " |")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "limitations": limitations,
        "runs": [
            {
                "case": r["case"],
                "mode": r["mode"],
                "language": r["language"],
                "repetition": r["repetition"],
                "pass": r["verdict"].get("pass"),
                "status": r["verdict"].get("status"),
                "api_error": r["verdict"].get("api_error"),
                "linter": r["verdict"]["linter"],
                "skill_triggered": r["verdict"].get("skill_triggered"),
                "deterministic_violations": r["verdict"]["deterministic_violations"],
                **({"dimensions": {name: dimension_status(r, name) for name in dimensions}}
                   if r["verdict"].get("dimensions") else {}),
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
    parser.add_argument("--skill-dir", default=None, help="Install another skill revision for controlled comparisons; graders remain current.")
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
    global INSTALLED_SKILL_DIR
    args = parse_args(argv)
    if args.skill_dir:
        INSTALLED_SKILL_DIR = Path(args.skill_dir).resolve()
        if not (INSTALLED_SKILL_DIR / "SKILL.md").is_file():
            raise ValueError("--skill-dir must contain SKILL.md")
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
        try:
            verdict = run_single(
                case, args.mode, args.language, args.backend, repetition,
                results_dir, args.timeout, args.judge,
            )
        except Exception as error:

            # One broken fixture must not erase evidence or cancel independent jobs.
            verdict = {"status": "invalid", "pass": None, "harness_error": f"{type(error).__name__}: {error}",
                       "linter": {"errors": -1}, "skill_triggered": None, "deterministic_violations": [],
                       "backend": args.backend}
            directory = results_dir / f"{case['id']}__{args.mode}__{args.language}__rep{repetition}"
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "verdict.json").write_text(json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8")
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
    failed = [r for r in records if not r["verdict"]["pass"] and r["verdict"].get("status") != "smoke"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
