# 总体判断

这是一个**方向非常正确、方法论高度一致、但工程闭环尚未完成的强 v0.1 skill**。

它最有价值的地方，并不是提出了若干“科研代码应该可复现”的常见口号，而是确立了一个非常明确的核心目标：

> **降低科学方法、研究者阅读到的源代码、机器实际执行的计算三者之间的语义距离。**

围绕这个目标，Stage、Artifact、科学分支、配置、绘图、性能优化和续跑设计基本形成了同一套逻辑，而不是彼此独立的规范。这一点相当难得。

我的主观评分是：

| 维度                      | 评价       |
| ------------------------- | ---------- |
| 方法论完整性              | 9/10       |
| 内部一致性                | 9/10       |
| Skill 结构设计            | 8.5/10     |
| 对 Agent 行为的约束力     | 7/10       |
| Linter 当前可靠性         | 6/10       |
| Artifact 系统可直接落地性 | 5.5/10     |
| Evals 成熟度              | 3.5/10     |
| 综合                      | **7.5/10** |

它已经远好于大多数“把一堆偏好写进 SKILL.md”的 skill，但现在更像一个**设计规范 + 原型工具链**，还没有变成一个经过实证验证、可以放心自动触发的完整系统。

------

# 一、这个 skill 真正设计的是什么

它表面上叫 Scientific Coding，实际上设计的是一套：

> **面向单项研究的、Artifact 驱动的科学计算操作模型。**

核心链路是：

```text
Declared Artifact + Explicit Config + Code
                       ↓
                Scientific Stage
                       ↓
               Immutable Artifact
                       ↓
                 Human Approval
```

其中：

- Stage 是一个有明确科学含义的转换；
- Artifact 是 Stage 之间唯一的正式接口；
- Config 是显式的科学参数；
- Run metadata 记录代码、环境、随机性和输入；
- Human approval 把“成功运行”和“科学上接受”区分开；
- View 只负责表达结果，不能偷偷承担分析；
- 优化和续跑只有在端到端研究价值足够大时才能引入复杂度。

因此它并不是传统意义上的 Python style guide，也不是简单的 pipeline framework。它更接近一个：

> **科研代码的语义治理层。**

这是一个很好的定位。

------

# 二、我最认可的部分

## 1. “最小语义跳转”比“最少代码”更适合科研代码

你没有沿用传统软件工程里经常被滥用的 DRY、Factory、Manager、Registry、Strategy 等模式，而是要求顶层代码尽量直接呈现科学流程：

```python
valid_trials, exclusions = remove_invalid_trials(...)
aligned_trials = align_trials(...)
features = compute_features(...)
```

而不是：

```python
PipelineFactory.create(config).execute()
```

对于单项研究的分析代码，我基本完全赞同。

科研代码的核心审查问题通常不是：

> 这个类有没有遵守某个设计模式？

而是：

> 某个 trial 经过了哪些变换？
> 为什么被排除？
> baseline 到底怎么算？
> permutation 的统计单位是什么？
> 当前结果和论文方法是否一致？

所以，“允许少量重复，换取方法局部完整可读”，是合理而且经常被低估的选择。Stage 文档对于“重复 orchestration 可以接受，但真正稳定的科学概念可以提取”这一边界也写得比较克制。

## 2. 科学分支和工程分支被明确区分

你强调：

- 不同科学方法不能仅因为 shape 和 dtype 相同就合并；
- 不同方法不能为了消除重复而隐藏在 `config.mode` 后；
- 只有 representation、unit、coordinate、time origin、preprocessing、sample meaning 都等价时，才能重新汇合。

这是非常重要的。

普通代码审查很容易认为：

```python
if config.mode == "raw":
    ...
elif config.mode == "hfb":
    ...
```

是“灵活”“可扩展”；但对研究者来说，它可能把两个完整的科学程序压进了一个动态分支，使得审查者必须在代码、配置和运行时状态之间来回跳转。

你真正反对的不是 `if`，而是：

> **用工程复用掩盖科学方法分叉。**

这个思想我认同。

## 3. Stable sample ID 和 exclusion ledger 是全仓库最有科学价值的规则之一

