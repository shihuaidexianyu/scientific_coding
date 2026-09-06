"""
在示例的进程启动边界保存日志、阶段进度、资源记录和独立实验索引。

文件流程
--------
命令 + 来源字典 --> 新 attempts/<编号> --> 子进程 stdout/stderr --> run.log
                                            |
子进程阶段通知 --> progress.json ------------+
                                            v
                                execution.json + index/<编号>.json

输入与配置
----------
父进程接收命令列表、当前工作目录和已知来源；不解析科学 TOML。
子进程只通过 SCIENTIFIC_EXECUTION_DIR 获取本次记录目录，不据此改变科学方法。
pipeline.py 提供实验名、配置路径和需保留的源码路径列表；本模块在启动前
保存源码，artifact_io 在配置读取时保存字节，并在外部输入核验后保留已有绑定。

加工与产物
----------
完整输出直接重定向到文件，保留 Python 以及继承输出描述符的子进程输出。
尝试记录在启动前写 running，结束后记录真实退出码、时刻和阶段数据。
每次索引独占一个文件，避免并发追加同一文件；科学产物单独发布。
墙钟时间由父进程测量，CPU 由示例工作进程测量。可用时读取进程寿命峰值 RSS；
本例每次 CLI 使用新进程。Windows 无 psutil 或不支持的系统记录未知原因。
本例没有 GPU 和并行科学子进程；资源值不声称覆盖通用进程树。
"""

# 记录器只负责进程与文件，不执行或复核科学计算。
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time
import traceback
import uuid


def save_snapshot(directory: Path, path: Path, content: bytes, kind: str) -> dict:
    """保留已读取文件的精确字节及来源索引，供失败后还原输入。

    参数
    ----
    directory : Path
        当前尝试目录，快照保存在其 snapshots 子目录。

    path : Path
        原文件路径，相对路径按当前工作目录解析后记录。

    content : bytes
        调用方已读取的完整文件字节，本函数不再次读取或验证原文件。

    kind : str
        code_at_launch 或 config_at_read，区分启动时源码与实际读取的配置。

    返回
    ----
    entry : dict
        origin 为原文件绝对路径字符串，sha256 为字节哈希，
        snapshot 为相对尝试目录的副本路径，kind 为传入来源角色。

    处理过程
    --------
    1. 对已在内存中的字节散列，保存副本及原路径描述。

    副作用
    ------
    写本尝试的快照文件与 JSON 索引，不改变原文件或解释配置值。
    """

    # 内容与原路径共同命名，避免同名配置及不同读取版本相互覆盖。
    digest = hashlib.sha256(content).hexdigest()
    identity = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:16]
    relative = f"snapshots/{kind}/{identity}_{digest}_{path.name}.snapshot"
    target = directory / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    entry = {"origin": str(path.resolve()), "sha256": digest, "snapshot": relative, "kind": kind}
    write_json(target.with_name(target.name + ".source.json"), entry)
    return entry


def write_json(path: Path, value: dict) -> None:
    """原子替换本次记录器独占的 JSON 文件。

    参数
    ----
    path : Path
        已存在父目录中的目标路径，相对路径按当前工作目录解析。

    value : dict
        JSON 可序列化的记录，字段结构由执行记录或阶段通知定义。

    返回
    ----
    None
        文件写入完成，无内存产物。

    处理过程
    --------
    1. 写同目录临时文件，再替换目标文件，防止读取半份 JSON。

    副作用
    ------
    写入 path；调用方保证本次尝试只有一个作者，不覆盖其他尝试。
    """

    # 每个记录文件只有所属进程写入，替换不跨文件系统。
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


