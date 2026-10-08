"""Build dashboard-data.json from one completed pipeline run."""
from __future__ import annotations
import argparse
from pathlib import Path
from dashboard_adapter import write_dashboard_data

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    root = args.run.resolve()
    result = write_dashboard_data(root / "stage2/final_score.validated.json", root / "combined_evidence_bank.json", root / "manifest.json", Path(__file__).parent / "prompts/stage2-maturity-scoring.txt", root / "dashboard-data.json")
    print(result)

if __name__ == "__main__":
    main()
