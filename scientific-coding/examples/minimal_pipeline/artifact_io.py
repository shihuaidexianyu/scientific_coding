"""为示例提供明确的配置读取、序列化、产物发布和外部读取边界。

输入文件与配置
--------------
各调用方提供 TOML 配置、契约路径、已计算的 CSV/JSON 字节或外部产物目录。
科学参数分别位于 configs/acquire_data.toml、configs/preprocess.toml、configs/analyze.toml；
本模块解析配置，不解释或重复校验各阶段的科学参数约束。
PROJECT_ROOT 为本文件所在目录。SCIENTIFIC_CODING_SCRIPTS 仅定位共享产物工具，
不选择科学方法；它是执行环境设置，不进入科学配置。

处理逻辑
--------
序列化时保留字段和行顺序；在私有暂存目录写完整文件，再封存哈希并发布。
读取外部产物时校验实际字节和契约一次，然后转换声明的数值字段。

输出文件
--------
发布函数写调用方给定的数据文件，以及 artifact_contract.toml、config.toml、
run.json、manifest.json；只有显式评审点才额外生成待评审记录。
其余序列化函数返回 bytes，读取函数返回字典或行列表；不执行科学计算。
"""

# 标准库负责文件读写、执行环境记录和共享工具定位。
import contextlib
import csv
import io
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile
import time
import tomllib

# 数据及配置路径以本文件所在项目为基准，不随终端工作目录改变。
PROJECT_ROOT = Path(__file__).resolve().parent

# 仅在模块加载时定位一次已安装 skill 的共享产物工具。
_candidates = [Path(os.environ["SCIENTIFIC_CODING_SCRIPTS"])] if "SCIENTIFIC_CODING_SCRIPTS" in os.environ else []
for parent in (PROJECT_ROOT, *PROJECT_ROOT.parents):
    _candidates.extend([
        parent / "scripts",
        parent / ".agents/skills/scientific-coding/scripts",
        parent / ".claude/skills/scientific-coding/scripts",
    ])
TOOL_DIR = next((p for p in _candidates if (p / "scientific_artifact.py").is_file()), None)
if TOOL_DIR is None:
    raise RuntimeError("Set SCIENTIFIC_CODING_SCRIPTS to this skill's scripts directory")
sys.path.insert(0, str(TOOL_DIR))
import scientific_artifact as artifact_tool
import scientific_code_lint as integrity


def read_config(path: Path) -> dict:
    """读取一份 TOML 配置，交由所属阶段解释科学约束。

    参数
    ----
    path : Path
        UTF-8 TOML 文件路径；相对路径按当前工作目录打开。
        具体字段由调用方所用的科学配置或编排配置定义。

    处理逻辑
    --------
    读取文本并解析 TOML 语法，不重复实施后续阶段的科学参数检查。

    产物
    ----
    config : dict
        TOML 解析后的字典；配置节为嵌套字典，各值保持 TOML 对应的类型。
        例如 {"seed": 20260904, "n_trials_per_condition": 40}。

    副作用
    ------
    读取一份文件，不修改它；语法或读取错误由解析器和文件 API 报出。
    """

    # TOML 解析器负责语法与类型解析，辅助函数不重复检查。
    return tomllib.loads(path.read_text(encoding="utf-8"))