要求样本在 raw、processed、feature、prediction、statistics 各阶段保留稳定身份，并在样本集合发生变化时输出逐样本 exclusion ledger，而不是只报告“删除了 37 个 trial”，这是非常好的设计。

大量真实科研错误都不是算法写错，而是：

- 排序后 label 没对齐；
- merge 后样本重复；
- 某一步静默 drop NaN；
- 图里删了 outlier，但统计阶段没有；
- CV、bootstrap 或 permutation 使用了错误的独立统计单位；
- 同一个 trial 被重复映射后当成独立样本。

Stable ID 和 exclusion ledger 至少能让这些问题可追踪。

## 4. Artifact 的双层 hash 设计是一个很好的技术细节

你区分了：

- `artifact_hash`：绑定 contract 和具有科学身份意义的 payload；
- `manifest_hash`：绑定包括 runtime、run provenance 在内的全部清单；
- `approval.json`：同时绑定这两个 hash。

这样既可以让 `run.json` 记录输出的 `artifact_hash`，又避免 manifest、run、approval 之间产生自引用哈希循环。这个方案是经过认真思考的，不是随手加几个 SHA-256 字段。

## 5. “运行成功不等于科学批准”非常正确

科研流水线里常见的错误是：

```text
exit code = 0
→ 结果可用
→ 自动进入下游
```

但实际上：

- 样本数量可能异常；
- 分布可能错；
- exclusion 可能超出预期；
- 坐标系可能翻转；
- 某个新默认值可能改变科学含义。

把 `produced` 和 `approved` 分开，是合理的。

## 6. 性能优化章节准确编码了你的研究价值观

这一部分与我理解的你的观念高度一致：

- 衡量的是 time to scientific answer；
- 只看端到端 wall-clock；
- kernel benchmark 只是诊断证据；
- 优先跨越研究反馈周期；
- 3 天到 7 小时远比 10 分钟到 5 分钟重要；
- RAM 只要可行就可以积极使用；
- I/O 占 70% 时不应该去优化数学 kernel；
- 并行之前先用 Amdahl’s law 判断上限；
- 复杂 fast path 必须保留可读 reference implementation。

这一部分是仓库里最成熟的 reference 之一。

## 7. 续跑设计没有陷入“所有任务都加 checkpoint”

你没有把 resumability 当成默认工程美德，而是先计算：

- 单 stage 时长；
- 失败概率；
- 排队延迟；
- 稀缺 GPU 成本；
- 重跑造成的实际研究延误。

并且优先使用确定性、幂等、可独立验证的 shard，而不是 pickle 任意 Python 状态。这非常符合科学计算。

## 8. View 的 deletion test 很好记，也很容易执行

你提出：

> 删除绘图库之后，如果剩下的操作仍然具有科学含义，那么它就不属于 View。

这是一条非常好的 Agent 规则。

例如：

- bootstrap CI；
- outlier removal；
- normalization；
- model fitting；
- group statistics；

这些都不能只存在于 `figure.py`。

## 9. Skill 本身使用了正确的 progressive disclosure 结构

