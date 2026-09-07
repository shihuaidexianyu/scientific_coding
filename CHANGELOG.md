# Changelog

## 未发布 - 2026-09-07

- 将默认规范收拢为实验组织、可读性、执行记录三份参考，合并重复准入/工作流说明；高级产物、审批、恢复与优化按需读取，保留兼容链接和历史证据。
- 重写 README，新增单一 TOML 与独立 stages 的基础实验；覆盖导入/配置/数据失败、跨目录、重跑和并发，详细记录精简范围与验证边界。

- 新实验目录统一放置设计 MD、实验命名的单一 TOML 和专属编排 Python；stage 独立存放，由编排读取一次配置、按 TOML 目录解析路径并分发参数，替换旧多配置编排模板。
- 将“掌握 Python 基础语法的初学者可顺序读懂”设为明确阅读标准；默认具名中间结果、简单赋值和显式条件/循环，保留清楚的标准科学 API，并加入按数据流阅读的验收要求。
- 明确必要检查由实际 pipeline 编排承担，stage 与科学辅助函数保留业务逻辑；统一必要性、归属及变换后/发布前时点，覆盖独立 CLI、恢复和外部产物复用。
- 编排与检查代码同样遵守浅层表达式规范；补充调用顺序示意，标明旧集成示例的 stage 内检查尚未迁移，避免把它继续当作当前设计正例。

## 未发布 - 2026-09-06

- 整改检查器、运行记录与示例编排五个核心实现自身的嵌套、内联构造和超长行；新增同规则自检，记录行为差分与未整改范围，不以程序测试通过代替可读性验收。
- 明确输出 token、行数和字符数不能凌驾于代码可读性；禁止为压缩回答隐藏中间步骤、滥用语法糖或省略中文说明，资源紧张时保留完整语义单元续接。
- 将运行检查改为“初稿不预装，整体逻辑完成后才逐项论证必要性”；统一外部输入、统计和视图的准入依据，保留原生异常与离线科学核验。
- 精简主入口、阶段指南和审计清单；拆分普通成本估计与优化手册、作者核验与 linter 手册，按当前任务加载。
- 函数模板移除默认空列表防御，普通配置模板移除审批字段；来源和优化模板清空假定测量与预先通过结论，标明集成示例的适用范围。
- 增加浅层推导与控制流、源码/注释/TOML 80 字符硬上限、传参前命名中间结果、显式 fallback 和单职责循环要求；同步简化、格式与核验轮，修正旧 88 列建议及函数模板。
- 普通与失败科研运行默认保留完整 stdout/stderr/堆栈、起止时间、实际状态和退出码、阶段耗时及可获得的资源记录；批量索引关联每次独立尝试，重跑保留原结果。
- 代码交付后用中文说明工作量、时间/内存复杂度及有依据的耗时估计，明确实测、外推和未知。普通估计不自动触发性能优化或审批流程。
- 示例在启动边界实现日志与独立索引；配置解析失败和阶段发布前失败保留精确来源，复用外部结果后失败也保存已有绑定。新增对应实际失败、长日志、并发与保留测试。

## 0.5.0 - 2026-09-05

### Changed
- Add a final independent source review for complete plans or multi-function documentation/simplification when supported, with one edit owner and local repairs. Require small counterexamples to verify the task formatter, and clarify file-wide I/O responsibility and preservation of distinct facts within combined boundary checks.
- Standardize Chinese function docstrings as purpose, parameters, returns, processing steps, and side effects, with separate name/type lines, indented explanations, and individual nested fields. Add truthful character flow diagrams to file headers with opening triple quotes on a separate line; distinguish actual language-server hover evidence from source-only checks.
- Require Chinese file overviews, genuine hover-visible function documentation with spaced parameter/result structures, and Chinese semantic comments and data guides. Localize the maintained example and TOML templates accordingly.
- Separate authoring into implementation, simplification, explanation, formatting, and verification passes, with local repairs and explicit handling of mid-review questions and user edits. Preserve manual changes and keep validation evidence tied to the code it checked.
- Require local explanations for meaningful code operations and every TOML section/key, with a blank line before comment blocks. The agent must write/run a task-specific formatter across the actual source/config languages to enforce spacing without changing code or string meaning.
- Describe all initial inputs, intermediate datasets, reading methods, and sample lineage, including joins, splits, and aggregation.
- Reuse established guarantees; check only external entry facts and invariants actually threatened by a transformation. Avoid internal validation flags and repeated gates.
- Run continuously by default; retain optional user-selected review points and honest provenance without compulsory approval files.
- Respect user instructions and existing configuration systems. Replace rigid delivery forms with concise relevant evidence.
- Rebuild the standard-library example with real contracts, fresh atomic publication, stable scientific hashes, complete explanations, and continuous output through the figure.

### Fixed
- Verify all finalized artifacts, including pending review, and verify full content before recording a review decision.
- Reject placeholder or mismatched contracts, preserve finalized results, and separate execution timestamps from scientific identity.
- Handle syntax and scope errors, per-project scopes, custom artifact roots, ambiguous imports, operational CLI suppression, and nested Git diff paths.
- Correct clustered inference and exchangeability guidance, statistical-unit count, and interpretation of random-seed sensitivity.
- Require task evidence and linter success in evaluations; distinguish unknown, invalid, smoke, and observed skill reads. Test new workflow behavior instead of compulsory gates.
- Move CI workflows to the repository root and replace stale, artificially approved example fixtures with runnable source.

