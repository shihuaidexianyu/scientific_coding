"""
编排从合成试次到最终图的连续流水线，仅在用户指定处暂停。

文件流程
--------
configs/pipeline.toml --> 选择上游、路径和暂停点
                                |
                                v
新采集 或 外部 RawTrials -----> 预处理
                                |
外部 ProcessedTrials -----------+
                                |
                                v
                               分析
                                |
                                v
                      results.svg + 来源记录

CLI 启动 --> executions/attempts/<编号>/run.log + execution.json
                         |
                         v
             executions/index/<编号>.json（所有尝试）

三个阶段分别使用 configs/acquire_data.toml、
configs/preprocess.toml 和 configs/analyze.toml。

输入与关联 TOML
---------------
默认读取项目根目录下 configs/pipeline.toml：run_root 指定结果父目录，
acquire_config、preprocess_config、analyze_config 指定三个阶段的科学配置。
raw_artifact、processed_artifact 可指定一个已保存的上游产物；同时为空时重新生成。
pause_after 为空时连续运行，填写阶段名时在该阶段新产物生成后暂停。
相对数据与阶段配置路径按本文件所在的项目根目录解析。

加工逻辑
--------
解析执行选择，分配新的运行目录；生成或读取上游、筛选试次、分析均值差及区间，
最后绘图。外部数据在进入流程时验证一次，同次流程的中间数据直接传递。

输出文件
--------
完整运行目录含 raw_trials、processed_trials、analysis_result 子目录，
results.svg、results.provenance.json 和 pipeline_config.toml。
复用外部结果时省略相应上游生产目录；暂停时只保留已完成阶段。
不覆盖历史运行。
CLI 通过独立工作进程捕获完整输出、异常堆栈、阶段时间和资源；
executions 中的可变记录位于已封存科学产物之外。直接函数调用供嵌入及测试，
由所属执行入口负责一份运行记录，不为每个内部调用再创建尝试。
"""

# 编排器管理执行顺序和路径，科学计算保留在各阶段内。
import argparse
import os
from pathlib import Path
import shutil
import sys
import uuid
from execution import Progress, execute

# 父进程只定位入口，业务模块留到日志已经建立后的工作进程中导入。
PROJECT_ROOT = Path(__file__).resolve().parent


