#!/usr/bin/env python3
"""Preserve an accepted specification version as an immutable snapshot.

Reads ``version`` from the specification's front matter and copies the file to
``<stem>.v<version><suffix>`` next to it (or into ``--out-dir``), read-only.
Workers and the observation log reference the snapshot, so the exact text a
piece of work was based on stays reproducible while the working file evolves.

Usage:
    snapshot_spec.py SPEC [--out-dir DIR]

Re-running for an unchanged version is a no-op. If a snapshot of that version
already exists with different content, nothing is written and the exit status
is 1 - bump the version instead of rewriting history. Exit status 2 for a
missing file or version. The snapshot path is printed on success.
"""

from __future__ import annotations

import argparse
import re
import stat
import sys
from pathlib import Path

_VERSION = re.compile(r"^version:\s*[\"']?([0-9A-Za-z][0-9A-Za-z.+-]*)[\"']?\s*$")


class SnapshotError(Exception):
    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


def spec_version(text: str) -> str:
    """Return the ``version`` value from the leading front matter block."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SnapshotError("specification has no front matter", 2)
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = _VERSION.match(line.strip())
        if match:
            return match.group(1)
    raise SnapshotError("front matter has no version", 2)


def snapshot(spec: Path, out_dir: Path | None = None) -> Path:
    """Create (or confirm) the read-only snapshot of the spec's current version."""
    if not spec.is_file():
        raise SnapshotError(f"{spec} is not a file", 2)
    content = spec.read_bytes()
    version = spec_version(content.decode("utf-8"))
    target = (out_dir or spec.parent) / f"{spec.stem}.v{version}{spec.suffix}"
    if target.exists():
        if target.read_bytes() == content:
            return target
        raise SnapshotError(
            f"{target} already holds different content for version {version}; "
            "bump the version instead",
            1,
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    target.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        target = snapshot(args.spec, args.out_dir)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"snapshot_spec: {exc}", file=sys.stderr)
        return 2
    except SnapshotError as exc:
        print(f"snapshot_spec: {exc}", file=sys.stderr)
        return exc.code
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
