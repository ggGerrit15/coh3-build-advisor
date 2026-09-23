"""Compare CoHDB snapshots while ignoring retrieval-only metadata."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


VOLATILE_FIELDS = frozenset({"retrieved_at"})


def comparable_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return the snapshot fields that represent imported CoHDB data."""
    return {key: value for key, value in snapshot.items() if key not in VOLATILE_FIELDS}


def snapshots_meaningfully_differ(
    existing: dict[str, Any], candidate: dict[str, Any]
) -> bool:
    """Return whether imported data changed beyond volatile metadata."""
    return comparable_snapshot(existing) != comparable_snapshot(candidate)


def load_snapshot(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Snapshot must be a JSON object: {path}")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--existing", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument(
        "--github-output",
        type=Path,
        help="Optional GitHub Actions output file to receive changed=true/false.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    candidate = load_snapshot(args.candidate)
    existing = load_snapshot(args.existing) if args.existing.exists() else None
    changed = existing is None or snapshots_meaningfully_differ(existing, candidate)

    if changed:
        args.candidate.replace(args.existing)
        message = "Meaningful CoHDB data changed; candidate promoted to latest.json."
    else:
        args.candidate.unlink()
        message = "No meaningful CoHDB data change; keeping the existing snapshot."

    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(f"changed={'true' if changed else 'false'}\n")

    print(f"changed={'true' if changed else 'false'}")
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