def run(config_path: Path, progress: Progress | None = None) -> Path:
    """按声明的上游来源和暂停点执行整个流水线。

    参数
    ----
    config_path : Path
        编排 TOML 的路径；命令行入口默认使用 configs/pipeline.toml。
        相对配置路径按当前工作目录打开；以下配置值中的路径按项目根目录解析。
        run_root 为新运行目录的父路径字符串。

        acquire_config、preprocess_config、analyze_config 分别为采集、筛选和分析
        TOML 的路径字符串。

        pause_after 为 ""、"acquire_data"、"preprocess" 或 "analyze" 字符串；
        空值表示连续执行，其余值只在对应阶段实际生产新结果后暂停。

        raw_artifact、processed_artifact 为已保存产物目录的路径字符串；
        空值表示不复用，两者不能同时非空，复用预处理结果会跳过采集与预处理。

    progress : Progress 或 None
        可选的执行边界观察器，保存阶段名、墙钟秒数和结果目录。
        CLI 传入当前尝试的对象；嵌入或单元测试可省略，由外层入口负责记录。
        该对象只观察进度，不决定阶段是否执行，也不校验科学数据。

    返回
    ----
    run_root : Path
        本次新结果目录的路径，形如 artifacts/run_<编号>。
        完整运行含 raw_trials、processed_trials、analysis_result 三个产物子目录，
        results.svg、results.provenance.json 及 pipeline_config.toml。
        复用时省略被跳过的上游生产目录，暂停时仅包含已完成阶段；
        调用方可由此路径打开最终 SVG 或待查看的阶段产物。

    处理过程
    --------
    1. 解析路径和暂停选择，拒绝互相冲突的外部输入设置。
    2. 分配新 run；必要时从外部入口读取数据，否则执行相应上游阶段。
    3. 顺序执行预处理、分析、绘图，只在用户选定且实际执行的阶段暂停。

    副作用
    ------
    创建结果文件并打印结果位置；不覆盖历史 run，不自动要求每阶段审批。
    """

    # 创建结果目录前确定执行选择；这些选择不改写科学方法。
    from artifact_io import load_external_artifact, read_config
    from stages import acquire_data, preprocess, analyze
    from figures.figure_results import write_figure

    # 配置解析和业务导入在工作进程中进行，失败会进入本次完整日志。
    config = read_config(config_path)
    pause_after = config["pause_after"]
    if pause_after not in ("", "acquire_data", "preprocess", "analyze"):
        raise ValueError("pause_after must name a stage or be empty")
    raw_input = config.get("raw_artifact", "")
    processed_input = config.get("processed_artifact", "")

    if raw_input and processed_input:
        raise ValueError(
            "Declare either raw_artifact or processed_artifact, not both"
        )

    # 暂停只能针对本次新生成的产物，跳过的生产阶段没有新评审对象。
    uses_external_input = raw_input or processed_input
    if uses_external_input and pause_after == "acquire_data":
        raise ValueError(
            "acquire_data is skipped for an external input; "
            "choose an executed stage"
        )
    if processed_input and pause_after == "preprocess":
        raise ValueError(
            "preprocess is skipped for processed_artifact; "
            "choose an executed stage"
        )

    # 分配新运行目录；编号只影响保存位置，不参与科学计算。
    run_root = (
        PROJECT_ROOT / config["run_root"] / ("run_" + uuid.uuid4().hex[:12])
    )
    run_root.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(config_path, run_root / "pipeline_config.toml")
    if progress is not None:
        progress.data["result_path"] = str(run_root)
        progress.data["effective_pipeline_config"] = config

    # 复用已声明的预处理结果时跳过上游，在外部入口核验一次。
    if processed_input:
        if progress is not None:
            progress.enter("load_processed")
        processed_rows, processed_binding = load_external_artifact(
            PROJECT_ROOT / processed_input,
            "ProcessedTrials@1",
        )
    else:

        # 按已确定的流程复用原始结果或重新生成试次。
        if raw_input:
            if progress is not None:
                progress.enter("load_raw")
            raw_rows, raw_binding = load_external_artifact(
                PROJECT_ROOT / raw_input, "RawTrials@1"
            )
        else:
            if progress is not None:
                progress.enter("acquire_data")
            raw_rows, raw_binding = acquire_data.run(
                PROJECT_ROOT / config["acquire_config"],
                run_root / "raw_trials",
                review_required=pause_after == "acquire_data",
            )
            if pause_after == "acquire_data":
                if progress is not None:
                    progress.data["status"] = "paused"
                print(f"Requested review point: {run_root / 'raw_trials'}")
                return run_root

        # 同次受控流程直接向下游传递已生成的数据及绑定。
        if progress is not None:
            progress.enter("preprocess")
        processed_rows, processed_binding = preprocess.run(
            raw_rows,
            raw_binding,
            PROJECT_ROOT / config["preprocess_config"],
            run_root / "processed_trials",
            review_required=pause_after == "preprocess",
        )
        if pause_after == "preprocess":
            if progress is not None:
                progress.data["status"] = "paused"
            print(f"Requested review point: {run_root / 'processed_trials'}")
            return run_root

    # 分析已建立保证的预处理输入，不重复入口检查。
    if progress is not None:
        progress.enter("analyze")
    result, result_binding = analyze.run(
        processed_rows,
        processed_binding,
        PROJECT_ROOT / config["analyze_config"],
        run_root / "analysis_result",
        review_required=pause_after == "analyze",
    )
    if pause_after == "analyze":
        if progress is not None:
            progress.data["status"] = "paused"
        print(f"Requested review point: {run_root / 'analysis_result'}")
        return run_root

    # 显示已经计算的数值，并将图绑定到实际分析来源。
    if progress is not None:
        progress.enter("figure")
    write_figure(result, result_binding, run_root / "results.svg")
    print(f"Completed pipeline: {run_root}")
    return run_root


if __name__ == "__main__":

    # 入口只接收一个配置路径，科学方法参数保存在 TOML 中。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "config", nargs="?", default=str(PROJECT_ROOT / "configs/pipeline.toml")
    )
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    config_path = Path(arguments.config).resolve()
    if not arguments.worker:

        # 父入口先保存尝试，再启动业务代码；错误配置也有日志与实际退出码。
        worker_command = [
            sys.executable,
            "-u",
            str(Path(__file__).resolve()),
            str(config_path),
            "--worker",
        ]
        source_names = (
            "pipeline.py",
            "execution.py",
            "artifact_io.py",
            "stages/acquire_data.py",
            "stages/preprocess.py",
            "stages/analyze.py",
            "figures/figure_results.py",
        )
        source_paths = [str(PROJECT_ROOT / name) for name in source_names]
        provenance = {
            "experiment_id": "minimal_pipeline",
            "config_path": str(config_path),
            "source_paths": source_paths,
        }
        execution_directory = PROJECT_ROOT / "executions"
        status, _ = execute(
            worker_command,
            execution_directory,
            PROJECT_ROOT,
            provenance,
        )
        raise SystemExit(status)

    # 父进程已保留启动源码；工作进程记录实际读取配置和既有阶段来源。
    progress = Progress(Path(os.environ["SCIENTIFIC_EXECUTION_DIR"]))
    progress.enter("setup")
    try:
        run(config_path, progress)
    except BaseException as error:

        # 保存失败阶段和已完成耗时，再传播异常，使父进程获得非零退出和完整堆栈。
        progress.data["error"] = {
            "type": type(error).__name__,
            "message": str(error),
        }
        progress.finish("failed")
        raise
    else:

        # 用户选定暂停与正常完成分别记录；两者的命令退出均为成功。
        if progress.data["status"] == "paused":
            final_status = "paused"
        else:
            final_status = "succeeded"
        progress.finish(final_status)