def csv_bytes(rows: list[dict], columns: list[str]) -> bytes:
    """把已声明的记录表序列化为 UTF-8 CSV 字节。

    参数
    ----
    rows : list[dict]
        每个字典是一行，键对应 columns；值为该表已确定的字符串或数值。
        可以为空列表，此时只输出表头；行顺序有意义并原样保留。

    columns : list[str]
        字段名列表，决定 CSV 列顺序；例如 ["trial_id", "condition", "amplitude_uv"]。

    处理逻辑
    --------
    建立内存文本缓冲区，按列名写表头和各行，以换行符分隔记录，再编码为 UTF-8。

    产物
    ----
    content : bytes
        含一行表头和 N 行数据的 CSV 文件内容，不额外添加数据框索引列。

    副作用
    ------
    不写磁盘、不修改 rows；序列化不重复检查生产者已建立的行级科学保证。
    """

    # 保持行列顺序，明确使用换行符分隔记录。
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def json_bytes(value: dict) -> bytes:
    """把结果或来源字典编码为格式稳定的 JSON 字节。

    参数
    ----
    value : dict
        可 JSON 序列化的字段字典，值可含字符串、数值、列表、嵌套字典及 None。
        科学结果字段由结果契约定义，来源字段由发布函数定义；数值不得为非有限数。

    处理逻辑
    --------
    按现有字段顺序序列化，保留中文、使用缩进并追加换行，编码为 UTF-8。
    由标准序列化器拒绝 JSON 不支持的非有限数。

    产物
    ----
    content : bytes
        可直接写入 .json 文件的 UTF-8 内容，根节点为对象。

    副作用
    ------
    不读写磁盘，不修改 value。
    """

    # 由序列化器拒绝非有限数，避免生成非标准 JSON。
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def binding_for(directory: Path, manifest: dict) -> dict:
    """从已有 manifest 构造轻量的产物来源绑定。

    参数
    ----
    directory : Path
        已发布产物目录，用于生成相对项目根目录的路径。

    manifest : dict
        封存或外部核验已获得的 manifest；含 contract 字典（name 为字符串，version 为整数），
        以及 artifact_hash、manifest_hash 两个字符串字段。

    处理逻辑
    --------
    将目录转为相对路径，从现有 manifest 提取契约名称、版本和两个哈希。

    产物
    ----
    binding : dict
        包含 path、contract、artifact_hash、manifest_hash 的字典；各值为字符串。
        path 相对项目根目录，contract 形如 RawTrials@1，两个哈希分别绑定数据身份和完整记录。

    副作用
    ------
    不读写文件、不修改 manifest，也不重新散列数据。
    """

    # 绑定数据内容和来源；路径尽可能相对项目根目录记录。
    path = os.path.relpath(directory, PROJECT_ROOT).replace("\\", "/")
    return {
        "path": path,
        "contract": f"{manifest['contract']['name']}@{manifest['contract']['version']}",
        "artifact_hash": manifest["artifact_hash"],
        "manifest_hash": manifest["manifest_hash"],
    }


