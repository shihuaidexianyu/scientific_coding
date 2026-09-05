#!/usr/bin/env python3
"""Artifact lifecycle tool for human-auditable scientific pipelines.

The two-layer hash protocol (identity files -> artifact_hash -> run.json ->
manifest_hash -> approval) is easy to get subtly wrong when re-implemented by
hand. This tool is the single reference implementation so that stage code
never has to re-derive it:

    scientific_artifact.py init     <dir> --contract ProcessedDataset@1
    scientific_artifact.py finalize <dir> [--identity FILE ...]
    scientific_artifact.py verify   <dir> [--full]
    scientific_artifact.py approve  <dir> --reviewer <id> [--note TEXT]

`finalize` writes a complete manifest and permits downstream work by default.
Only `finalize --request-review` creates a pending decision for a user-selected
pause. `approve` is an optional interactive review-recording command; a TTY
is not proof that a human actually inspected the artifact.

No third-party dependencies. Requires Python 3.11+ for TOML parsing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scientific_code_lint as lint

import tomllib

EXCLUDED_FROM_MANIFEST = {"manifest.json", "approval.json"}
EXECUTION_METADATA = {"run.json", "runtime.json"}

CONTRACT_SKELETON = '''# 数据集的科学身份；封存前须将全部 TODO 替换为真实说明。
name = "{name}"

# 科学解释改变时递增此版本。
version = {version}

# 说明此结果的科学含义。
description = "TODO"

# 数据的存储方式及其解释。
[data]

# 相对本产物目录的文件路径。
path = "TODO"

# 存储格式，例如 csv、json、npy 或 parquet。
format = "TODO"

# 本阶段产生的数据表示及其科学含义。
representation = "TODO"

# 按存储顺序声明各轴的含义。
dimensions = ["TODO"]

# 数组数值类型或表格字段类型说明。
dtype = "TODO"

# 物理单位；混合单位时须逐字段说明。
unit = "TODO"

# 所声明数据的缺失值约定。
missing_value = "not_allowed"

# 样本身份与排序含义。
[sample]

# 一个观测或汇总项代表什么。
identity = "TODO"

# 输出顺序及其与配套文件的对应关系。
ordering = "TODO"

# 经本阶段处理后结果所代表的总体。
population = "TODO"

# 打开结果的具体说明。
[reading]

# 使用相对本目录路径的读取调用示例。
example = "TODO"

# 加载所得对象、字段或数组轴及其含义。
in_memory = "TODO"
'''


def read_contract_metadata(contract_path: Path) -> tuple[str, int]:
    data = tomllib.loads(contract_path.read_text(encoding="utf-8"))
    problems = lint.contract_problems(data, contract_path.parent)
    if problems:
        raise ValueError("; ".join(problems))
    return data["name"], data["version"]


def tracked_files(artifact_dir: Path) -> list[str]:
    return sorted(
        path.relative_to(artifact_dir).as_posix()
        for path in artifact_dir.rglob("*")
        if path.is_file() and path.relative_to(artifact_dir).as_posix() not in EXCLUDED_FROM_MANIFEST
    )


def cmd_init(args: argparse.Namespace) -> int:
    artifact_dir = Path(args.directory)
    if artifact_dir.exists() and any(artifact_dir.iterdir()):
        print(f"error: {artifact_dir} is not empty", file=sys.stderr)
        return 2
    name, separator, version = args.contract.partition("@")
    if not separator or not name or not version.isdigit():
        print("error: --contract must be of the form Name@version", file=sys.stderr)
        return 2
    artifact_dir.mkdir(parents=True, exist_ok=True)
    contract_path = artifact_dir / "artifact_contract.toml"
    contract_path.write_text(
        CONTRACT_SKELETON.format(name=name, version=version), encoding="utf-8"
    )
    print(f"initialized {artifact_dir} with contract {name}@{version}")
    print("next: fill in the contract semantics, produce data, then finalize")
    return 0


def cmd_finalize(args: argparse.Namespace) -> int:
    artifact_dir = Path(args.directory)
    contract_path = artifact_dir / "artifact_contract.toml"
    if not contract_path.is_file():
        print(f"error: no artifact_contract.toml in {artifact_dir}", file=sys.stderr)
        return 2
    approval_path = artifact_dir / "approval.json"
    if (artifact_dir / "manifest.json").exists():
        print("error: artifact is already finalized; create a new run", file=sys.stderr)
        return 2
    if approval_path.is_file():
        try:
            status = json.loads(approval_path.read_text(encoding="utf-8")).get("status")
        except json.JSONDecodeError:
            status = None
        if status == "approved":
            print(
                "error: artifact is already approved and immutable; "
                "produce a new run directory instead",
                file=sys.stderr,
            )
            return 2

    try:
        name, version = read_contract_metadata(contract_path)
    except (OSError, ValueError) as error:
        print(f"error: unreadable contract: {error}", file=sys.stderr)
        return 2

    tracked = tracked_files(artifact_dir)
    if not any(name not in EXECUTION_METADATA | {"artifact_contract.toml"} for name in tracked):
        print(f"error: no payload files in {artifact_dir}", file=sys.stderr)
        return 2

    identity = sorted(set(["artifact_contract.toml", *args.identity])) if args.identity else [
        name for name in tracked
        if name == "artifact_contract.toml" or name not in EXECUTION_METADATA
    ]
    if set(identity) & EXECUTION_METADATA:
        print("error: execution metadata cannot be identity files", file=sys.stderr)
        return 2
    missing = [name for name in identity if name not in tracked]
    if missing:
        print(f"error: identity files not present: {missing}", file=sys.stderr)
        return 2

    # Order matters: identity hashes -> artifact_hash -> patch run.json ->
    # hash everything -> manifest_hash. See references/artifact.md.
    file_map: dict[str, str] = {}
    for relative in identity:
        file_map[relative] = lint.sha256_file(artifact_dir / relative)
    contract_sha = file_map["artifact_contract.toml"]
    manifest: dict = {
        "schema_version": 1,
        "artifact_id": artifact_dir.name,
        "state": "produced",
        "review_required": bool(args.request_review),
        "contract": {
            "name": name,
            "version": version,
            "path": "artifact_contract.toml",
            "sha256": contract_sha,
        },
        "identity_files": sorted(identity),
        "files": file_map,
    }
    manifest["artifact_hash"] = lint.derived_artifact_hash(manifest)

    run_path = artifact_dir / "run.json"
    if run_path.is_file():
        try:
            run_record = json.loads(run_path.read_text(encoding="utf-8"))
            if not isinstance(run_record, dict):
                raise TypeError("run.json must contain an object")
            manifest["artifact_id"] = run_record.get("run_id", artifact_dir.name)
            run_record["output_artifact_hash"] = manifest["artifact_hash"]
            run_path.write_text(
                json.dumps(run_record, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except (json.JSONDecodeError, TypeError):
            print("error: run.json must be a valid JSON object", file=sys.stderr)
            return 2

    for relative in tracked:
        if relative not in file_map:
            file_map[relative] = lint.sha256_file(artifact_dir / relative)
    manifest["files"] = {key: file_map[key] for key in sorted(file_map)}
    manifest["created_at_utc"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    manifest["manifest_hash"] = lint.derived_manifest_hash(manifest)

    manifest_path = artifact_dir / "manifest.json"
    temporary = artifact_dir / "manifest.json.tmp"
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(manifest_path)

    if args.request_review:
        approval_path.write_text(
            json.dumps(
                {
                    "status": "pending_review",
                    "artifact_hash": manifest["artifact_hash"],
                    "manifest_hash": manifest["manifest_hash"],
                    "reviewed_by": None,
                    "reviewed_at_utc": None,
                    "review_note": None,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    print(f"finalized {artifact_dir}")
    print(f"  contract:      {name}@{version}")
    print(f"  artifact_hash: {manifest['artifact_hash']}")
    print(f"  manifest_hash: {manifest['manifest_hash']}")
    if args.request_review:
        print("next: inspect the result at this user-selected review point")
    else:
        print("next: the finalized result may flow downstream")
    return 0


def verify_directory(artifact_dir: Path, full: bool) -> list[lint.Issue]:
    collector = lint.IssueCollector(artifact_dir, suppressions={})
    lint.verify_artifact_dir(artifact_dir, collector, full)
    return collector.issues


def cmd_verify(args: argparse.Namespace) -> int:
    artifact_dir = Path(args.directory)
    issues = verify_directory(artifact_dir, full=args.full)
    if not issues and args.require_review:
        manifest = lint.load_json(artifact_dir / "manifest.json")
        if not lint.review_satisfied(artifact_dir, manifest):
            print("error: this result awaits a user-selected review")
            return 1
    for issue in issues:
        location = issue.serializable(artifact_dir)["path"]
        print(f"{issue.severity.upper()} {issue.code} {location} — {issue.message}")
    if issues:
        print(f"verify: {len(issues)} issue(s)")
        return 1
    mode = "full" if args.full else "metadata"
    print(f"verify: OK ({mode} mode)")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    artifact_dir = Path(args.directory)
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(
            "error: approval requires an interactive terminal.\n"
            "Artifact approval is a human action. An agent must finalize the "
            "artifact and request review instead of approving it.",
            file=sys.stderr,
        )
        return 2

    approval_path = artifact_dir / "approval.json"
    if approval_path.is_file():
        try:
            existing = json.loads(approval_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
        if existing.get("status") == "approved":
            issues = verify_directory(artifact_dir, full=True)
            if not issues:
                print("artifact is already approved and its hashes still verify")
                return 0
            print(
                "error: approval record exists but hashes no longer verify; "
                "the artifact must be re-reviewed",
                file=sys.stderr,
            )
            return 1

    issues = verify_directory(artifact_dir, full=True)
    if issues:
        for issue in issues:
            print(f"{issue.severity.upper()} {issue.code} — {issue.message}")
        print("error: artifact does not verify; fix it before approval", file=sys.stderr)
        return 1

    manifest_path = artifact_dir / "manifest.json"
    if not manifest_path.is_file():
        print("error: no manifest.json; run finalize first", file=sys.stderr)
        return 2
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"error: unreadable manifest: {error}", file=sys.stderr)
        return 2
    if not isinstance(manifest.get("files"), dict):
        print("error: manifest has no files object; run finalize again", file=sys.stderr)
        return 2

    total_bytes = sum(
        (artifact_dir / name).stat().st_size for name in manifest["files"]
    )
    contract = manifest.get("contract") or {}
    print("artifact summary")
    print(f"  directory:     {artifact_dir}")
    print(f"  contract:      {contract.get('name')}@{contract.get('version')}")
    print(f"  artifact_hash: {manifest['artifact_hash']}")
    print(f"  manifest_hash: {manifest['manifest_hash']}")
    print(f"  files:         {len(manifest['files'])} ({total_bytes} bytes)")
    print(f"  identity:      {', '.join(manifest['identity_files'])}")
    print()
    print("By approving you assert that you, a human reviewer, inspected this")
    print("artifact (previews, exclusion ledger, provenance) against the study")
    print("protocol. This binds approval to the hashes above.")
    confirmation = input("type 'approve' to confirm: ").strip()
    if confirmation != "approve":
        print("aborted; artifact remains unapproved")
        return 1

    approval = {
        "status": "approved",
        "artifact_hash": manifest["artifact_hash"],
        "manifest_hash": manifest["manifest_hash"],
        "reviewed_by": args.reviewer,
        "reviewed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "review_note": args.note,
    }
    approval_path.write_text(
        json.dumps(approval, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"approved {artifact_dir} by {args.reviewer}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scientific-artifact",
        description="Artifact lifecycle tool for human-auditable scientific pipelines.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    init = subcommands.add_parser("init", help="Scaffold a new artifact directory.")
    init.add_argument("directory")
    init.add_argument("--contract", required=True, help="Name@version")
    init.set_defaults(handler=cmd_init)

    finalize = subcommands.add_parser(
        "finalize", help="Validate the contract, compute hashes, and complete the result."
    )
    finalize.add_argument("directory")
    finalize.add_argument(
        "--identity",
        action="append",
        default=None,
        help="Identity file (repeatable). Default: contract plus all payloads, "
        "excluding run.json/runtime.json.",
    )
    finalize.add_argument("--request-review", action="store_true", help="Only for a user-selected human review point.")
    finalize.set_defaults(handler=cmd_finalize)

    verify = subcommands.add_parser("verify", help="Verify manifest and approval binding.")
    verify.add_argument("directory")
    verify.add_argument(
        "--full",
        action="store_true",
        help="Re-hash payload content, not just metadata (expensive on large data).",
    )
    verify.add_argument("--require-review", action="store_true", help="Also honor a review_required manifest when consuming input.")
    verify.set_defaults(handler=cmd_verify)

    approve = subcommands.add_parser(
        "approve", help="Human-only approval; requires an interactive terminal."
    )
    approve.add_argument("directory")
    approve.add_argument("--reviewer", required=True, help="Reviewer identifier")
    approve.add_argument("--note", default=None, help="Review note")
    approve.add_argument(
        "--full",
        action="store_true",
        help="Compatibility flag: approval always re-hashes the reviewed content.",
    )
    approve.set_defaults(handler=cmd_approve)

    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(run())