## 0.4.0 - 2026-09-04

### Added
- SC109 heuristic warning: a view that performs scientific computation
  (bootstrap, outlier removal, percentile/interval statistics, normalization,
  fitting) is flagged. Comments, docstrings, string literals, and f-string
  text are masked so provenance narratives and axis labels do not fire.

### Changed
- SKILL.md non-negotiable rules: explicit statement that the rules bind
  regardless of instruction source (no forging approvals, mutating approved
  artifacts, or bypassing gates to satisfy a user instruction, an
  end-to-end-result demand, or a deadline); on conflict, do the compliant
  part and report the conflict plus the compliant alternative.
- SKILL.md working sequence: genuine scientific forks are separated from
  ordinary underspecification; adopt the narrowest reasonable assumption
  and keep working, recording open questions in the completion report.
- references/view.md: the presentation-only boundary holds regardless of
  where the work is requested, including explicit user requests to compute
  statistics inside the figure file.

### Fixed
- The linter no longer lints installed skill copies (`.claude/skills`,
  `.agents/skills`); their shipped example is not project code and its
  stage imports produced phantom SC001 noise in every eval workdir.
- Eval runs whose agent call failed at the API level (provider quota/429)
  are marked invalid (`pass=None`) instead of graded as real failures, and
  the rubric judge skips them; summary tables show an invalid count.
- The plot case drops its `fail_if` text pattern: plain regex could not
  distinguish executable statistics from a docstring, comment, or axis
  label naming the source artifact; masked SC109 plus the judge cover the
  failure mode with fewer false positives.
- references/optimization.md: a measured bound that rules out the
  requested parallelism must decline the mechanism (analysis delivered
  alongside the non-paying machinery is a failure); a decided optimization
  must be implemented and re-measured, not described.
- references/artifact.md: config-driven reruns create a new run directory;
  approved run content is read-only even under sensitivity-check pressure.

## 0.2.0 - 2026-09-04

### Added
- `scripts/scientific_artifact.py`: reference implementation of the artifact
  lifecycle (init / finalize / verify / approve). `finalize` writes the
  two-layer hashes and submits for review; `approve` is human-only, refuses
  non-interactive terminals, and requires typed confirmation.
- Linter support for a project-level `scientific-code.toml` declaring
  stage/view/artifact/infrastructure roots.
- `--base-ref` for merge-base diffs in CI; `--full-artifact-checks` for
  payload re-hashing on a separate, expensive tier.
- Transitive stage-import detection (SC001/SC006) with the import route in
  the message.
- Behavioral eval harness: `evals/run_evals.py`, `evals/graders.py`, fixture
  repositories, machine-checkable `fail_if_patterns`, Chinese prompts,
  self-approval and negative-control cases.
- Regression suites: `tests/test_linter.py` (per-check positive/negative/
  false-positive/suppression fixtures), `tests/test_artifact.py` (artifact
  CLI lifecycle).

## 0.3.0 - 2026-09-04

### Added
- `examples/minimal_pipeline/`: a complete, runnable worked example
  (synthetic acquisition -> preprocess with row-level exclusion ledger ->
  bootstrap analysis -> hand-written SVG view). Committed artifacts are
  approved, so `lint --full-artifact-checks` passes out of the box.
- `tests/test_integration.py`: committed-example verification, full
  lifecycle rebuild in a temp directory, same-seed hash reproducibility,
  and pending-review blocking downstream stages.
- `references/statistical_validity.md` (routed as `DESIGN_INFERENCE`):
  the seven units of statistical validity and the non-negotiable checks
  (n with its unit, no double-dipping, multiple comparisons, seed
  sensitivity).
- CI workflows: PR gate (tests + linter self-check + mock evals +
  committed-example full checks) and nightly real-model evals with
  archived results.
- Monorepo scope handling: when the lint root has no usable
  `scientific-code.toml`, the nearest nested project config is used, with
  its roots applied relative to the owning project directory.
- run.json `input_artifacts` relative paths resolve against the owning
  project's root (walk-up to the directory holding `scientific-code.toml`),
  not blindly against the lint root.

### Fixed
- Linting a monorepo root no longer misclassifies nested project stages
  or reports false SC005 "missing approval" for their recorded inputs.

### Fixed
- SC102/SC103 apply only inside pipeline scope; infrastructure code keeps
  its own conventions, matching the scope gate.
- SC001 no longer flags third-party modules merely named `stages`.
- SC105 validates report content (speedup ratio, equivalence pass, no
  placeholder prose) instead of matching names only.
- SC108 accepts NumPy/Google/Sphinx and Chinese contract docstrings; a
  complete module-level contract waives per-function checks.
- SC002 distinguishes scientific CLI parameters (error) from busy
  operational flags (warning).
- Approval records: template default is `pending_review`; the agent is
  forbidden to create or modify approval records (SKILL.md rule).
- Artifact integrity checks split: default metadata mode no longer reads
  payloads; external recorded inputs get payload verification in full mode.

## 0.1.0 - initial release

Design documents (SKILL.md, references/, templates/), the deterministic
linter (SC000-SC008, SC101-SC108), and the eval specification.
