"""Filesystem job worker used by the local web application."""
from __future__ import annotations
import argparse, json, os, re, traceback
from pathlib import Path
from dema.pipeline import run_assessment
from dema.stage0 import prepare_sources
from dema.storage import atomic_write_json, utc_now
from dashboard_adapter import write_dashboard_data

STATES = ["Uploaded", "Preparing document", "Extracting evidence", "Validating evidence", "Building evidence bank", "Scoring indicators", "Building dashboard", "Complete"]

def safe_run_id(value: str) -> str:
    if not re.fullmatch(r"dema-[a-f0-9]{24}", value): raise ValueError("Invalid run ID")
    return value

def status(root: Path, state: str, *, error: str | None = None) -> None:
    atomic_write_json(root / "status.json", {"run_id": root.name, "state": state, "updated_at": utc_now(), "error": error})

def run(root: Path, country: str, mode: str) -> None:
    try:
        status(root, "Preparing document")
        prepare_sources(root / "upload", root / "prepared")
        bank = root / "input_evidence_bank.json"
        if mode == "document_only":
            atomic_write_json(bank, {"evidence_items": []})
        else:
            configured = os.getenv("DEMA_BASELINE_BANK")
            if not configured: raise RuntimeError("DEMA_BASELINE_BANK is required for baseline_plus_document mode")
            bank = Path(configured).resolve()
        status(root, "Extracting evidence")
        run_assessment(env_path=Path(os.getenv("DEMA_ENV_FILE", ".env")), chunks_path=root / "prepared/chunks", base_bank_path=bank, output_path=root, country=country, stage2_max_output_tokens=32768, progress_callback=lambda state: status(root, state))
        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")); manifest["assessment_mode"] = mode; atomic_write_json(manifest_path, manifest)
        status(root, "Building dashboard")
        write_dashboard_data(root / "stage2/final_score.validated.json", root / "combined_evidence_bank.json", manifest_path, Path(__file__).parents[1] / "prompts/stage2-maturity-scoring.txt", root / "dashboard-data.json")
        status(root, "Complete")
    except Exception as exc:
        status(root, "Failed", error=f"{type(exc).__name__}: {exc}")
        (root / "worker-error.log").write_text(traceback.format_exc(), encoding="utf-8")

def main():
    p=argparse.ArgumentParser(); p.add_argument("run_dir", type=Path); p.add_argument("--country", required=True); p.add_argument("--mode", choices=["document_only","baseline_plus_document"], required=True); a=p.parse_args()
    root=a.run_dir.resolve(); safe_run_id(root.name); run(root,a.country,a.mode)
if __name__ == "__main__": main()
