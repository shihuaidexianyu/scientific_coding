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

`finalize` is how an agent submits an artifact for review: it writes the
manifest and a `pending_review` approval record. `approve` is a human-only
action: it refuses to run without an interactive terminal, and requires
typing a confirmation after inspecting the artifact summary.

No third-party dependencies. Requires Python 3.11+ for TOML parsing (falls
back to a minimal name/version reader otherwise).
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

try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = None

EXCLUDED_FROM_MANIFEST = {"manifest.json", "approval.json"}
EXECUTION_METADATA = {"run.json", "runtime.json"}

CONTRACT_SKELETON = '''name = "{name}"
version = {version}
description = "TODO: one sentence on the scientific meaning of this artifact."

[data]
path = "TODO"
representation = "TODO"
dimensions = ["TODO"]
dtype = "TODO"
unit = "TODO"
missing_value = "not_allowed"

[sample]
identity = "TODO"
id_column = "sample_id"
ordering = "TODO"
population = "TODO"

[compatibility]
consumers_require_exact_version = true
'''


def read_contract_metadata(contract_path: Path) -> tuple[str, int]:
    text = contract_path.read_text(encoding="utf-8")
    if tomllib is not None:
        data = tomllib.loads(text)
        name = data.get("name")
        version = data.get("version")
        if not isinstance(name, str) or not isinstance(version, int):
            raise ValueError("contract must define string 'name' and integer 'version'")
        return name, version
    name_match = re.search(r'^\s*name\s*=\s*"([^"]+)"', text, re.MULTILINE)
    version_match = re.search(r"^\s*version\s*=\s*(\d+)", text, re.MULTILINE)
    if not name_match or not version_match:
        raise ValueError("contract must define string 'name' and integer 'version'")
    return name_match.group(1), int(version_match.group(1))


def tracked_files(artifact_dir: Path) -> list[str]:
    return sorted(
        path.relative_to(artifact_dir).as_posix()
        for path in artifact_dir.rglob("*")
        if path.is_file() and path.name not in EXCLUDED_FROM_MANIFEST
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
    if not tracked:
        print(f"error: no payload files in {artifact_dir}", file=sys.stderr)
        return 2

    identity = list(args.identity) if args.identity else [
        name for name in tracked
        if name == "artifact_contract.toml" or name not in EXECUTION_METADATA
    ]
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
            run_record["output_artifact_hash"] = manifest["artifact_hash"]
            run_path.write_text(
                json.dumps(run_record, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except json.JSONDecodeError:
            print("warning: run.json is not valid JSON; left untouched", file=sys.stderr)

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

    if not approval_path.is_file():
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
    print(f"  state:         produced -> pending_review")
    print("next: a human reviews and runs `scientific_artifact.py approve`")
    return 0


def verify_directory(artifact_dir: Path, full: bool) -> list[lint.Issue]:
    collector = lint.IssueCollector(artifact_dir, suppressions={})
    lint.verify_artifact_dir(artifact_dir, collector, full)
    return collector.issues


def cmd_verify(args: argparse.Namespace) -> int:
    artifact_dir = Path(args.directory)
    issues = verify_directory(artifact_dir, full=args.full)
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
            issues = verify_directory(artifact_dir, full=False)
            if not issues:
                print("artifact is already approved and its hashes still verify")
                return 0
            print(
                "error: approval record exists but hashes no longer verify; "
                "the artifact must be re-reviewed",
                file=sys.stderr,
            )
            return 1

    issues = verify_directory(artifact_dir, full=args.full)
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
        "finalize", help="Compute hashes, write the manifest, submit for review."
    )
    finalize.add_argument("directory")
    finalize.add_argument(
        "--identity",
        action="append",
        default=None,
        help="Identity file (repeatable). Default: contract plus all payloads, "
        "excluding run.json/runtime.json.",
    )
    finalize.set_defaults(handler=cmd_finalize)

    verify = subcommands.add_parser("verify", help="Verify manifest and approval binding.")
    verify.add_argument("directory")
    verify.add_argument(
        "--full",
        action="store_true",
        help="Re-hash payload content, not just metadata (expensive on large data).",
    )
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
        help="Re-hash payload content before approving (recommended for release).",
    )
    approve.set_defaults(handler=cmd_approve)

    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(run())