主 `SKILL.md` 保留高频规则和路由，详细内容放在 references；确定性行为交给脚本；模板独立保存。这与当前 Codex skill 的 progressive disclosure 机制和官方建议基本一致：初始只暴露 name 和 description，选择 skill 后再加载完整 `SKILL.md`，需要时再读取 references。([developers.openai.com](https://developers.openai.com/codex/build-skills))

------

# 三、我是否认同你的整体观念

我大约 **85% 认同**，而且认同最核心的那一部分：

> 对单项研究的科学流水线，代码首先是科学方法的可执行表述，其次才是可复用软件。

我尤其认同以下优先级：

```text
科学正确性
> 人工可审计性
> 数据血缘
> 可复现性
> 研究迭代延迟
> 性能
> 内存
> 复用
> 代码紧凑度
```

但是我认为你现在有一个潜在风险：

> 你成功地反对了过度工程化，但有少数规则可能从“反对过度抽象”摆向“系统性排斥合理抽象”。

真正应该成为不可妥协原则的是：

- 科学语义必须显式；
- 样本身份和成员变化必须可追踪；
- 输入、随机性和 provenance 不能隐藏；
- 科学方法变化必须报告；
- 优化和 checkpoint 复杂度必须有证据；
- 正式图表不能隐藏推断过程。

而下面这些更适合作为**强默认值**，不应全部叫 Non-Negotiable：

- 一个 Stage 默认一个 Python 文件；
- 配置一定使用 TOML；
- 所有科学分支一定复制成 sibling 文件；
- 下游永远只能消费人工批准的 Artifact；
- 任何 `Manager`、`Adapter` 或 `utils.py` 都值得怀疑；
- Stage CLI 永远只能有一两个参数。

换句话说：

> **原则应当不可妥协，具体机制应当允许等价实现。**

这是我对你的核心观念唯一比较重要的修正。

------

# 四、当前最主要的问题

## 1. `evals/cases.toml` 目前只是“评测规格”，还不是“评测系统”

这是目前最大的缺口。

你已经定义了：

- 12 个案例；
- `default_repetitions = 5`；
- compliance、task success、unnecessary abstraction 等指标；
- 每个案例的 pass criteria 和 fail criteria。

这些设计得不错，但仓库里没有：

- 调用 `codex exec --json` 的 runner；
- 捕获 Agent trajectory 的逻辑；
- 真实 fixture repository；
- deterministic grader；
- rubric grader；
- skill 是否实际触发的检查；
- 运行结果；
- 无 skill baseline；
- explicit 与 implicit invocation 对照；
- 回归趋势。

OpenAI 对 agent skill eval 的定义是：

```text
prompt
→ captured trace + generated artifacts
→ deterministic / rubric checks
→ comparable score
```

并明确建议同时测试 explicit invocation、implicit invocation 和 negative control。([developers.openai.com](https://developers.openai.com/blog/eval-skills))

因此你目前的 `cases.toml` 更准确的名字是：

```text
eval specification
```

而不是已经可运行的 eval suite。

### 现有案例还有一个问题：答案给得太明显

例如：

```text
Only 20% of runtime is parallelizable. Use 64 workers.
```

setup 已经直接告诉模型只有 20% 可并行，正确答案当然很容易变成 Amdahl 1.25x。

更真实的评测应该给它：

- 一个 profile JSON；
- 一段实际代码；
- 一份运行日志；
- 一个已有 repository；

让它自己发现只有 20% 可并行。

否则测到的是“能否复述 SKILL.md”，而不是“能否在复杂代码环境中贯彻原则”。

------

## 2. 现在还没有真正解决“Agent 为什么经常不遵循 skill”

当前 `description` 已经比很多 skill 清晰，但范围仍然很宽：

- create；
- modify；
- audit；
- optimize；
- preprocessing；
- feature；
- statistics；
- evaluation；
- visualization；
- long-running computation。

而官方说明里，`description` 是 implicit invocation 的主要触发信号，且建议 skill 尽量聚焦一个明确工作。([developers.openai.com](https://developers.openai.com/codex/build-skills))

你现在依靠：

```yaml
allow_implicit_invocation: true
```

但没有实测：

- 中文提示能否触发；
- “优化科研代码”是否触发；
- “修改一个 reusable numerical library”是否错误触发；
- “修改机器人 simulator”是否错误触发；
- 仅仅出现 `permutation` 一词时是否过度触发；
- Agent 是否真的读取了对应 reference。

更重要的是，`default_prompt` 写的是：

```text
implement this scientific pipeline task with explicit stages,
artifacts, and a scientific diff
```

这会在某些任务上过度施加架构：

- `AUDIT_STAGE` 不一定要 implement；
- `CREATE_VIEW` 不一定要创建新 Stage；
- `INFRASTRUCTURE` 明确不应被强制 artifact 化；
- 修改现有 legacy 项目时，不应该顺手重构整套 pipeline。

建议改成：

```yaml
default_prompt: >-
  Use $scientific-coding. First apply the scope gate and classify the task.
  Read the required reference before editing. Follow only the applicable
  workflow, make the narrowest coherent change, run the relevant checks,
  and report the scientific diff. Do not impose the artifact architecture
  on out-of-scope or unrelated code.
```

------

## 3. 最重要的规则不能只依赖 skill 自动触发

如果某些规则是你希望 Agent 在某个科研仓库里**每次都遵守**的，那么只放在 optional skill 里并不够。

Codex 当前会在开始工作前加载适用的 `AGENTS.md`；官方也把它定位为存放 repo layout、测试命令、工程约束和 Definition of Done 的地方。([developers.openai.com](https://developers.openai.com/codex/agent-configuration/agents-md?utm_source=chatgpt.com))

最稳妥的结构应该是：

```text
AGENTS.md
    ↓ 强制触发和少数不可妥协规则

$scientific-coding
    ↓ 完整方法论与任务路由

deterministic tools
    ↓ linter / artifact verification / schema validation

eval harness
    ↓ 证明它确实有效
```

例如科研项目根目录放一个很短的 `AGENTS.md`：

```md
## Scientific pipeline work

For changes under `stages/`, `analysis/`, `figures/`, or `artifacts/`,
invoke `$scientific-coding` before editing.

Do not apply it automatically to reusable libraries, simulation engines,
dataset SDKs, infrastructure, or production services.

Before completion, run:

python <skill-dir>/scripts/scientific_code_lint.py . --changed-only

Always report whether scientific behavior, sample inclusion, randomness,
or artifact semantics changed.
```

这样即使 implicit skill routing 偶尔失败，关键入口仍然存在。

------

# 五、Linter 的具体优点与问题

## 优点

当前 linter 有几个设计方向是对的：

- 无第三方依赖；
- AST 而不是简单 grep；
- hard errors 和 heuristic warnings 分开；
- warnings 可以带理由局部 suppress；
- JSON 输出；
- 检查 stage import、view import、网络输入、mutation、checkpoint、优化报告；
- 对 artifact hash 和 approval 有实际验证逻辑。

但它当前还不能承担“确定性规范执行层”这个强定位。

## 1. `SC102` 和 `SC103` 与 Scope Gate 直接冲突

代码中：

- generic module warning；
- Factory、Registry、Manager、Adapter、Context、Plugin 等 class warning；

是在 `stage` / `view` 条件块之外执行的。

也就是说，只要扫描到：

```python
class ConnectionManager:
    ...
```

哪怕它位于合法的基础设施模块，也会产生 `SC102`。

同样，一个完全合理的基础设施 `utils.py` 也会产生 `SC103`。

但 `SKILL.md` 又明确说：

> 不要把这套架构强加给基础设施、parser、SDK、production service。

这是一个明确的内部矛盾。

### 建议

只有在以下条件之一成立时才运行 SC102/SC103：

- 文件显式包含 `# scientific-code: stage`；
- 文件位于配置过的 scientific roots；
- 文件已经被确定为 stage 或 view；
- 用户显式要求对整个 repository 做 architecture audit。

而不是对所有 Python 文件生效。

------

## 2. Stage 检测既容易漏报，也可能误报

当前 Stage 主要通过以下方式识别：

- 路径中存在 `stage` 或 `stages`；
- 文件包含 marker；
- 顶层文件名匹配 `preprocess_*`、`analysis_*` 等。

这会漏掉例如：

```text
src/pipeline/neural_features.py
research/encoding_model.py
experiments/subject_level_cv.py
```

同时也可能把名为 `stages` 的普通第三方 package import 当成 Stage import。

### 建议

增加项目级配置：

```toml
[scope]
stage_roots = ["research/stages", "analysis"]
view_roots = ["research/views", "figures"]
artifact_roots = ["artifacts"]
infrastructure_roots = ["src/core", "src/runtime"]
```

显式 marker 应当比文件名猜测具有更高置信度。

------

## 3. 某些 “hard error” 实际上只是启发式判断

例如 `SC002`：

```text
Stage 定义超过两个 CLI 参数
→ hard error
```

但是 AST 并不知道这些参数是：

- 科学参数；
- `--config`；
- `--log-level`；
- `--dry-run`；
- `--output-dir`；
- 调度和资源参数。

因此它不能机械地证明这是科学错误。

建议改成：

- 默认 warning；
- 如果参数名命中 `alpha`、`normalization`、`window`、`seed`、`split` 等科学参数，再升级；
- 或要求 stage 只接受 config path，但允许在 repo config 中声明 operational CLI allowlist。

真正的 hard error 应该具有极高精度，例如：

- 已批准 Artifact 的文件 hash 确实变化；
- manifest path 逃逸；
- 明确标记的 Stage 导入另一个明确标记的 Stage；
- input artifact hash 确实不一致。

------

## 4. `SC108` 对 docstring 的判断太脆弱

它通过检查 docstring 是否出现这些英文词：

```text
input / parameters
processing / transformation / method / procedure
output / returns
mutation / side effects
```

来判断 scientific contract 是否完整。

因此以下情况都会产生误报：

- 中文 docstring；
- NumPy style 使用 `Parameters` 但方法描述没有写 `transformation`；
- Google style 使用 `Args`；
- 已经写清楚算法，但没出现规定关键词；
- 使用数学表达直接描述变换。

建议：

- SC108 默认改成低优先级 warning；
- 支持 NumPy、Google、Sphinx 和中文标题；
- 更重要的是检查 Stage 级 module docstring，而不是强迫每个函数都重复完整 contract；
- 允许项目配置 `docstring_contract = "module" | "function" | "off"`。

------

## 5. `SC105` 很容易被形式化绕过

当前 optimization report 的匹配逻辑主要只是读取：

```json
{
  "stage": "permutation_analysis"
}
```

只要存在一个 stage 名字匹配的 `optimization_report.json`，就可以覆盖 SC105。它并不验证：

- before/after 是否同一 workload；
- `pipeline_speedup` 是否等于两者比值；
- git commit 是否对应当前代码；
- correctness result 是否真实存在；
- profile fraction 是否有效；
- report 是否还是模板内容。

因此它目前验证的是：

> “有没有一份叫 optimization report 的文件”

而不是：

> “有没有有效的端到端优化证据”。

需要 JSON Schema 和 cross-field validation。

------

## 6. `--changed-only` 不适合直接用于干净的 CI checkout

它当前基于：

```bash
git diff HEAD
git ls-files --others
```

因此主要找到的是工作区未提交修改和 untracked files。

在 PR 的干净 CI checkout 中，代码已经提交，工作区可能完全 clean，于是可能检查到 0 个 Python 文件。

建议增加：

```bash
--base-ref origin/main
--diff-range <merge-base>...HEAD
--all
```

并在 CI 中显式使用 merge base。

------

## 7. Artifact 验证和代码 lint 不应绑在同一个默认命令里

目前 linter 对每个 approved artifact 的每个 tracked file 重新计算完整 SHA-256。

如果 Artifact 是：

- 500 GB 的 `.npy`；
- 数 TB 的视频数据；
- Zarr store；
- 远程对象存储；
- 大型模型 checkpoint；

那么每次运行 code lint 都重新扫描全部数据，会极其昂贵。这反而违背了 skill 自己的端到端性能原则。

虽然提供了：

```bash
--no-artifact-checks
```

但这会让核心完整性保证变成一个容易被常态跳过的选项。

更合理的是拆成：

```text
scientific-code lint
scientific-artifact verify
scientific-artifact verify --full
scientific-artifact verify --referenced
```

代码 lint 默认验证：

- schema；
- path；
- metadata consistency；
- manifest references。

完整 payload hash 由单独命令按目标 Artifact 执行。

------

## 8. 外部 input Artifact 的真实内容没有被重新验证

`run.json` 中的 input artifact 可以指向项目根目录外的路径。当前逻辑会读取它的：

- `manifest.json`；
- `approval.json`；
- manifest 中声明的 hash；

然后比较这些元数据，但不会重新 hash 该外部 Artifact 的真实 payload。

如果外部 Artifact 的数据文件被修改，但 manifest 和 approval 没变，而该目录又不在本次 root scan 中，就可能通过。

应当调用同一个 Artifact verifier 对每一个 recorded input 做完整或受信任级别的验证。

------

# 六、Artifact 体系的不足

## 1. 当前要求 Agent 手写太多容易出错的 metadata

Skill 要求 Agent 正确完成：

- 临时目录；
- 原子写入；
- data hash；
- contract hash；
- artifact hash；
- run record；
- runtime record；
- manifest hash；
- approval binding；
- input validation。

但仓库只提供模板，没有提供真正的生成和 finalize 工具。

这是一个典型的情况：

> 规范是正确的，但把最容易出错的工作留给了语言模型。

建议增加一个无第三方依赖的小型 CLI：

```bash
scientific-artifact init
scientific-artifact finalize
scientific-artifact verify
scientific-artifact approve
scientific-artifact diff-contract
scientific-artifact lineage
```

让 Agent 调命令，而不是自己重写哈希协议。

## 2. `approval.json` 现在只是声明，不是真正的 Human Approval

当前模板中：

```json
{
  "status": "approved",
  "reviewed_by": "researcher_id"
}
```

任何程序或 Agent 都可以生成。

所以当前实现保证的是：

- approval record 与 artifact hash 一致；

但不能保证：

- 真的是某个人审批；
- reviewer identity 可信；
- Agent 没有自己把结果标成 approved。

需要明确写入 Non-Negotiable Rule：

> Agent 不得自行创建 `status = approved` 的记录。Agent 只能生成 review packet；只有用户显式执行 approval 操作或外部审批系统返回认证结果后，才能批准。

而且 approval 模板默认状态不应是 `approved`，应当是：

```json
{
  "status": "pending_review"
}
```

对于一般研究项目，不一定需要上密码学签名；但必须区分：

```text
完整性 integrity
≠
审批真实性 authenticity
```

## 3. 线性单输入模型不足以表示真实科研 DAG

当前抽象是：

```text
A(i+1) = S(i)(A(i), C(i))
```

pipeline template 也是单个：

```toml
input_contract = "ProcessedDatasetV1"
output_contract = "AnalysisResultV1"
```

但真实 Stage 经常需要：

- neural features；
- behavioral labels；
- subject metadata；
- split definitions；
- mapping artifacts；
- camera calibration；
- pretrained checkpoint；

多个输入共同产生一个输出。

更合理的模型是：

```text
A_out = S({name_k: A_in,k}, C_resolved, D_design)
```

配置可以变成：

```toml
[[stage.input]]
name = "features"
contract = "NeuralFeatureV2"

[[stage.input]]
name = "behavior"
contract = "BehaviorLabelV1"

[[stage.input]]
name = "splits"
contract = "SubjectSplitV3"
```

否则 Agent 容易为了适配单输入模型，把多个语义完全不同的对象塞进一个 mega-artifact。

## 4. Stable sample ID 还不足以表达多对一和一对多 lineage

Exclusion ledger 很好，但只能清楚表达“哪些样本被删除”。

它不完整覆盖：

- 多个 trial 聚合为一个 subject statistic；
- 一个视频切成多个 clip；
- 多个传感器窗口映射到一个训练样本；
- resampling 后一个输出依赖多个输入；
- mapping 复制同一个 source trial 多次；
- augmentation 产生派生样本。

需要增加可选的 `lineage.parquet`：

```text
output_id
input_id
relation
weight
operation
```

至少支持：

```text
derived_from
aggregated_from
windowed_from
replicated_from
joined_with
```

这对于你之前关注的 permutation 独立单位和重复 mapping 问题尤其重要。

## 5. Approved-only 模式对探索阶段过于严格

正式 pipeline 下游只消费 approved artifact 是合理的。

但科研过程还有大量：

- 调试；
- 探索；
- sanity check；
- 小规模 prototype；
- 超参数试验；
- 临时可视化。

如果每个边界都要求人类审批，系统很快会变成形式主义，研究者最终会绕过它。

建议定义三个运行等级：

```text
exploratory
formal
release
```

其中：

| 模式        | 行为                                                       |
| ----------- | ---------------------------------------------------------- |
| exploratory | 允许未批准输入，但输出必须标记为 tainted，不得进入正式结论 |
| formal      | contract、provenance 和机器验证完整，关键边界要求审批      |
| release     | 全量验证、冻结、可选签名，用于论文或共享结果               |

View 也可分为：

- exploratory view：允许临时计算，但不能成为正式下游输入；
- formal view：只能消费正式分析 Artifact，presentation-only。

## 6. 大型 Artifact 和对象存储没有纳入模型

完整 SHA-256 适合中小型本地 Artifact，但不总适合：

- 大规模视频；
- Zarr；
- S3/OSS；
- 版本化数据湖；
- 数 TB checkpoint。

建议支持：

```toml
integrity_mode = "full_sha256"
integrity_mode = "chunked_merkle"
integrity_mode = "object_version"
integrity_mode = "trusted_external"
```

并明确不同模式提供的保证等级。

------

# 七、方法论上还缺少的一层：真正的科学有效性

Skill 把：

```text
Scientific correctness
```

放在第一优先级。

但当前大部分规则实际保护的是：

- 方法实现没有被悄悄改变；
- 数据血缘清楚；
- 结果可复现；
- 架构可审计。

这些不等于方法本身科学上正确。

例如当前 skill 并不能系统检查：

- train/test leakage；
- preprocessing 是否在 fold 外 fit；
- permutation exchangeability；
- bootstrap unit 是否对应独立统计单位；
- repeated measures 是否被当作独立样本；
- subject-level split；
- nested CV；
- multiple comparison；
- pseudo-replication；
- model selection 与最终评估是否混用。

Stage 文档在测试示例里提到了一部分，但尚未形成工作流。

这里有两个选择。

### 选择 A：缩小声明

把第一项改成：

```text
Preservation of declared scientific semantics
```

也就是 skill 保证实现忠实、可审计，但不声称能验证整个科学设计。

### 选择 B：增加一个可选 reference

增加：

```text
references/statistical_validity.md
```

或者单独的：

```text
AUDIT_RESAMPLING
AUDIT_EVALUATION_DESIGN
```

至少要求 Agent 明确：

```text
observation unit
sampling unit
independent statistical unit
split unit
permutation unit
bootstrap unit
aggregation unit
```

我更推荐 B，因为这是你的 skill 真正可以形成独特价值的方向。

------

# 八、应当优先修改什么

## P0：让它从“好规范”变成“可验证的 skill”

### 1. 建立真实 eval harness

至少支持：

```text
explicit invocation
implicit invocation
negative control
without-skill baseline
```

每次运行保存：

```text
prompt
repository fixture
JSONL trajectory
generated diff
linter output
rubric score
token/command count
```

加入中文和英文 prompt。

现有 12 个 case 可以保留，但要补充：

- 不应触发：reusable numerical library；
- 不应触发：simulation engine；
- 不应触发：parser / dataset SDK；
- 不应把现有 Hydra/YAML 项目强制迁移成 TOML；
- 应当允许提取真正稳定的科学概念；
- 10 分钟任务但每天运行 1000 次，优化可能值得；
- 20 分钟任务但节点高频抢占，checkpoint 可能值得；
- formal view 与 exploratory view；
- nested CV leakage；
- repeated mapping permutation；
- 中文隐式触发。

### 2. 增加真实 fixture repository

模板不能替代工作示例。

建议提供：

```text
examples/minimal_pipeline/
├── AGENTS.md
├── configs/
├── stages/
├── artifacts/
├── views/
└── tests/
```

包含一次完整流程：

```text
raw artifact
→ preprocessing
→ exclusion ledger
→ analysis
→ approval
→ formal figure
```

官方 skill 指南也明确建议提供 working example 或 good result，而不是只靠抽象说明。([developers.openai.com](https://developers.openai.com/codex/use-cases/reusable-codex-skills))

### 3. 拆分 code lint 和 artifact verify

这是最重要的工具层重构。

### 4. 为 linter 写自测

仓库 README 说当前版本通过了 linter isolation behavior tests，但目录中没有相应测试代码、CI workflow 或保存的结果，因此外部使用者无法从仓库独立复现这项声明。

至少为每个 `SCxxx` 提供：

```text
positive fixture
negative fixture
false-positive regression fixture
suppression fixture
```

------

## P1：降低形式主义和迁移成本

### 1. 把规则分成三层

```text
MUST
SHOULD
MAY
```

MUST 只保留少数科学不变量。

### 2. 明确 legacy repository 策略

加入一句非常重要的规则：

> 使用本 skill 修改现有项目，不代表自动把整个项目迁移为本架构。除非用户明确要求，只对当前科学边界做最小一致修改，并报告未迁移的结构风险。

否则 Agent 很容易借一次小改动创建：

```text
artifacts/
contracts/
pipeline.toml
approval.json
orchestrator/
```

把小任务扩大成架构迁移。

### 3. 区分 scientific inputs 和 execution inputs

当前“科学输入只能是 artifact + config + code”的方向是对的，但需要显式允许：

```text
SLURM_JOB_ID
CUDA_VISIBLE_DEVICES
worker count
cache directory
credentials
temporary directory
```

作为 execution-plane 输入，只要它们：

- 不改变科学语义；
- 被记录；
- 不偷偷改变样本、算法或随机设计。

可以明确成：

```text
Scientific plane:
artifacts + resolved config + code + experiment-design artifacts

Execution plane:
hardware + workers + scheduler + cache + credentials + runtime paths
```

### 4. TOML 改为新项目默认，而不是普遍强制迁移

真正应该不可妥协的是：

- resolved config 必须完整；
- 必须 snapshot；
- 必须 hash；
- 不能有未记录的 override。

至于作者使用 TOML、YAML、Python dataclass 还是已有 Hydra 项目，应当适配上下文。

------

## P2：增强正式发布能力

包括：

- approval 外部认证或签名；
- object-store version binding；
- Merkle/chunk hashing；
- Artifact catalog；
- contract semantic diff CLI；
- environment lock/container digest；
- Git dirty state 和 patch hash；
- superseded/rejected/frozen 状态机；
- 发布为 plugin。

当前官方文档对本地 skill 更推荐 `.agents/skills`，但另一份官方 use case 仍然提到 `~/.codex/skills`。README 最好同时说明当前推荐路径和兼容路径，而不是只写 `$CODEX_HOME/skills`。([developers.openai.com](https://developers.openai.com/codex/build-skills))

------

# 九、我建议的下一版目录

```text
scientific-coding/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── stage.md
│   ├── artifact.md
│   ├── lineage.md
│   ├── statistical_validity.md
│   ├── view.md
│   ├── optimization.md
│   ├── resumability.md
│   └── audit.md
├── schemas/
│   ├── artifact_manifest.schema.json
│   ├── run_manifest.schema.json
│   ├── approval.schema.json
│   └── optimization_report.schema.json
├── templates/
├── scripts/
│   ├── scientific_code_lint.py
│   ├── scientific_artifact.py
│   └── scientific_diff.py
├── examples/
│   └── minimal_pipeline/
├── tests/
│   ├── test_linter.py
│   ├── test_artifact.py
│   └── fixtures/
└── evals/
    ├── prompts.csv
    ├── fixtures/
    ├── run_evals.py
    ├── graders.py
    ├── rubric.schema.json
    └── baselines/
```

------

# 十、最终结论

我认同你的核心判断：

> **科研流水线不应该优先优化软件工程意义上的优雅，而应该优先优化科学方法的可见性、可追踪性和研究迭代效率。**

这个 skill 最大的优点是，它已经把这个观念从抽象理念落实到了：

- Stage 边界；
- Artifact contract；
- sample lineage；
- scientific diff；
- formal view；
- optimization；
- resumability；
- audit checklist。

它目前最大的不足不是观念错误，而是：

> **仍然把太多关键正确性寄托在 Agent 自觉遵循文档上。**

下一步不应该继续大幅增加原则，而应当把现有原则压缩成更少的真正不变量，并通过：

```text
AGENTS.md 强制入口
+ 更精确的 Skill routing
+ Artifact CLI
+ Schema
+ 高精度 linter
+ 可运行 trajectory evals
```

形成闭环。

最值得优先完成的不是再写一篇 reference，而是：

> **让 `evals/cases.toml` 真正跑起来，并证明使用这个 skill 相比不用 skill，确实显著降低了科学分支隐藏、无意义抽象、错误优化和无必要 checkpoint 的发生率。**