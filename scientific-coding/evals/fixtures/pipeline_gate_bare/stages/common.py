"""Shared helpers for the minimal pipeline example stages.

This module sits inside the declared stage_roots directory only so the
stages can share TOML loading and file hashing without each stage
re-deriving the mechanics. It contains no scientific logic; every
scientific decision lives in the stage that owns it.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_toml_config(path: Path) -> dict:
    """Parse a TOML config file.

    Parameters: absolute path to the TOML file. Returns the parsed dict.
    Method: tomllib on Python 3.11+, else a minimal ``key = value`` reader
    sufficient for the flat example configs. No mutation or side effects.
    """
    text = path.read_text(encoding="utf-8")
    try:
        import tomllib
    except ImportError:  # pragma: no cover - exercised only on Python < 3.11
        config: dict[str, object] = {}
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or "=" not in line:
                continue
            key, _, raw = line.partition("=")
            raw = raw.strip()
            if raw.startswith('"'):
                config[key.strip()] = raw.strip('"')
            else:
                try:
                    config[key.strip()] = int(raw)
                except ValueError:
                    config[key.strip()] = float(raw)
        return config
    return tomllib.loads(text)


def sha256_file(path: Path) -> str:
    """Hash a file's bytes.

    Parameters: file path. Returns the hex sha256. Method: stream the file
    in 64 KiB chunks. No mutation or side effects.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repo_relative(path: Path) -> str:
    """Return a repo-relative POSIX path for provenance records.

    Parameters: any path under the repo root. Returns the relative POSIX
    string. Method: Path.relative_to with a POSIX conversion. No mutation
    or side effects.
    """
    return path.relative_to(REPO_ROOT).as_posix()


if str(REPO_ROOT / "stages") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "stages"))
