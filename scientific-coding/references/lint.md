# 科研代码检查工具

仅在使用、配置或解释 linter 时读取；它是离线撰写工具，不是业务运行门控。

## Deterministic Linter

Run:

```bash
python <skill-dir>/scripts/scientific_code_lint.py <project-root> --changed-only
```

Use `--base-ref origin/main` in CI to diff against the merge base (a clean PR checkout has no working-tree changes, so plain `--changed-only` would check nothing). Use `--strict-warnings` in CI once existing warnings have been triaged. Use `--format json` for machine-readable output. Static AST checks cannot prove semantic correctness; combine them with contract and scientific-invariant tests.

Which files count as stages or views is decided by, in order: an in-file marker (`# scientific-code: stage` / `view`), the project's `scientific-code.toml` scope roots (see [the template](../templates/scientific-code.toml)), then naming conventions (`stages/` directories, common stage/view file stems). Infrastructure roots declared in the config are exempt from the naming-discipline heuristics. Declare the scope explicitly whenever the project layout does not match the conventions. When the lint root has no `scientific-code.toml` — or one with an empty `[scope]` — the nearest nested project config is used instead (monorepo layout), and its roots apply relative to that project's directory, not to the lint root.

Artifact integrity checks run in two modes. The default metadata mode validates schema, paths, derived hashes, and approval binding without reading payload content, so lint stays cheap on large data. `--full-artifact-checks` additionally re-hashes finalized artifact payloads and recorded input artifact payloads; use it for release verification or scheduled integrity audits, not on every lint run.

Hard errors:

| Code | Meaning |
|---|---|
| `SC000` | source or project configuration cannot be read or parsed, so checks cannot run reliably |
| `SC001` | stage imports another stage implementation, directly or through a chain of local modules |
| `SC003` | finalized artifact hashes or an optional approval binding disagree |
| `SC004` | an artifact candidate is missing or has an unreadable manifest |
| `SC005` | a recorded input is invalid/hash-incompatible or fails an explicitly requested review point; in `--full-artifact-checks` mode also fires when the input payload no longer matches its manifest |
| `SC006` | a view imports a scientific stage implementation, directly or transitively |
| `SC007` | tracked artifact content differs from its finalized manifest (payload comparison requires `--full-artifact-checks`) |
| `SC008` | a formal non-acquisition stage performs a known network call |

CLI structure is an engineering choice, so `SC002` is advisory even when scientific parameter names are detected. A user-selected CLI must still record effective scientific choices.

Heuristic warnings:

| Code | Meaning |
|---|---|
| `SC002` | scientific parameter CLI or more than two operational arguments; prefer explicit configuration unless the project/user chose this interface |
| `SC101` | scientific branch may be hidden behind config `if/else` |
| `SC102` | factory/registry/manager-style abstraction appeared in pipeline scope |
| `SC103` | generic `utils.py`/`helpers.py`-style module appeared in pipeline scope |
| `SC104` | checkpoint or resume machinery appeared |
| `SC105` | optimized/specialized implementation lacks a valid optimization report (missing, placeholder text, or `pipeline_speedup` inconsistent with the recorded end-to-end times) |
| `SC106` | broad exception fallback may hide failure |
| `SC107` | a scientific function may mutate an input parameter |
| `SC108` | a likely scientific function lacks a semantic contract docstring (NumPy, Google, Sphinx, and Chinese conventions are accepted; a module overview does not waive scientific function contracts) |
| `SC109` | a view appears to perform scientific computation (bootstrap, outlier removal, percentile/interval statistics, normalization, fitting); comments, docstrings, and labels are masked, executable identifiers are heuristic evidence, not proof of a calculation |

`SC102`/`SC103` apply only inside pipeline scope (stage/view files); infrastructure code keeps its own conventions, per the scope gate.

A warning may be suppressed at file scope only with a concrete justification:

```python
# scientific-code: allow SC104 -- 任务在可抢占节点运行四天，已核验确定性分片
```

Only warnings can be suppressed, including SC002; hard errors cannot be suppressed. Use a directive when the flagged construct is deliberate and the reason would help a reviewer. Do not override an authorized engineering choice just to silence a style warning.
