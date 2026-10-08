"""Prepare PDF/HTML sources as reviewed 10-page Markdown chunks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dema.stage0 import prepare_sources


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("source_documents"))
    parser.add_argument("--output", type=Path, default=Path("prepared_data"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = prepare_sources(args.input, args.output)
    print(f"STAGE 0 COMPLETE | {manifest}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