class Progress:
    """工作进程的阶段观察器；所有状态仅用于记录，不控制科学执行。"""

    def __init__(self, directory: Path):
        """建立本次工作进程的阶段记录。

        参数
        ----
        directory : Path
            父进程已建立的尝试目录，供 progress.json 保存阶段状态。

        返回
        ----
        None
            初始化当前实例；data 内含 status、current_stage、stages 和 result_path。

        处理过程
        --------
        1. 记录 CPU 起点，建立空阶段列表；首个阶段由调用方明确指定。

        副作用
        ------
        暂不写文件，后续 enter/finish 才保存进度。
        """

        # 每个 CLI 尝试使用一个新工作进程，CPU 差值覆盖其编排与科学工作。
        self.path = directory / "progress.json"
        self.cpu_start = time.process_time()
        self.stage_start = time.perf_counter()
        self.data = {"status": "running", "current_stage": None, "stages": [], "result_path": None}
        self.data["environment"] = {"python": platform.python_version(), "system": platform.platform(),
                                    "processor": platform.processor() or None, "logical_cpus": os.cpu_count(),
                                    "scientific_workers": 1, "dependencies": {"standard_library": platform.python_version()}}

    def enter(self, name: str) -> None:
        """记录进入一个主要阶段，并完成上一阶段的计时。

        参数
        ----
        name : str
            编排器提供的阶段名，例如 analyze；仅说明执行位置。

        返回
        ----
        None
            更新内存与 progress.json，不返回科学数据。

        处理过程
        --------
        1. 若已有阶段，记录它从进入到此刻的墙钟秒数。
        2. 开始新阶段并写入当前名称，异常时可以定位最后进入的阶段。

        副作用
        ------
        替换本尝试的 progress.json，不检查输入或改变调用顺序。
        """

        # 阶段包括自己的读取、计算和发布开销；本例阶段顺序执行，不重叠。
        now = time.perf_counter()
        if self.data["current_stage"] is not None:
            self.data["stages"].append({"name": self.data["current_stage"],
                                        "wall_time_s": now - self.stage_start, "status": "completed"})
        self.data["current_stage"] = name
        self.stage_start = now
        write_json(self.path, self.data)
        print(f"进入阶段：{name}", flush=True)

    def finish(self, status: str) -> None:
        """保存最后阶段、工作进程 CPU 和可获得的峰值内存。

        参数
        ----
        status : str
            succeeded、paused 或 failed；由实际执行结果决定，不触发控制流程。

        返回
        ----
        None
            progress.json 增加 resources 字典：cpu_time_s 为本次 CPU 秒数，
            peak_ram_bytes 为进程寿命峰值 RSS 或 null，ram_note 解释口径或缺失。
            peak_vram_bytes 为 null，本例不使用 GPU。

        处理过程
        --------
        1. 保存当前阶段的耗时及完成/失败状态。
        2. 记录 CPU 差值和系统提供的进程峰值 RSS，再写入进度文件。

        副作用
        ------
        读取当前进程计数器并替换 progress.json，不重新遍历科学数据。
        """

        # 失败阶段也保留实际已经消耗的时间；暂停表示选定阶段已经完成。
        if self.data["current_stage"] is not None:
            self.data["stages"].append({"name": self.data["current_stage"],
                                        "wall_time_s": time.perf_counter() - self.stage_start,
                                        "status": "failed" if status == "failed" else "completed"})
        self.data["status"] = status
        resources = {"cpu_time_s": time.process_time() - self.cpu_start,
                     "cpu_scope": "工作进程本次编排区间，不含子进程 CPU",
                     "peak_ram_bytes": None, "ram_note": "当前系统未提供本示例使用的进程峰值接口",
                     "peak_vram_bytes": None, "vram_note": "本例不使用 GPU"}

        # Linux/macOS 的 ru_maxrss 单位不同；Windows 的可选 psutil 提供 peak_wset。
        try:
            if sys.platform in ("linux", "darwin"):
                import resource
                peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                resources["peak_ram_bytes"] = peak * (1 if sys.platform == "darwin" else 1024)
            elif sys.platform == "win32":
                import psutil
                self.data["environment"]["dependencies"]["psutil"] = psutil.__version__
                resources["peak_ram_bytes"] = psutil.Process().memory_info().peak_wset
            if resources["peak_ram_bytes"] is not None:
                resources["ram_note"] = "工作进程整个寿命的峰值 RSS，含导入；不含子进程，不是阶段增量"
        except (ImportError, OSError, AttributeError) as error:
            resources["ram_note"] = f"未能采集峰值 RSS：{type(error).__name__}；可使用调度器或安装 psutil 采集"
        self.data["resources"] = resources
        write_json(self.path, self.data)