def publish_payload(payloads: dict[str, bytes], contract_path: Path,
                    config_path: Path, script_path: Path, output_dir: Path,
                    inputs: list[dict], *, config_values: dict, review_required: bool = False) -> dict:
    """将完整数据和来源封存后发布到新目录。

    参数
    ----
    payloads : dict[str, bytes]
        数据相对路径到完整文件字节的映射，例如 {"result.json": b"..."}。
        路径由本示例的阶段代码构造，指向新产物内部；生产者已建立数据不变量。

    contract_path : Path
        该结果的中文 TOML 契约模板路径，包含数据结构、语义和读取说明。

    config_path : Path
        本次实际使用的科学 TOML 配置路径，复制到新产物的 config.toml。

    script_path : Path
        生产该数据的阶段 Python 源文件路径，用于记录实际源码哈希和阶段名称。

    output_dir : Path
        尚不存在的新产物目标目录；暂存目录建立在它的父目录中。

    inputs : list[dict]
        本次消费的输入绑定列表；每项含 path、contract、artifact_hash、
        manifest_hash 字符串，可另含 role 描述输入角色；采集阶段使用空列表。

    config_values : dict
        调用方已解析并使用的有效配置，键值结构与 config_path 对应。
        原样写入 run.json 的 effective_config，不再次读取或校验同一配置。

    review_required : bool
        默认 False；只有用户选定此产物为暂停点时才写待评审记录。

    处理逻辑
    --------
    1. 建立私有暂存目录，写数据、契约、配置副本及真实来源信息。
    2. 调用一次封存工具绑定文件哈希，不重复扫描生产者已保证的行级事实。
    3. 将完整暂存目录重命名为目标目录；失败时只清理自己的暂存目录。

    产物
    ----
    binding : dict
        包含 path、contract、artifact_hash、manifest_hash 的字典；各值为字符串。
        path 相对项目根目录，contract 形如 RawTrials@1，两个哈希分别绑定数据身份和完整记录。
        output_dir 中保留 payloads 的文件，以及契约、配置、run.json、manifest.json。

    副作用
    ------
    创建上述新目录及文件；不覆盖已有产物，不修改调用方对象。
    记录时间属于来源元数据，不作为阶段运行耗时的测量。
    """

    # 开始写入前拒绝覆盖；发布时的重命名也不替换已有目录。
    if output_dir.exists():
        raise FileExistsError(f"Choose a fresh output directory: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=output_dir.parent))
    try:

        # 将已经算好的数据与同步维护的结构说明写入暂存目录。
        for relative, content in payloads.items():
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        shutil.copyfile(contract_path, staging / "artifact_contract.toml")
        shutil.copyfile(config_path, staging / "config.toml")

        # 记录实际源码、输入绑定、有效配置与执行环境。
        record = {
            "schema_version": 1,
            "run_id": os.path.relpath(output_dir, PROJECT_ROOT).replace("\\", "/"),
            "stage": script_path.stem,
            "config": {"path": "config.toml", "sha256": integrity.sha256_file(config_path)},
            "code": {"path": str(script_path.relative_to(PROJECT_ROOT)), "sha256": integrity.sha256_file(script_path)},
            "execution_code_sha256": integrity.sha256_file(Path(__file__)),
            "input_artifacts": inputs,
            "python_version": platform.python_version(),
            "library_versions": {"standard_library": platform.python_version()},
            "hardware": {"machine": platform.machine(), "processor": platform.processor()},
            "effective_config": config_values,
            "randomness": {"seed": config_values.get("seed")},
            "recorded_at_unix_s": time.time(),
        }
        (staging / "run.json").write_bytes(json_bytes(record))

        # 封存文件字节和声明的元数据；生产者已建立行级数据保证。
        args = ["finalize", str(staging)]
        if review_required:
            args.append("--request-review")
        with contextlib.redirect_stdout(io.StringIO()):
            status = artifact_tool.run(args)
        if status:
            raise ValueError("Artifact finalization failed; no result was published")
        manifest = integrity.load_json(staging / "manifest.json")

        # 直接使用内存中的封存清单；重命名后不再次计算相同哈希。
        staging.rename(output_dir)
        return binding_for(output_dir, manifest)
    finally:

        # 发布失败时仅清理本函数创建的私有暂存目录。
        if staging.exists():
            shutil.rmtree(staging)


def load_external_artifact(directory: Path, expected_contract: str) -> tuple[object, dict]:
    """一次验证外部保存结果，并按契约读入内存。

    参数
    ----
    directory : Path
        外部产物目录，包含 manifest.json、artifact_contract.toml 和被追踪的数据文件。

    expected_contract : str
        消费方要求的确切契约，形如 RawTrials@1、ProcessedTrials@1 或 AnalysisResult@1。

    处理逻辑
    --------
    1. 核验实际字节、清单和声明的基础 CSV/JSON 结构。
    2. 匹配消费方契约，只在产物已声明评审要求时检查对应决定。
    3. 根据 data.columns 把 CSV 数值列转换一次；JSON 保持其解析类型。

    产物
    ----
    data : list[dict] 或 dict
        RawTrials@1 或 ProcessedTrials@1 返回长度为 N 的试次行列表：
        每行 trial_id 为唯一字符串，condition 为 control 或 treatment 字符串，
        amplitude_uv 为有限 float，单位为微伏；沿用文件顺序。

        AnalysisResult@1 返回标量字典：control_mean_uv、treatment_mean_uv、
        difference_uv、ci_low_uv、ci_high_uv 为微伏浮点数；
        n_control、n_treatment 为试次数整数，n_bootstrap、seed 为整数，
        confidence_level 为区间概率浮点数，method 为方法说明字符串。
        CSV 的字段转换由 data.columns 声明；JSON 保持解析后的类型。

    binding : dict
        包含 path、contract、artifact_hash、manifest_hash 的字典；各值为字符串。
        path 相对项目根目录，contract 与 expected_contract 一致。
        artifact_hash 绑定数据身份，manifest_hash 绑定完整清单记录。

    副作用
    ------
    读取并散列外部文件，不修改产物；核验或契约不匹配时抛出明确异常。
    """

    # 外部文件可能已被修改，因此在进入流程的此处核验一次。
    collector = integrity.IssueCollector(directory, {})
    manifest = integrity.verify_artifact_dir(directory, collector, full=True)
    if collector.issues:
        raise ValueError("; ".join(issue.message for issue in collector.issues))
    binding = binding_for(directory, manifest)
    if binding["contract"] != expected_contract:
        raise ValueError(f"Expected {expected_contract}, got {binding['contract']}")
    if not integrity.review_satisfied(directory, manifest):
        raise ValueError("This input awaits the user-selected human review")

    # 按已核验的字段声明转换 CSV 数值；JSON 保留解析后的类型。
    contract = read_config(directory / "artifact_contract.toml")
    data = contract["data"]
    path = directory / data["path"]
    if data["format"] == "json":
        return integrity.load_json(path), binding
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        for key, kind in data["columns"].items():
            if kind.startswith("float"):
                row[key] = float(row[key])
            elif kind.startswith("int"):
                row[key] = int(row[key])
    return rows, binding
