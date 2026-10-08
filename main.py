"""Run the two-stage DEMA documentary pre-assessment."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dema.config import DEFAULT_BASE_BANK, DEFAULT_CHUNKS, DEFAULT_ENV, DEFAULT_OUTPUT
from dema.pipeline import run_assessment


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    parser.add_argument("--base-bank", type=Path, default=DEFAULT_BASE_BANK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--country", default="Togo")
    parser.add_argument("--stage2-max-output-tokens", type=int, default=32768)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_assessment(
        env_path=args.env,
        chunks_path=args.chunks,
        base_bank_path=args.base_bank,
        output_path=args.output,
        country=args.country,
        stage2_max_output_tokens=args.stage2_max_output_tokens,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted; completed Stage 1 chunks remain resumable.", file=sys.stderr)
        raise
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
