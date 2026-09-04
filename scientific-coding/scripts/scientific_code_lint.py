#!/usr/bin/env python3
"""Deterministic checks for human-auditable scientific pipelines.

The checks deliberately separate hard, mechanically testable violations from
heuristics that require researcher judgment. The script has no third-party
dependencies and is intended to run before a project's normal tests.

A project may declare directory roles in a root-level scientific-code.toml:

    [scope]
    stage_roots = ["stages", "analysis"]
    view_roots = ["figures", "views"]
    artifact_roots = ["artifacts"]
    infrastructure_roots = ["src", "infra"]

Files under stage/view roots are always treated as pipeline code; files under
infrastructure roots are exempt from naming-discipline heuristics, matching
the scope gate in SKILL.md.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import re
import subprocess
import sys
import tokenize
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    import tomllib
except ImportError:  # Python < 3.11: project scope config is unavailable
    tomllib = None


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
VIEW_SCIENTIFIC_COMPUTATION = re.compile(
    r"\b(?:bootstrap\w*|jackknife|permutation[_ ]?test|outlier\w*|percentile|"
    r"confidence[_ ]interval|confint|normaliz\w+|standardiz\w+|z[_ -]?scores?|"
    r"p[_ -]?values?|benjamini|bonferroni|false[_ ]discovery|"
    r"linear_regression|logistic_regression|fit_transform)|\.fit\("
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

# CLI argument names that look like scientific parameters rather than
# operational flags. Used to decide whether a large CLI surface is a hard
# error (scientific parameters exposed) or a warning (merely busy).
SCIENTIFIC_ARG_NAME = re.compile(
    r"^(alpha|beta|sigma|gamma|lambda_|epsilon|tol|tolerance|seed|split|"
    r"fold|folds|window|threshold|cutoff|normalization|normalize|baseline|"
    r"method|mode|freq|frequency|sampling_rate|epoch|epochs|permutation|"
    r"permutations|n_permutations|bootstrap|n_bootstrap|smoothing|filter|"
    r"n_components|regularization|min_.+|max_.+|.+_ms|.+_hz)$",
    re.IGNORECASE,
)

# Docstring contract sections accept NumPy (Parameters/Returns), Google
# (Args/Returns), Sphinx (:param:) and Chinese headings, so that a genuine
# contract is not flagged merely for its documentation style or language.
DOCSTRING_PATTERNS = {
    "input semantics": re.compile(
        r"\b(inputs?|parameters?|args|arguments)\b|:param|输入|参数",
        re.IGNORECASE,
    ),
    "transformation": re.compile(
        r"\b(processing|transformation|transforms?|method|procedure|"
        r"algorithm|steps?|approach|computes?|calculates?)\b|"
        r"变换|转换|算法|方法|流程|步骤|处理",
        re.IGNORECASE,
    ),
    "output semantics": re.compile(
        r"\b(outputs?|returns?|yields)\b|:returns?:|输出|返回",
        re.IGNORECASE,
    ),
    "mutation/side effects": re.compile(
        r"\b(mutations?|side[ -]?effects?|in[ -]?place|mutates?|modifies|"
        r"modifying)\b|副作用|就地|原地|不修改|无修改",
        re.IGNORECASE,
    ),
}

# Template prose that indicates an optimization report was copied verbatim
# instead of being filled with real measurements.
PLACEHOLDER_TEXT = re.compile(
    r"^\s*(describe\b|state\s+the\b|todo\b|record\s)", re.IGNORECASE
)


@dataclass(frozen=True)
class ScopeConfig:
    """Project-declared directory roles from scientific-code.toml."""

    stage_roots: tuple[str, ...] = ()
    view_roots: tuple[str, ...] = ()
    artifact_roots: tuple[str, ...] = ()
    infrastructure_roots: tuple[str, ...] = ()


def load_scope_config(root: Path) -> ScopeConfig:
    config_path = root / "scientific-code.toml"
    if not config_path.is_file():
        # A monorepo may nest self-contained scientific projects (each with
        # its own scientific-code.toml) under an outer root that has none.
        # Scope checks then classify by file content alone, which mislabels
        # nested stages. Fall back to the nearest scientific-code.toml in any
        # descendant directory so nested projects keep their own scope.
        candidates = sorted(
            path
            for path in root.rglob("scientific-code.toml")
            if path.is_file() and not is_ignored(path, root)
        )
        if candidates:
            return load_scope_config(candidates[0].parent)
        return ScopeConfig()
    config: ScopeConfig = _parse_scope_config(config_path)
    if config != ScopeConfig():
        return config
    # The root config exists but declares nothing usable; still allow a
    # nested project config to take over, for the same monorepo reason.
    candidates = sorted(
        path
        for path in root.rglob("scientific-code.toml")
        if path.is_file() and not is_ignored(path, root) and path != config_path
    )
    if candidates:
        return load_scope_config(candidates[0].parent)
    return config


@dataclass(frozen=True)
class ScopeBinding:
    """A scope config paired with the project root its paths are relative to.

    In a monorepo the lint root and the project root differ: the project's
    scientific-code.toml lives in a nested directory, and its stage_roots /
    infrastructure_roots are relative to that directory, not to the lint
    root. Every classification check must use `path_root`.
    """

    path_root: Path
    config: ScopeConfig

    def is_under(self, path: Path, roots: tuple[str, ...]) -> bool:
        return is_under_roots(path, self.path_root, roots)


def scope_binding(root: Path) -> ScopeBinding:
    config_path = root / "scientific-code.toml"
    if config_path.is_file() and _parse_scope_config(config_path) != ScopeConfig():
        return ScopeBinding(path_root=root, config=_parse_scope_config(config_path))
    candidates = sorted(
        path
        for path in root.rglob("scientific-code.toml")
        if path.is_file() and not is_ignored(path, root)
    )
    if candidates:
        project_root = candidates[0].parent
        return ScopeBinding(path_root=project_root, config=_parse_scope_config(candidates[0]))
    return ScopeBinding(path_root=root, config=ScopeConfig())


def _parse_scope_config(config_path: Path) -> ScopeConfig:
    if tomllib is None:
        print(
            "scientific-code lint: scientific-code.toml found but tomllib is "
            "unavailable (Python < 3.11); ignoring the project scope config.",
            file=sys.stderr,
        )
        return ScopeConfig()
    try:
        with config_path.open("rb") as stream:
            data = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as error:
        print(
            f"scientific-code lint: could not parse scientific-code.toml: {error}",
            file=sys.stderr,
        )
        return ScopeConfig()
    scope = data.get("scope", {})
    if not isinstance(scope, dict):
        return ScopeConfig()
    if tomllib is None:
        print(
            "scientific-code lint: scientific-code.toml found but tomllib is "
            "unavailable (Python < 3.11); ignoring the project scope config.",
            file=sys.stderr,
        )
        return ScopeConfig()
    try:
        with config_path.open("rb") as stream:
            data = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as error:
        print(
            f"scientific-code lint: could not parse scientific-code.toml: {error}",
            file=sys.stderr,
        )
        return ScopeConfig()
    scope = data.get("scope", {})
    if not isinstance(scope, dict):
        return ScopeConfig()

    def roots(key: str) -> tuple[str, ...]:
        value = scope.get(key, [])
        if not isinstance(value, list):
            return ()
        return tuple(
            str(item).replace("\\", "/").strip("/")
            for item in value
            if isinstance(item, str) and item.strip("/")
        )

    return ScopeConfig(
        stage_roots=roots("stage_roots"),
        view_roots=roots("view_roots"),
        artifact_roots=roots("artifact_roots"),
        infrastructure_roots=roots("infrastructure_roots"),
    )


def is_under_roots(path: Path, root: Path, roots: tuple[str, ...]) -> bool:
    if not roots:
        return False
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        return False
    return any(relative == entry or relative.startswith(entry + "/") for entry in roots)


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


def is_stage_file(path: Path, binding: ScopeBinding, text: str) -> bool:
    path_root = binding.path_root
    scope = binding.config
    try:
        relative = path.relative_to(path_root)
    except ValueError:
        relative = path
    lowered_parts = {part.lower() for part in relative.parts[:-1]}
    if lowered_parts & {"test", "tests", "template", "templates"}:
        return False
    # An explicit in-file marker is the strongest signal and always wins.
    if contains_marker(text, "stage"):
        return True
    if binding.is_under(path, scope.infrastructure_roots):
        return False
    if binding.is_under(path, scope.stage_roots):
        return True
    return (
        bool(lowered_parts & STAGE_DIRECTORIES)
        or (
            len(relative.parts) == 1
            and bool(STAGE_STEM.match(path.stem.lower()))
        )
    )


def is_view_file(path: Path, binding: ScopeBinding, text: str) -> bool:
    path_root = binding.path_root
    scope = binding.config
    try:
        relative = path.relative_to(path_root)
    except ValueError:
        relative = path
    lowered_parts = {part.lower() for part in relative.parts[:-1]}
    if lowered_parts & {"test", "tests", "template", "templates"}:
        return False
    if contains_marker(text, "view"):
        return True
    if binding.is_under(path, scope.infrastructure_roots):
        return False
    if binding.is_under(path, scope.view_roots):
        return True
    return (
        bool(lowered_parts & VIEW_DIRECTORIES)
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


def git_changed_python_files(root: Path, base_ref: str | None = None) -> set[Path] | None:
    if base_ref:
        diff_target = f"{base_ref}...HEAD"
    else:
        diff_target = "HEAD"
    commands = [
        ["git", "-C", str(root), "diff", "--name-only", "--diff-filter=ACMR", diff_target, "--"],
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
                # Guard against a hung or oddly-configured git blocking lint;
                # 20s is far beyond any plausible metadata query.
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


def project_module_names(paths: Sequence[Path], root: Path) -> dict[str, Path]:
    """Map importable module names to project files (resolved paths).

    Includes `src.`-stripped aliases and package aliases for __init__.py so
    that imports can be resolved to actual project files — and third-party
    modules (which resolve to nothing) are never confused with local stages.
    """
    modules: dict[str, Path] = {}
    for path in paths:
        name = module_name(path, root)
        resolved = path.resolve()
        modules.setdefault(name, resolved)
        if name.startswith("src."):
            modules.setdefault(name[4:], resolved)
        if name.endswith(".__init__"):
            modules.setdefault(name[: -len(".__init__")], resolved)
    return modules


def package_parts_of(current: Path, root: Path) -> list[str]:
    try:
        return list(current.relative_to(root).with_suffix("").parts[:-1])
    except ValueError:
        return list(current.with_suffix("").parts[:-1])


def resolve_candidates(
    candidates: Iterable[str],
    current: Path,
    root: Path,
    project_modules: dict[str, Path],
) -> str | None:
    """Resolve import candidates to a project module name, or None.

    Resolution order: exact project module, `src.`-stripped form, package-
    relative form (sibling imports in flat, non-package layouts), and finally
    a unique-stem fallback for bare names imported through sys.path tricks.
    """
    package_parts = package_parts_of(current, root)
    for candidate in candidates:
        if not candidate:
            continue
        forms = [candidate, candidate.removeprefix("src.")]
        if package_parts:
            forms.append(".".join(package_parts + [candidate]))
        for form in forms:
            if form in project_modules:
                return form
    for candidate in candidates:
        if candidate and "." not in candidate:
            suffix = "." + candidate
            for module in project_modules:
                if module.endswith(suffix):
                    return module
    return None


def iter_imports(
    tree: ast.AST,
    current: Path,
    root: Path,
    project_modules: dict[str, Path],
) -> list[tuple[int, str, str | None]]:
    """Return (line, display name, resolved project module or None) per import."""
    results: list[tuple[int, str, str | None]] = []

    def canonical(resolved: str | None) -> str | None:
        if resolved is None:
            return None
        target = project_modules.get(resolved)
        return module_name(target, root) if target is not None else None

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                resolved = resolve_candidates(
                    [alias.name], current, root, project_modules
                )
                results.append((node.lineno, alias.name, canonical(resolved)))
        elif isinstance(node, ast.ImportFrom):
            candidates: list[str] = []
            display = node.module or ""
            if node.level:
                package_parts = package_parts_of(current, root)
                parents_to_remove = node.level - 1
                if parents_to_remove <= len(package_parts):
                    if parents_to_remove:
                        package_parts = package_parts[:-parents_to_remove]
                    base = package_parts + (node.module.split(".") if node.module else [])
                    candidates.extend(
                        ".".join(base + [alias.name]) for alias in node.names
                    )
                    if node.module:
                        candidates.append(".".join(base))
                    display = ".".join(base) or display
            elif node.module:
                candidates.extend(f"{node.module}.{alias.name}" for alias in node.names)
                candidates.append(node.module)
            resolved = resolve_candidates(candidates, current, root, project_modules)
            results.append((node.lineno, display, canonical(resolved)))
    return results


def find_stage_route(
    start: str,
    import_graph: dict[str, set[str]],
    project_modules: dict[str, Path],
    stage_paths: set[Path],
    origin: Path,
) -> list[str] | None:
    """DFS from a directly imported module; return a route to any stage module."""
    stack = [(start, [start])]
    visited: set[str] = set()
    while stack:
        node, route = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        node_path = project_modules.get(node)
        if (
            node_path is not None
            and node_path.resolve() != origin
            and node_path in stage_paths
        ):
            return route
        for follow in sorted(import_graph.get(node, ())):
            if follow not in visited:
                stack.append((follow, route + [follow]))
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


def cli_arguments(tree: ast.AST) -> list[tuple[int, str | None]]:
    """Return (line, argument name or None) for each CLI argument definition."""
    arguments: list[tuple[int, str | None]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = qualified_name(node.func)
        if not (
            name.endswith(".add_argument")
            or name.endswith(".option")
            or name in {"typer.Option", "click.option"}
        ):
            continue
        argument_name: str | None = None
        if (
            node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            argument_name = node.args[0].value.lstrip("-").replace("-", "_")
        arguments.append((node.lineno, argument_name))
    return arguments


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


def missing_contract_sections(doc: str) -> list[str]:
    """List contract sections absent from a docstring.

    Accepts NumPy, Google, and Sphinx styles as well as Chinese headings;
    a section counts as present when the docstring addresses the topic at
    all, regardless of documentation convention.
    """
    checks = {
        # Roughly one meaningful sentence in any language; shorter
        # docstrings rarely carry a contract worth auditing.
        "purpose": len(doc.strip()) >= 20,
    }
    for name, pattern in DOCSTRING_PATTERNS.items():
        checks[name] = bool(pattern.search(doc))
    return [name for name, present in checks.items() if not present]


def warning_suppressions(text: str) -> dict[str, str]:
    return {match.group(1): match.group(2).strip() for match in SUPPRESSION.finditer(text)}


def view_scientific_computation(text: str) -> tuple[int, str] | None:
    """First statistics pattern in executable view code.

    Comments, docstrings, and string literals (including f-string text and
    interpolation keys) are masked so provenance narratives ("bootstrap CI
    computed by the analyze stage") and axis labels do not trip the check;
    only real computation triggers SC109.
    """
    lines = text.splitlines(keepends=True)

    def offset(pos: tuple[int, int]) -> int:
        row, col = pos
        return sum(len(line) for line in lines[: row - 1]) + col

    prose_types = {tokenize.COMMENT, tokenize.STRING}
    fstring_middle = getattr(tokenize, "FSTRING_MIDDLE", None)
    if fstring_middle is not None:
        prose_types.add(fstring_middle)
    masked: list[tuple[int, int]] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type in prose_types:
                masked.append((offset(token.start), offset(token.end)))
    except (tokenize.TokenError, IndentationError):
        masked = []
    for match in VIEW_SCIENTIFIC_COMPUTATION.finditer(text):
        if any(start <= match.start() < end for start, end in masked):
            continue
        line = text.count("\n", 0, match.start()) + 1
        return line, match.group(0)
    return None


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


def find_placeholder_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip()[:60] if PLACEHOLDER_TEXT.match(value) else None
    if isinstance(value, dict):
        for item in value.values():
            found = find_placeholder_text(item)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = find_placeholder_text(item)
            if found:
                return found
    return None


def validate_optimization_report(report: dict[str, Any]) -> list[str]:
    """Check that an optimization report contains real end-to-end evidence.

    A report that merely names the stage does not count: the speedup must be
    the ratio of the two measured end-to-end times, scientific equivalence
    must have passed, and template placeholder prose is rejected.
    """
    problems: list[str] = []
    if not isinstance(report.get("stage"), str):
        problems.append("missing stage name")

    reference = report.get("reference")
    optimized = report.get("optimized")
    reference_time = (
        reference.get("end_to_end_wall_time_s") if isinstance(reference, dict) else None
    )
    optimized_time = (
        optimized.get("end_to_end_wall_time_s") if isinstance(optimized, dict) else None
    )
    times_valid = (
        isinstance(reference_time, (int, float))
        and reference_time > 0
        and isinstance(optimized_time, (int, float))
        and optimized_time > 0
    )
    if not times_valid:
        problems.append("reference/optimized end-to-end times are missing or invalid")
    else:
        speedup = report.get("pipeline_speedup")
        if not isinstance(speedup, (int, float)):
            problems.append("pipeline_speedup is missing")
        else:
            expected = reference_time / optimized_time
            # 1% tolerance absorbs rounding in reported timings without
            # accepting claims that misstate the measured ratio.
            if abs(speedup - expected) / expected > 0.01:
                problems.append(
                    "pipeline_speedup does not equal the reference/optimized ratio"
                )

    equivalence = report.get("scientific_equivalence")
    if not isinstance(equivalence, dict) or equivalence.get("result") != "pass":
        problems.append("scientific_equivalence.result is not 'pass'")
    if report.get("decision") not in {"accept", "reject"}:
        problems.append("decision is missing or not accept/reject")

    environment = report.get("environment")
    if isinstance(environment, dict):
        commit = str(environment.get("git_commit", ""))
        if commit and set(commit) == {"0"}:
            problems.append("environment.git_commit is a placeholder")

    placeholder = find_placeholder_text(report)
    if placeholder:
        problems.append(f"contains template placeholder text: {placeholder!r}")
    return problems


def optimization_report_targets(root: Path) -> dict[str, list[str]]:
    """Map stage-name keys to the validation problems of their report.

    An empty problem list means a valid report covers that key.
    """
    targets: dict[str, list[str]] = {}
    for report_path in find_files_named(root, "optimization_report.json"):
        try:
            report = load_json(report_path)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(report, dict) or not isinstance(report.get("stage"), str):
            continue
        problems = validate_optimization_report(report)
        stage = report["stage"].replace("\\", "/").strip().lower()
        for key in {stage, Path(stage).stem.lower(), stage.removesuffix(".py")}:
            # A valid report wins over an invalid one for the same key.
            if key not in targets or not problems:
                targets[key] = problems
    return targets


def optimization_report_problems(
    path: Path,
    root: Path,
    targets: dict[str, list[str]],
) -> list[str] | None:
    """None if no report claims this file; otherwise the report's problems."""
    try:
        relative = path.relative_to(root).as_posix().lower()
    except ValueError:
        relative = path.as_posix().lower()
    candidates = {
        path.stem.lower(),
        relative,
        relative.removesuffix(".py"),
    }
    found: list[str] | None = None
    for key in candidates:
        if key in targets:
            problems = targets[key]
            if found is None or not problems:
                found = problems
    return found


def verify_artifact_dir(
    artifact_dir: Path,
    collector: IssueCollector,
    full: bool,
) -> None:
    """Verify one artifact directory.

    Metadata mode (full=False) checks schema, paths, existence, derived
    hashes, and approval binding without reading payload content, so lint
    stays cheap on large data. Full mode additionally re-hashes every tracked
    payload of an approved artifact to detect post-approval tampering.
    """
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
        return

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
        return

    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
        collector.add(
            "error",
            "SC004",
            manifest_path,
            0,
            "Artifact manifest must contain a files object.",
        )
        return
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
        return

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
        if full and approved:
            actual_hash = sha256_file(tracked_path)
            if actual_hash != expected_hash:
                collector.add(
                    "error",
                    "SC007",
                    tracked_path,
                    0,
                    f"Tracked content changed after approval; expected "
                    f"{expected_hash}, got {actual_hash}.",
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
        return

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


def check_artifacts(root: Path, collector: IssueCollector, full: bool) -> None:
    candidates = artifact_candidate_directories(root)

    for artifact_dir in sorted(candidates):
        verify_artifact_dir(artifact_dir, collector, full)

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
                # Paths in run.json are relative to the owning project's
                # root (the directory whose scientific-code.toml scopes the
                # pipeline), which may differ from the lint root in a
                # nested/monorepo layout.
                input_dir = run_path.parent
                while input_dir != input_dir.parent and not (
                    input_dir / "scientific-code.toml"
                ).is_file():
                    input_dir = input_dir.parent
                if not (input_dir / "scientific-code.toml").is_file():
                    input_dir = root
                input_dir = input_dir / raw_path

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
                continue

            if full:
                # Metadata comparison alone cannot detect payload tampering in
                # an external artifact; re-hash its tracked content.
                for relative_name, expected_file_hash in sorted(
                    manifest["files"].items()
                ):
                    tracked_path = input_dir / str(relative_name)
                    payload_ok = (
                        stays_within(tracked_path, input_dir)
                        and tracked_path.is_file()
                        and sha256_file(tracked_path) == expected_file_hash
                    )
                    if not payload_ok:
                        collector.add(
                            "error",
                            "SC005",
                            run_path,
                            0,
                            f"Input artifact {raw_path!r} payload "
                            f"{relative_name!r} does not match its approved manifest.",
                        )
                        break


def analyze_python(
    path: Path,
    root: Path,
    text: str,
    tree: ast.AST,
    imports: list[tuple[int, str, str | None]],
    project_modules: dict[str, Path],
    import_graph: dict[str, set[str]],
    stage_paths: set[Path],
    scope: ScopeBinding,
    optimization_targets: dict[str, list[str]],
    collector: IssueCollector,
) -> None:
    stage = is_stage_file(path, scope, text)
    view = is_view_file(path, scope, text)

    if stage or view:
        for line, display, resolved in imports:
            if resolved is None:
                continue
            target_path = project_modules.get(resolved)
            if target_path is None or target_path.resolve() == path.resolve():
                continue
            if target_path in stage_paths:
                if stage:
                    collector.add(
                        "error",
                        "SC001",
                        path,
                        line,
                        f"Stage imports stage implementation {display!r}; "
                        "depend on its artifact contract instead.",
                    )
                else:
                    collector.add(
                        "error",
                        "SC006",
                        path,
                        line,
                        f"View imports stage implementation {display!r}; "
                        "consume an approved artifact instead.",
                    )
                continue
            route = find_stage_route(
                resolved, import_graph, project_modules, stage_paths, path.resolve()
            )
            if route:
                pretty = " -> ".join(route)
                if stage:
                    collector.add(
                        "error",
                        "SC001",
                        path,
                        line,
                        f"Stage reaches stage implementation transitively via "
                        f"{display!r} ({pretty}); depend on the artifact contract instead.",
                    )
                else:
                    collector.add(
                        "error",
                        "SC006",
                        path,
                        line,
                        f"View reaches stage implementation transitively via "
                        f"{display!r} ({pretty}); consume an approved artifact instead.",
                    )

    if stage:
        cli_args = cli_arguments(tree)
        scientific_args = [
            (line, name)
            for line, name in cli_args
            if name and SCIENTIFIC_ARG_NAME.match(name)
        ]
        if scientific_args:
            names = ", ".join(sorted({name for _, name in scientific_args}))
            collector.add(
                "error",
                "SC002",
                path,
                scientific_args[0][0],
                f"Stage exposes scientific parameter(s) via CLI ({names}); "
                "put scientific configuration in TOML.",
            )
        # Documented ceiling: config path plus one operational flag. A
        # busier CLI almost always means scientific parameters leaked out
        # of the TOML config.
        elif len(cli_args) > 2:
            collector.add(
                "warning",
                "SC002",
                path,
                cli_args[2][0],
                f"Stage defines {len(cli_args)} CLI parameters; keep the CLI "
                "minimal and put configuration in TOML.",
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
        if optimization:
            line, name = optimization
            problems = optimization_report_problems(path, root, optimization_targets)
            if problems is None:
                collector.add(
                    "warning",
                    "SC105",
                    path,
                    line,
                    f"Optimization construct {name!r} has no optimization_report.json with end-to-end evidence.",
                )
            elif problems:
                joined = "; ".join(problems)
                collector.add(
                    "warning",
                    "SC105",
                    path,
                    line,
                    f"Optimization construct {name!r} has an optimization report, "
                    f"but it lacks valid evidence: {joined}.",
                )

        module_doc = ast.get_docstring(tree, clean=False) or ""
        module_contract_complete = not missing_contract_sections(module_doc)

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
            if likely_scientific_function(node) and not module_contract_complete:
                doc = ast.get_docstring(node, clean=False) or ""
                missing = missing_contract_sections(doc)
                if missing:
                    collector.add(
                        "warning",
                        "SC108",
                        path,
                        node.lineno,
                        f"Likely scientific function {node.name!r} lacks contract content: {', '.join(missing)}.",
                    )

    if view:
        scientific_hit = view_scientific_computation(text)
        if scientific_hit:
            line, token_text = scientific_hit
            collector.add(
                "warning",
                "SC109",
                path,
                line,
                f"View appears to perform scientific computation ({token_text!r}); "
                "move statistics to an analysis stage artifact and keep the view presentation-only.",
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

        # Naming-discipline heuristics apply only inside the scientific
        # pipeline scope; legitimate infrastructure keeps its own conventions
        # (see the scope gate in SKILL.md).
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
        "--base-ref",
        metavar="REF",
        default=None,
        help="Analyze files changed between REF's merge base and HEAD (for CI); "
        "implies --changed-only.",
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
    parser.add_argument(
        "--full-artifact-checks",
        action="store_true",
        help="Re-hash approved artifact payloads and recorded input payloads. "
        "Off by default so lint stays cheap on large data; enable for release "
        "verification or scheduled integrity audits.",
    )
    return parser.parse_args(argv)


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"scientific-code lint: project root does not exist: {root}", file=sys.stderr)
        return 2
    scope = scope_binding(root)

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

    # Parse every file once: the import graph needs imports from files that
    # are not themselves selected for analysis (e.g. a middle module between
    # two stages).
    trees: dict[Path, ast.AST] = {}
    for path, text in text_by_path.items():
        try:
            trees[path] = ast.parse(text, filename=str(path))
        except SyntaxError as error:
            collector.add(
                "error",
                "SC000",
                path,
                error.lineno or 0,
                f"Python source could not be parsed: {error.msg}.",
            )

    stage_paths = {
        path.resolve()
        for path, text in text_by_path.items()
        if is_stage_file(path, scope, text)
    }

    project_modules = project_module_names(all_python_files, root)
    imports_by_path: dict[Path, list[tuple[int, str, str | None]]] = {}
    import_graph: dict[str, set[str]] = {}
    for path, tree in trees.items():
        imports = iter_imports(tree, path, root, project_modules)
        imports_by_path[path] = imports
        module = module_name(path, root)
        edges = import_graph.setdefault(module, set())
        for _, _, resolved in imports:
            if resolved is not None and resolved != module:
                edges.add(resolved)

    selected_files = set(text_by_path)
    if args.changed_only or args.base_ref:
        changed = git_changed_python_files(root, args.base_ref)
        if changed is not None:
            selected_files &= changed
        elif args.base_ref:
            print(
                f"scientific-code lint: could not diff against {args.base_ref!r}; "
                "falling back to all files.",
                file=sys.stderr,
            )

    optimization_targets = optimization_report_targets(root)

    for path in sorted(selected_files):
        analyze_python(
            path,
            root,
            text_by_path[path],
            trees[path],
            imports_by_path.get(path, []),
            project_modules,
            import_graph,
            stage_paths,
            scope,
            optimization_targets,
            collector,
        )

    if not args.no_artifact_checks:
        check_artifacts(root, collector, full=args.full_artifact_checks)

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
                        "full_artifact_checks": bool(args.full_artifact_checks),
                        "scope_config": (root / "scientific-code.toml").is_file(),
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
