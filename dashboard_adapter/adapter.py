"""Convert canonical Stage 2 artifacts into the versioned dashboard contract."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from dema.storage import atomic_write_json, read_json, utc_now

PHASE_NAMES = {
    1: "Incomplete, ad hoc",
    2: "Recognized but reactive",
    3: "Managed and defined",
    4: "Controlled, optimizing",
    5: "State of the art, transformational",
}
DIMENSION_COLORS = {"A": "#d91e36", "B": "#006f8b", "C": "#5b4b8a"}


def framework_structure(prompt_text: str) -> list[dict[str, Any]]:
    dimensions: list[dict[str, Any]] = []
    dimension: dict[str, Any] | None = None
    subdimension: dict[str, Any] | None = None
    for line in prompt_text.splitlines():
        match = re.match(r"^DIMENSION\s+([A-C])\s+[—-]\s+(.+)$", line)
        if match:
            dimension = {"id": match.group(1), "label": match.group(2).strip().title(), "subdimensions": []}
            dimensions.append(dimension)
            continue
        match = re.match(r"^SUBDIMENSION\s+([A-C]\.\d+)\s+[—-]\s+(.+)$", line)
        if match and dimension:
            subdimension = {"id": match.group(1), "label": match.group(2).strip(), "indicators": []}
            dimension["subdimensions"].append(subdimension)
            continue
        match = re.match(r"^INDICATOR\s+([A-C]\.?(?:\d+)\.\d+[a-z]?)[.]?\s+[—-]\s+(.+)$", line)
        if match and subdimension:
            code = match.group(1)
            if code[1] != ".":
                code = code[0] + "." + code[1:]
            subdimension["indicators"].append({"indicator_code": code.rstrip("."), "indicator_name": match.group(2).strip()})
    if sum(len(s["indicators"]) for d in dimensions for s in d["subdimensions"]) != 31:
        raise ValueError("Frozen Stage 2 prompt does not contain the expected 31 indicators")
    return dimensions


def _score(value: Any) -> int | None:
    if isinstance(value, int) and 1 <= value <= 5:
        return value
    return None


def build_dashboard_data(
    stage2: dict[str, Any], evidence_bank: dict[str, Any], manifest: dict[str, Any], prompt_text: str,
) -> dict[str, Any]:
    result = stage2.get("result", stage2)
    assessments = {item.get("indicator_code"): item for item in result.get("indicator_assessments", [])}
    evidence = {item.get("evidence_id"): item for item in evidence_bank.get("evidence_items", [])}
    dimensions = framework_structure(prompt_text)
    for dimension in dimensions:
        dimension["color"] = DIMENSION_COLORS[dimension["id"]]
        for subdimension in dimension["subdimensions"]:
            for indicator in subdimension["indicators"]:
                assessment = assessments.get(indicator["indicator_code"])
                if not assessment:
                    indicator.update({"score_status": "insufficient_evidence", "phase_score": None, "phase_name": "Not scored", "supporting_evidence": [], "limiting_evidence": [], "requirement_checks": []})
                    continue
                score = _score(assessment.get("phase_score"))
                supporting_ids = assessment.get("evidence_supporting_score", [])
                limiting_ids = assessment.get("contrary_or_limiting_evidence", [])
                missing = [identifier for identifier in [*supporting_ids, *limiting_ids] if identifier not in evidence]
                if missing:
                    raise ValueError(f"Assessment references unknown evidence IDs: {sorted(set(missing))}")
                indicator.update({
                    "score_status": "scored" if score else "insufficient_evidence",
                    "phase_score": score,
                    "phase_name": PHASE_NAMES.get(score, "Not scored"),
                    "matched_phase_requirement": assessment.get("matched_phase_requirement", ""),
                    "score_reasoning": assessment.get("score_reasoning", ""),
                    "next_phase_gap": assessment.get("next_phase_gap", ""),
                    "contrary_or_limiting_reasoning": assessment.get("contrary_or_limiting_reasoning", ""),
                    "requirement_checks": assessment.get("assigned_phase_requirement_checks", []),
                    "supporting_evidence": [evidence[i] for i in supporting_ids],
                    "limiting_evidence": [evidence[i] for i in limiting_ids],
                })
    return {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "classification": "INTERNAL",
        "notice": "Documentary pre-assessment — not expert validation",
        "run": {
            "run_id": manifest.get("run_id", "unknown"),
            "country": result.get("country", manifest.get("country", "Unknown")),
            "assessment_mode": manifest.get("assessment_mode", "document_only"),
            "status": manifest.get("status", "complete"),
            "started_at": manifest.get("started_at"),
            "completed_at": manifest.get("completed_at"),
            "prompt_versions": manifest.get("prompt_versions", {}),
            "sample": bool(manifest.get("sample", False)),
        },
        "assessment_summary": result.get("assessment_summary", ""),
        "validation_warnings": stage2.get("warnings", []),
        "dimensions": dimensions,
    }


def write_dashboard_data(stage2_path: Path, evidence_path: Path, manifest_path: Path, prompt_path: Path, output_path: Path) -> Path:
    data = build_dashboard_data(read_json(stage2_path), read_json(evidence_path), read_json(manifest_path), prompt_path.read_text(encoding="utf-8"))
    atomic_write_json(output_path, data)
    return output_path