def execute(command: list[str], directory: Path, cwd: Path, provenance: dict) -> tuple[int, Path]:
    """启动一次独立进程，完整保存输出、结果状态和实验索引。

    参数
    ----
    command : list[str]
        可执行文件及逐项参数，不经过 shell 展开，不应包含凭据。

    directory : Path
        记录父目录；每次创建 attempts/<UUID> 和 index/<UUID>.json。

    cwd : Path
        子进程实际工作目录，亦是其相对路径的解析基准。

    provenance : dict
        experiment_id 为可选实验标识，config_path 为实际配置路径字符串，
        source_paths 为启动前保存的源码路径字符串列表。输入来源由读取边界
        保存到 input_bindings，配置字节保存在 snapshots；已有阶段 run.json
        继续提供科学参数和来源，不在记录器中重新核验数据。

    返回
    ----
    exit_code : int
        子进程退出码；启动失败时为入口约定的 1，但记录中实际退出码保持 null。

    attempt : Path
        新尝试目录，含 run.log、execution.json，协作的工作进程另写 progress.json。
        execution.json 含 status、exit_code、started_at_utc、finished_at_utc、wall_time_s、
        command、cwd、provenance 和 progress；progress 的结构由 Progress 定义。

    处理过程
    --------
    1. 创建唯一目录及 running 记录，直接将子进程 stdout/stderr 重定向到日志。
    2. 等待真实退出；取消时结束所属进程树，保留日志。
    3. 结合子进程进度写终态和独立索引，返回真实退出结果。

    副作用
    ------
    执行 command 并写新记录；不覆盖旧尝试，不判断科学显著性。
    无法捕获记录器自身被强杀或掉电，此时保留未确认的 running 记录。
    """

    # 每次记录独占 UUID 文件，批量并发无需竞争同一个追加句柄。
    attempt = directory.resolve() / "attempts" / uuid.uuid4().hex
    attempt.mkdir(parents=True, exist_ok=False)
    index = directory.resolve() / "index" / (attempt.name + ".json")
    index.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    record = {"schema_version": 1, "attempt_id": attempt.name,
              "experiment_id": provenance.get("experiment_id"), "status": "running",
              "started_at_utc": datetime.now(timezone.utc).isoformat(), "finished_at_utc": None,
              "wall_time_s": None, "exit_code": None, "command": command, "cwd": str(cwd.resolve()),
              "provenance": provenance, "log_path": str(attempt / "run.log"),
              "record_path": str(attempt / "execution.json"), "scientific_outcome": "not_assessed"}
    write_json(attempt / "execution.json", record)
    write_json(index, record)
    print(f"运行日志：{attempt / 'run.log'}", flush=True)

    # 文件描述符级重定向保存完整输出；Python 输出统一 UTF-8，原生输出字节不改写。
    environment = {**os.environ, "SCIENTIFIC_EXECUTION_DIR": str(attempt),
                   "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    with (attempt / "run.log").open("wb") as log:
        try:
            record["code_at_launch"] = [save_snapshot(attempt, Path(path), Path(path).read_bytes(), "code_at_launch")
                                         for path in provenance.get("source_paths", [])]
            write_json(attempt / "execution.json", record)
            child = subprocess.Popen(command, cwd=cwd, env=environment, stdout=log, stderr=subprocess.STDOUT,
                                     start_new_session=os.name != "nt",
                                     creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
                                     if os.name == "nt" else 0)
        except OSError:
            record["status"] = "launch_failed"
            log.write(traceback.format_exc().encode("utf-8"))
        else:
            try:
                record["exit_code"] = child.wait()
            except KeyboardInterrupt:

                # 仅取消此记录器启动的计算；Windows 按进程树，POSIX 按独立进程组。
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], stdout=log,
                                   stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                record["exit_code"] = child.wait()
                record["status"] = "cancelled"
            if record["status"] == "running":
                record["status"] = "succeeded" if record["exit_code"] == 0 else "failed"

    # 进度属于诊断；缺失时明确未知，不凭 exit=0 捏造完整研究结果。
    try:
        record["progress"] = json.loads((attempt / "progress.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        record["progress"] = None
        record["progress_note"] = f"阶段与资源未取得：{type(error).__name__}"
    if record["progress"] and record["progress"].get("status") == "running":
        record["progress_note"] = "这是终止前最后写出的阶段快照；当前阶段结束、CPU/RAM 数据未确认，未补造测量"
        record["progress"].setdefault("resources", None)
    record["config_snapshots"] = [str(path.relative_to(attempt))
                                   for path in sorted((attempt / "snapshots/config_at_read").glob("*.source.json"))]
    record["input_bindings"] = [json.loads(path.read_text(encoding="utf-8"))
                                 for path in sorted((attempt / "input_bindings").glob("*.json"))]
    if record["status"] == "succeeded" and record["progress"] and record["progress"]["status"] == "paused":
        record["status"] = "paused"
    record["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    record["wall_time_s"] = time.perf_counter() - started
    write_json(attempt / "execution.json", record)
    write_json(index, record)
    print(f"运行状态：{record['status']}；记录：{attempt / 'execution.json'}", flush=True)
    return record["exit_code"] if record["exit_code"] is not None else 1, attempt
