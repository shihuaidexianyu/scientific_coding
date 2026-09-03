#!/usr/bin/env python3
"""Deterministic checks for human-auditable scientific pipelines.

The checks deliberately separate hard, mechanically testable violations from
heuristics that require researcher judgment. The script has no third-party
dependencies and is intended to run before a project's normal tests.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "evals",
    "node_modules",
    "site-packages",
    "templates",
    "test",
    "tests",
    "venv",
}
STAGE_DIRECTORIES = {"stage", "stages"}
VIEW_DIRECTORIES = {"explore", "figures", "plots", "reports", "tables", "views"}
GENERIC_MODULE_NAMES = {"common.py", "helpers.py", "misc.py", "utils.py"}
ABSTRACTION_NAME = re.compile(
    r"(Factory|Registry|Manager|Provider|Strategy|Adapter|BaseProcessor|"
    r"PipelineExecutor|Context|Plugin)$"
)
STAGE_STEM = re.compile(
    r"^(preprocess|feature|analysis|main_analysis|permutation|bootstrap|"
    r"evaluate|evaluation|experiment|model_evaluation)(?:_|$)"
)
VIEW_STEM = re.compile(r"^(figure|fig|plot|table|report)(?:_|$)")
SUPPRESSION = re.compile(
    r"^\s*#\s*scientific-code:\s*allow\s+(SC1\d{2})\s*--\s*(\S.*)$",
    re.MULTILINE,
)
BRANCH_KEYS = {
    "branch",
    "data_mode",
    "method",
    "mode",
    "pipeline",
    "preprocessing",
    "procedure",
    "representation",
}
MUTATING_METHODS = {
    "add",
    "append",
    "clear",
    "discard",
    "drop",
    "extend",
    "insert",
    "pop",
    "remove",
    "reverse",
    "setdefault",
    "sort",
    "update",
}
SCIENTIFIC_VERBS = {
    "aggregate",
    "align",
    "baseline",
    "bootstrap",
    "classify",
    "compute",
    "correct",
    "estimate",
    "evaluate",
    "extract",
    "filter",
    "fit",
    "normalize",
    "permutation",
    "remove",
    "resample",
    "rotate",
    "score",
    "select",
    "transform",
}
OPTIMIZATION_IMPORTS = {
    "concurrent",
    "cupy",
    "joblib",
    "multiprocessing",
    "numba",
    "triton",
}
NETWORK_PREFIXES = (
    "aiohttp.",
    "ftplib.",
    "http.client.",
    "httpx.",
    "paramiko.",
    "requests.",
    "socket.create_connection",
    "urllib.request.urlopen",
    "urlopen",
)


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    path: Path
    line: int
    message: str

    def serializable(self, root: Path) -> dict[str, Any]:
        try:
            display_path = self.path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            display_path = str(self.path)
        result = asdict(self)
        result["path"] = display_path
        return result


class IssueCollector:
    def __init__(self, root: Path, suppressions: dict[Path, dict[str, str]]) -> None:
        self.root = root
        self.suppressions = suppressions
        self.issues: list[Issue] = []

    def add(
        self,
        severity: str,
        code: str,
        path: Path,
        line: int,
        message: str,
    ) -> None:
        if severity == "warning" and code in self.suppressions.get(path, {}):
            return
        self.issues.append(Issue(severity, code, path, line, message))


def is_ignored(path: Path, root: Path) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        parts = path.parts
    return any(part in IGNORED_DIRECTORIES for part in parts)


def read_utf8(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def contains_marker(text: str, marker: str) -> bool:
    return bool(
        re.search(
            rf"^\s*#\s*scientific-code:\s*{re.escape(marker)}\s*$",
            text,
            re.MULTILINE,
        )
    )


def is_stage_file(path: Path, root: Path, text: str) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    lowered_parts = {part.lower() for part in relative.parts[:-1]}
    if lowered_parts & {"test", "tests", "template", "templates"}:
        return False
    return (
        bool(lowered_parts & STAGE_DIRECTORIES)
        or contains_marker(text, "stage")
        or (
            len(relative.parts) == 1
            and bool(STAGE_STEM.match(path.stem.lower()))
        )
    )


def is_view_file(path: Path, root: Path, text: str) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    lowered_parts = {part.lower() for part in relative.parts[:-1]}
    if lowered_parts & {"test", "tests", "template", "templates"}:
        return False
    return (
        bool(lowered_parts & VIEW_DIRECTORIES)
        or contains_marker(text, "view")
        or (
            len(relative.parts) == 1
            and bool(VIEW_STEM.match(path.stem.lower()))
        )
    )


def is_acquisition_stage(path: Path, text: str) -> bool:
    return (
        path.stem.lower().startswith(("acquire_", "download_", "fetch_"))
        or contains_marker(text, "acquisition-stage")
    )


def discover_python_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.py")
        if path.is_file() and not is_ignored(path, root)
    )


def git_changed_python_files(root: Path) -> set[Path] | None:
    commands = [
        ["git", "-C", str(root), "diff", "--name-only", "--diff-filter=ACMR", "HEAD", "--"],
        ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"],
    ]
    discovered: set[Path] = set()
    successful_command = False

    for command in commands:
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode != 0:
            continue
        successful_command = True
        for raw_path in result.stdout.splitlines():
            candidate = (root / raw_path.strip()).resolve()
            if candidate.suffix == ".py" and candidate.is_file():
                discovered.add(candidate)

    return discovered if successful_command else None


def module_name(path: Path, root: Path) -> str:
    try:
        relative = path.relative_to(root).with_suffix("")
    except ValueError:
        relative = path.with_suffix("")
    return ".".join(relative.parts)


def imported_stage(
    tree: ast.AST,
    current: Path,
    stage_files: Sequence[Path],
    root: Path,
) -> tuple[int, str] | None:
    stage_modules: set[str] = set()
    stage_stems: set[str] = set()

    for stage_path in stage_files:
        if stage_path.resolve() == current.resolve():
            continue
        name = module_name(stage_path, root)
        stage_modules.add(name)
        if name.startswith("src."):
            stage_modules.add(name[4:])
        stage_stems.add(stage_path.stem)

    def matches(name: str) -> bool:
        parts = name.split(".")
        return (
            "stages" in parts
            or name in stage_modules
            or name.removeprefix("src.") in stage_modules
            or (len(parts) == 1 and name in stage_stems)
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if matches(alias.name):
                    return node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom):
            imported_modules: list[str] = []
            if node.level:
                try:
                    package_parts = list(
                        current.relative_to(root).with_suffix("").parts[:-1]
                    )
                except ValueError:
                    package_parts = list(current.with_suffix("").parts[:-1])
                parents_to_remove = node.level - 1
                if parents_to_remove <= len(package_parts):
                    if parents_to_remove:
                        package_parts = package_parts[:-parents_to_remove]
                    module_parts = node.module.split(".") if node.module else []
                    base_parts = package_parts + module_parts
                    if node.module:
                        imported_modules.append(".".join(base_parts))
                    else:
                        imported_modules.extend(
                            ".".join(base_parts + [alias.name])
                            for alias in node.names
                        )
            elif node.module:
                imported_modules.append(node.module)

            for imported in imported_modules:
                if matches(imported):
                    return node.lineno, imported
    return None


def qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = qualified_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound_name = alias.asname or alias.name.split(".")[0]
                expanded_name = alias.name if alias.asname else bound_name
                aliases[bound_name] = expanded_name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return aliases


def expand_alias(name: str, aliases: dict[str, str]) -> str:
    first, separator, remainder = name.partition(".")
    replacement = aliases.get(first)
    if replacement is None:
        return name
    return replacement + (separator + remainder if separator else "")


def config_selector(node: ast.AST) -> str | None:
    if isinstance(node, ast.Attribute):
        base = qualified_name(node.value).split(".")[0]
        if base in {"cfg", "config", "settings"} and node.attr.lower() in BRANCH_KEYS:
            return f"{base}.{node.attr}"
    if isinstance(node, ast.Subscript):
        base = qualified_name(node.value).split(".")[0]
        key: str | None = None
        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            key = node.slice.value
        if base in {"cfg", "config", "settings"} and key in BRANCH_KEYS:
            return f"{base}[{key!r}]"
    return None


def find_hidden_branch(tree: ast.AST) -> tuple[int, str] | None:
    for node in ast.walk(tree):
        selector_node: ast.AST | None = None
        if isinstance(node, ast.If):
            selector_node = node.test
        elif isinstance(node, ast.Match):
            selector_node = node.subject
        if selector_node is None:
            continue
        for child in ast.walk(selector_node):
            selector = config_selector(child)
            if selector is not None:
                return node.lineno, selector
    return None


def cli_argument_lines(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = qualified_name(node.func)
        if name.endswith(".add_argument"):
            lines.append(node.lineno)
        elif name.endswith(".option") or name in {"typer.Option", "click.option"}:
            lines.append(node.lineno)
    return lines


def network_call(tree: ast.AST) -> tuple[int, str] | None:
    aliases = import_aliases(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = expand_alias(qualified_name(node.func), aliases)
        if name.startswith(NETWORK_PREFIXES):
            return node.lineno, name
        if any(
            name == prefix.removesuffix(".") or name.startswith(prefix)
            for prefix in NETWORK_PREFIXES
        ):
            return node.lineno, name
    return None


def has_checkpoint_machinery(tree: ast.AST) -> tuple[int, str] | None:
    pattern = re.compile(
        r"(checkpoint|resume|resumable|completed_shards|save_state|load_state)",
        re.IGNORECASE,
    )
    for node in ast.walk(tree):
        name = ""
        if isinstance(node, (ast.Name, ast.Attribute, ast.FunctionDef, ast.ClassDef)):
            name = getattr(node, "id", "") or getattr(node, "attr", "") or getattr(node, "name", "")
        if name and pattern.search(name):
            return getattr(node, "lineno", 1), name
    return None


def has_optimization_construct(tree: ast.AST) -> tuple[int, str] | None:
    aliases = import_aliases(tree)
    for alias, imported in aliases.items():
        if imported.split(".")[0] in OPTIMIZATION_IMPORTS:
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    return node.lineno, imported
            return 1, alias

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lowered = node.name.lower()
            if lowered.endswith(("_fast", "_optimized")) or lowered.startswith(("fast_", "optimized_")):
                return node.lineno, node.name
            for decorator in node.decorator_list:
                name = qualified_name(decorator.func if isinstance(decorator, ast.Call) else decorator)
                if name.endswith((".jit", ".njit", ".compile")) or name in {"jit", "njit"}:
                    return node.lineno, name
        elif isinstance(node, ast.Call):
            name = expand_alias(qualified_name(node.func), aliases)
            if name.endswith((".jit", ".njit", ".compile")):
                return node.lineno, name
    return None


def broad_exception(tree: ast.AST) -> tuple[int, str] | None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if node.type is None:
            return node.lineno, "bare except"
        caught = qualified_name(node.type)
        if caught in {"BaseException", "Exception"}:
            return node.lineno, caught
        if isinstance(node.type, ast.Tuple):
            names = {qualified_name(item) for item in node.type.elts}
            if names & {"BaseException", "Exception"}:
                return node.lineno, ", ".join(sorted(names))
    return None


def root_object_name(node: ast.AST) -> str | None:
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def function_parameters(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    arguments = function.args
    params = {
        arg.arg
        for arg in (
            list(arguments.posonlyargs)
            + list(arguments.args)
            + list(arguments.kwonlyargs)
        )
    }
    if arguments.vararg:
        params.add(arguments.vararg.arg)
    if arguments.kwarg:
        params.add(arguments.kwarg.arg)
    return params


def parameter_mutation(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[int, str] | None:
    params = function_parameters(function)
    for node in ast.walk(function):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            if isinstance(node, ast.Assign):
                targets = node.targets
            else:
                targets = [node.target]
            for target in targets:
                if isinstance(target, (ast.Attribute, ast.Subscript)):
                    root = root_object_name(target)
                    if root in params:
                        return node.lineno, root
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            root = root_object_name(node.func.value)
            if root in params and node.func.attr in MUTATING_METHODS:
                return node.lineno, root
            if root in params and any(
                keyword.arg == "inplace"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in node.keywords
            ):
                return node.lineno, root
    return None


def likely_scientific_function(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    if function.name.startswith("_") or function.name == "main":
        return False
    tokens = set(function.name.lower().split("_"))
    return bool(tokens & SCIENTIFIC_VERBS) and bool(function_parameters(function))


def missing_contract_sections(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[str]:
    doc = ast.get_docstring(function, clean=False) or ""
    lowered = doc.lower()
    checks = {
        "purpose": len(doc.strip()) >= 20,
        "input semantics": bool(re.search(r"\b(input|inputs|parameters)\b", lowered)),
        "transformation": bool(re.search(r"\b(processing|transformation|method|procedure)\b", lowered)),
        "output semantics": bool(re.search(r"\b(output|outputs|returns)\b", lowered)),
        "mutation/side effects": bool(re.search(r"\b(mutation|side effects?)\b", lowered)),
    }
    return [name for name, present in checks.items() if not present]


def warning_suppressions(text: str) -> dict[str, str]:
    return {match.group(1): match.group(2).strip() for match in SUPPRESSION.finditer(text)}


def find_files_named(root: Path, filename: str) -> list[Path]:
    return sorted(
        path
        for path in root.rglob(filename)
        if path.is_file() and not is_ignored(path, root)
    )


def is_under_artifact_root(path: Path, root: Path) -> bool:
    try:
        parts = {part.lower() for part in path.relative_to(root).parts}
    except ValueError:
        parts = {part.lower() for part in path.parts}
    return bool(parts & {"artifact", "artifacts"})


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def derived_artifact_hash(manifest: dict[str, Any]) -> str:
    files = manifest["files"]
    identity_files = {
        name: files[name]
        for name in sorted(manifest["identity_files"])
    }
    payload = {
        "schema_version": manifest.get("schema_version", 1),
        "contract": manifest.get("contract"),
        "identity_files": identity_files,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def derived_manifest_hash(manifest: dict[str, Any]) -> str:
    payload = {
        str(key): manifest[key]
        for key in sorted(manifest)
        if key != "manifest_hash"
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def stays_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def artifact_candidate_directories(root: Path) -> set[Path]:
    candidates: set[Path] = set()

    for path in find_files_named(root, "manifest.json"):
        if is_under_artifact_root(path, root) or (path.parent / "approval.json").is_file():
            candidates.add(path.parent)
            continue
        try:
            manifest = load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if (
            isinstance(manifest, dict)
            and isinstance(manifest.get("files"), dict)
            and "contract" in manifest
            and "artifact_hash" in manifest
        ):
            candidates.add(path.parent)

    for path in find_files_named(root, "approval.json"):
        if is_under_artifact_root(path, root) or (path.parent / "manifest.json").is_file():
            candidates.add(path.parent)

    for filename in ("run.json", "runtime.json"):
        for path in find_files_named(root, filename):
            if is_under_artifact_root(path, root):
                candidates.add(path.parent)
    return candidates


def optimization_report_targets(root: Path) -> set[str]:
    targets: set[str] = set()
    for report_path in find_files_named(root, "optimization_report.json"):
        try:
            report = load_json(report_path)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(report, dict) or not isinstance(report.get("stage"), str):
            continue
        stage = report["stage"].replace("\\", "/").strip().lower()
        targets.add(stage)
        targets.add(Path(stage).stem.lower())
        targets.add(stage.removesuffix(".py"))
    return targets


def optimization_report_covers(
    path: Path,
    root: Path,
    targets: set[str],
) -> bool:
    try:
        relative = path.relative_to(root).as_posix().lower()
    except ValueError:
        relative = path.as_posix().lower()
    candidates = {
        path.stem.lower(),
        relative,
        relative.removesuffix(".py"),
    }
    return bool(candidates & targets)


def check_artifacts(root: Path, collector: IssueCollector) -> None:
    candidates = artifact_candidate_directories(root)

    for artifact_dir in sorted(candidates):
        manifest_path = artifact_dir / "manifest.json"
        approval_path = artifact_dir / "approval.json"

        if not manifest_path.is_file():
            collector.add(
                "error",
                "SC004",
                artifact_dir,
                0,
                "Artifact candidate has no manifest.json.",
            )
            continue

        try:
            manifest = load_json(manifest_path)
        except (OSError, json.JSONDecodeError) as error:
            collector.add(
                "error",
                "SC004",
                manifest_path,
                0,
                f"Artifact manifest is unreadable: {error}.",
            )
            continue

        if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
            collector.add(
                "error",
                "SC004",
                manifest_path,
                0,
                "Artifact manifest must contain a files object.",
            )
            continue
        identity_files = manifest.get("identity_files")
        if (
            not isinstance(identity_files, list)
            or not identity_files
            or any(not isinstance(name, str) for name in identity_files)
            or any(name not in manifest["files"] for name in identity_files)
        ):
            collector.add(
                "error",
                "SC004",
                manifest_path,
                0,
                "Artifact manifest must list non-empty identity_files present in files.",
            )
            continue

        approval: dict[str, Any] | None = None
        if approval_path.is_file():
            try:
                loaded_approval = load_json(approval_path)
                if isinstance(loaded_approval, dict):
                    approval = loaded_approval
                else:
                    raise ValueError("approval root is not an object")
            except (OSError, json.JSONDecodeError, ValueError) as error:
                collector.add(
                    "error",
                    "SC003",
                    approval_path,
                    0,
                    f"Approval record is unreadable: {error}.",
                )

        approved = approval is not None and approval.get("status") == "approved"
        artifact_hash = derived_artifact_hash(manifest)
        manifest_hash = derived_manifest_hash(manifest)
        tracked_content_changed = False
        tracked_names = {str(name).replace("\\", "/") for name in manifest["files"]}

        for relative_name, expected_hash in sorted(manifest["files"].items()):
            tracked_path = artifact_dir / str(relative_name)
            if not stays_within(tracked_path, artifact_dir):
                if approved:
                    collector.add(
                        "error",
                        "SC007",
                        manifest_path,
                        0,
                        f"Tracked path escapes artifact directory: {relative_name!r}.",
                    )
                    tracked_content_changed = True
                continue
            if not tracked_path.is_file():
                if approved:
                    collector.add(
                        "error",
                        "SC007",
                        tracked_path,
                        0,
                        "Tracked artifact file is missing after approval.",
                    )
                    tracked_content_changed = True
                continue
            actual_hash = sha256_file(tracked_path)
            if actual_hash != expected_hash and approved:
                collector.add(
                    "error",
                    "SC007",
                    tracked_path,
                    0,
                    f"Tracked content changed after approval; expected {expected_hash}, got {actual_hash}.",
                )
                tracked_content_changed = True

        if approved:
            allowed_untracked = {"approval.json", "manifest.json"}
            for actual_path in sorted(artifact_dir.rglob("*")):
                if not actual_path.is_file():
                    continue
                relative_name = actual_path.relative_to(artifact_dir).as_posix()
                if relative_name not in tracked_names | allowed_untracked:
                    collector.add(
                        "error",
                        "SC007",
                        actual_path,
                        0,
                        "Untracked file was added to an approved artifact.",
                    )
                    tracked_content_changed = True

        if not approved:
            continue

        recorded_artifact_hash = manifest.get("artifact_hash")
        recorded_manifest_hash = manifest.get("manifest_hash")
        approval_artifact_hash = approval.get("artifact_hash") if approval else None
        approval_manifest_hash = approval.get("manifest_hash") if approval else None
        if (
            tracked_content_changed
            or recorded_artifact_hash != artifact_hash
            or recorded_manifest_hash != manifest_hash
            or approval_artifact_hash != artifact_hash
            or approval_manifest_hash != manifest_hash
        ):
            collector.add(
                "error",
                "SC003",
                approval_path if approval_path.is_file() else manifest_path,
                0,
                "Approved artifact/manifest hashes do not match canonical content and provenance.",
            )

    for run_path in find_files_named(root, "run.json"):
        try:
            run_record = load_json(run_path)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(run_record, dict):
            continue

        raw_inputs = run_record.get("input_artifacts", [])
        if not isinstance(raw_inputs, list):
            continue

        for item in raw_inputs:
            if isinstance(item, str):
                raw_path = item
                recorded_hash = None
            elif isinstance(item, dict):
                raw_path = item.get("path")
                recorded_hash = item.get("artifact_hash")
                recorded_manifest_hash = item.get("manifest_hash")
            else:
                continue
            if isinstance(item, str):
                recorded_manifest_hash = None
            if not isinstance(raw_path, str) or not raw_path:
                continue

            input_dir = Path(raw_path)
            if not input_dir.is_absolute():
                input_dir = root / input_dir

            approval_path = input_dir / "approval.json"
            manifest_path = input_dir / "manifest.json"
            try:
                approval = load_json(approval_path)
                manifest = load_json(manifest_path)
            except (OSError, json.JSONDecodeError):
                collector.add(
                    "error",
                    "SC005",
                    run_path,
                    0,
                    f"Input artifact {raw_path!r} lacks readable manifest/approval records.",
                )
                continue

            if (
                not isinstance(approval, dict)
                or approval.get("status") != "approved"
                or not isinstance(manifest, dict)
                or not isinstance(manifest.get("files"), dict)
                or not isinstance(manifest.get("identity_files"), list)
            ):
                collector.add(
                    "error",
                    "SC005",
                    run_path,
                    0,
                    f"Input artifact {raw_path!r} is not approved with a valid manifest.",
                )
                continue

            try:
                expected_hash = derived_artifact_hash(manifest)
                expected_manifest_hash = derived_manifest_hash(manifest)
            except (KeyError, TypeError):
                collector.add(
                    "error",
                    "SC005",
                    run_path,
                    0,
                    f"Input artifact {raw_path!r} has an invalid identity-file manifest.",
                )
                continue
            if (
                approval.get("artifact_hash") != expected_hash
                or manifest.get("artifact_hash") != expected_hash
                or approval.get("manifest_hash") != expected_manifest_hash
                or manifest.get("manifest_hash") != expected_manifest_hash
                or (recorded_hash is not None and recorded_hash != expected_hash)
                or (
                    recorded_manifest_hash is not None
                    and recorded_manifest_hash != expected_manifest_hash
                )
            ):
                collector.add(
                    "error",
                    "SC005",
                    run_path,
                    0,
                    f"Input artifact {raw_path!r} does not match the approved hash recorded by the run.",
                )


def analyze_python(
    path: Path,
    root: Path,
    text: str,
    tree: ast.AST,
    stage_files: Sequence[Path],
    optimization_targets: set[str],
    collector: IssueCollector,
) -> None:
    stage = is_stage_file(path, root, text)
    view = is_view_file(path, root, text)

    if stage:
        imported = imported_stage(tree, path, stage_files, root)
        if imported:
            line, name = imported
            collector.add(
                "error",
                "SC001",
                path,
                line,
                f"Stage imports stage implementation {name!r}; depend on its artifact contract instead.",
            )

        cli_lines = cli_argument_lines(tree)
        if len(cli_lines) > 2:
            collector.add(
                "error",
                "SC002",
                path,
                cli_lines[2],
                f"Stage defines {len(cli_lines)} CLI parameters; put scientific configuration in TOML.",
            )

        if not is_acquisition_stage(path, text):
            hidden_network = network_call(tree)
            if hidden_network:
                line, name = hidden_network
                collector.add(
                    "error",
                    "SC008",
                    path,
                    line,
                    f"Formal stage performs network call {name!r}; materialize network data in an acquisition artifact.",
                )

        branch = find_hidden_branch(tree)
        if branch:
            line, selector = branch
            collector.add(
                "warning",
                "SC101",
                path,
                line,
                f"Scientific procedure may be hidden behind {selector}; consider sibling stage files.",
            )

        checkpoint = has_checkpoint_machinery(tree)
        if checkpoint:
            line, name = checkpoint
            collector.add(
                "warning",
                "SC104",
                path,
                line,
                f"Checkpoint/resume machinery {name!r} needs restart-loss justification and resume equivalence.",
            )

        optimization = has_optimization_construct(tree)
        if optimization and not optimization_report_covers(
            path,
            root,
            optimization_targets,
        ):
            line, name = optimization
            collector.add(
                "warning",
                "SC105",
                path,
                line,
                f"Optimization construct {name!r} has no optimization_report.json with end-to-end evidence.",
            )

        for node in tree.body if isinstance(tree, ast.Module) else []:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            mutation = parameter_mutation(node)
            if mutation:
                line, parameter = mutation
                collector.add(
                    "warning",
                    "SC107",
                    path,
                    line,
                    f"Function {node.name!r} may mutate input parameter {parameter!r}, obscuring lineage.",
                )
            if likely_scientific_function(node):
                missing = missing_contract_sections(node)
                if missing:
                    collector.add(
                        "warning",
                        "SC108",
                        path,
                        node.lineno,
                        f"Likely scientific function {node.name!r} lacks contract content: {', '.join(missing)}.",
                    )

    if view:
        imported = imported_stage(tree, path, stage_files, root)
        if imported:
            line, name = imported
            collector.add(
                "error",
                "SC006",
                path,
                line,
                f"View imports stage implementation {name!r}; consume an approved artifact instead.",
            )

    if stage or view:
        caught = broad_exception(tree)
        if caught:
            line, name = caught
            collector.add(
                "warning",
                "SC106",
                path,
                line,
                f"Broad exception fallback ({name}) may hide a scientific or provenance failure.",
            )

    if path.name.lower() in GENERIC_MODULE_NAMES:
        collector.add(
            "warning",
            "SC103",
            path,
            1,
            "Generic utility module obscures ownership; keep logic local or name the stable concept.",
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and ABSTRACTION_NAME.search(node.name):
            collector.add(
                "warning",
                "SC102",
                path,
                node.lineno,
                f"Abstraction {node.name!r} needs a concrete scientific concept or demonstrated reuse boundary.",
            )


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scientific-code lint",
        description="Lint human-auditable scientific pipeline invariants.",
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Project root to inspect (default: current directory).",
    )
    parser.add_argument(
        "--changed-only",
        action="store_true",
        help="Analyze changed/untracked Python files when Git metadata is available.",
    )
    parser.add_argument(
        "--strict-warnings",
        action="store_true",
        help="Return a non-zero status when warnings remain.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--no-artifact-checks",
        action="store_true",
        help="Skip manifest, approval, and recorded-input integrity checks.",
    )
    return parser.parse_args(argv)


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"scientific-code lint: project root does not exist: {root}", file=sys.stderr)
        return 2

    all_python_files = discover_python_files(root)
    text_by_path: dict[Path, str] = {}
    parse_failures: list[tuple[Path, Exception]] = []

    for path in all_python_files:
        try:
            text_by_path[path] = read_utf8(path)
        except (OSError, UnicodeError) as error:
            parse_failures.append((path, error))

    suppressions = {
        path: warning_suppressions(text)
        for path, text in text_by_path.items()
    }
    collector = IssueCollector(root, suppressions)

    for path, error in parse_failures:
        collector.add(
            "error",
            "SC000",
            path,
            0,
            f"Python source could not be read: {error}.",
        )

    stage_files = [
        path
        for path, text in text_by_path.items()
        if is_stage_file(path, root, text)
    ]

    selected_files = set(text_by_path)
    if args.changed_only:
        changed = git_changed_python_files(root)
        if changed is not None:
            selected_files &= changed

    optimization_targets = optimization_report_targets(root)

    for path in sorted(selected_files):
        text = text_by_path[path]
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as error:
            collector.add(
                "error",
                "SC000",
                path,
                error.lineno or 0,
                f"Python source could not be parsed: {error.msg}.",
            )
            continue

        analyze_python(
            path,
            root,
            text,
            tree,
            stage_files,
            optimization_targets,
            collector,
        )

    if not args.no_artifact_checks:
        check_artifacts(root, collector)

    collector.issues.sort(
        key=lambda issue: (
            0 if issue.severity == "error" else 1,
            str(issue.path),
            issue.line,
            issue.code,
        )
    )
    errors = sum(issue.severity == "error" for issue in collector.issues)
    warnings = sum(issue.severity == "warning" for issue in collector.issues)

    if args.format == "json":
        print(
            json.dumps(
                {
                    "root": str(root),
                    "issues": [
                        issue.serializable(root)
                        for issue in collector.issues
                    ],
                    "summary": {
                        "errors": errors,
                        "warnings": warnings,
                        "checked_python_files": len(selected_files),
                        "artifact_checks": not args.no_artifact_checks,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for issue in collector.issues:
            serialized = issue.serializable(root)
            location = serialized["path"]
            if issue.line:
                location += f":{issue.line}"
            print(
                f"{issue.severity.upper()} {issue.code} "
                f"{location} — {issue.message}"
            )
        print(
            "scientific-code lint: "
            f"{errors} error(s), {warnings} warning(s), "
            f"{len(selected_files)} Python file(s) checked"
        )

    return 1 if errors or (args.strict_warnings and warnings) else 0


if __name__ == "__main__":
    raise SystemExit(run())
