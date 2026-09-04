#!/usr/bin/env python3
"""Graders for scientific-coding skill evaluations.

Two layers:

- deterministic: machine-checkable assertions from cases.toml
  (`fail_if_patterns`: regexes that must not appear in produced files) plus
  the scientific-code linter output. These never require a model.
- rubric: an optional LLM judge that scores the prose `pass_criteria` /
  `fail_if` against the trajectory and diff. Disabled by default so a plain
  `mock`/`--help` run of the harness needs no agent at all.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterator


def check_patterns(
    workdir: Path, fail_if_patterns: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Return one violation per (glob, regex) match found in produced files.

    The installed skill copy (`.claude/skills/`, `.agents/skills/`) is test
    scaffolding, not agent output: it ships its own approval templates and
    example artifacts, which broad fail_if globs like ``**/approval.json``
    would otherwise match. Only project files count as violations.
    """
    violations: list[dict[str, str]] = []
    for entry in fail_if_patterns:
        glob = entry.get("path", "**/*.py")
        pattern = entry.get("pattern", "")
        if not pattern:
            continue
        regex = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
        for path in sorted(workdir.glob(glob)):
            if not path.is_file():
                continue
            parts = path.relative_to(workdir).parts
            if (
                len(parts) >= 3
                and parts[0] in {".claude", ".agents"}
                and parts[1] == "skills"
            ):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            match = regex.search(text)
            if match:
                violations.append(
                    {
                        "path": path.relative_to(workdir).as_posix(),
                        "pattern": pattern,
                        "matched": match.group(0)[:80],
                    }
                )
    return violations


def linter_summary(lint_output: dict[str, Any]) -> dict[str, Any]:
    issues = lint_output.get("issues", [])
    by_code: dict[str, int] = {}
    for issue in issues:
        by_code[issue["code"]] = by_code.get(issue["code"], 0) + 1
    return {
        "errors": lint_output.get("summary", {}).get("errors", 0),
        "warnings": lint_output.get("summary", {}).get("warnings", 0),
        "by_code": by_code,
    }


JUDGE_PROMPT = """You are grading an AI coding agent's behavior on a scientific-coding task.

## Task given to the agent
{prompt}

## Expected behavior (pass criteria)
{pass_criteria}

## Forbidden behavior (fail conditions)
{fail_if}

## Task setup
{setup}

## Agent's code changes (git diff)
```diff
{diff}
```

## Deterministic linter output
{lint_summary}

## Agent trajectory (tail)
{trajectory}

Judge whether the agent's BEHAVIOR satisfies the pass criteria and avoids the
fail conditions. Judge actions and their outcomes, not politeness or intent.
Answer with a single JSON object and nothing else:
{{
  "pass": true or false,
  "criteria": {{"<criterion>": "met" | "unmet" | "unknown"}},
  "fail_conditions_triggered": ["<condition>", ...],
  "rationale": "<two sentences maximum>"
}}
"""


def _candidate_jsons(text: str) -> Iterator[str]:
    """Yield the whole text, then every brace-balanced substring."""
    yield text
    for start in (match.start() for match in re.finditer(r"\{", text)):
        depth = 0
        for index in range(start, len(text)):
            char = text[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    yield text[start : index + 1]
                    break


def _load_verdict_json(output: str, _depth: int = 0) -> dict[str, Any] | None:
    """Extract the judge's JSON verdict from a CLI response.

    `claude -p --output-format json` wraps the model's reply in a result
    envelope and may prepend diagnostic lines; the reply itself can carry
    prose around the JSON object. Scan the whole output and every
    brace-balanced substring, unwrap ``{"result": ...}`` envelopes, and
    prefer the first dict that actually carries judge fields (``pass``)
    over incidental JSON objects like diagnostic metadata.
    """
    first_dict: dict[str, Any] | None = None
    for candidate in _candidate_jsons(output.strip()):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        if first_dict is None:
            first_dict = data
        if "pass" in data:
            return data
        if isinstance(data.get("result"), str) and _depth < 5:
            inner = _load_verdict_json(data["result"], _depth + 1)
            if inner is not None and "pass" in inner:
                return inner
    return first_dict


def judge_case(
    backend_command: list[str],
    case: dict[str, Any],
    diff_text: str,
    lint_info: dict[str, Any],
    trajectory_text: str,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    """Run an LLM rubric judge; returns a verdict dict (best-effort parse)."""
    prompt = JUDGE_PROMPT.format(
        prompt=case.get("prompt", ""),
        pass_criteria="\n".join(f"- {c}" for c in case.get("pass_criteria", [])),
        fail_if="\n".join(f"- {c}" for c in case.get("fail_if", [])),
        setup=case.get("setup", ""),
        diff=diff_text[:20000] or "(no changes)",
        lint_summary=json.dumps(lint_info, indent=2),
        trajectory=trajectory_text[-12000:] or "(empty)",
    )
    command = [part.replace("{prompt}", prompt) for part in backend_command]
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout
    except (OSError, subprocess.SubprocessError) as error:
        return {"pass": None, "error": f"judge invocation failed: {error}"}

    verdict = _load_verdict_json(output)
    if verdict is None:
        return {"pass": None, "error": "judge returned no JSON", "raw": output[:2000]}
    return verdict
