"""One explicit two-stage DEMA assessment workflow.

Markdown chunks -> evidence extraction -> evidence bank -> maturity scoring
-> validated assessment.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Callable

from .config import (
    EXTRACTION_PROMPT_NAME,
    EXTRACTION_PROMPT_VERSION,
)
from .llm import build_model_client, call_model_json, model_name, model_runtime_identity
from .prompts import (
    get_extraction_prompt,
    get_langfuse_client,
    get_scoring_prompt,
    scoring_prompt_snapshot,
)
from .storage import atomic_write_json, atomic_write_text, read_json, sha256_text, utc_now

STAGE1_REQUIRED_ROW_FIELDS = {
    "evidence_id",
    "subdimension",
    "evidence_scope",
    "country_specificity",
    "supporting_quote",
    "evidence_statement",
    "interpretation_boundary",
    "page_number",
}

SCORING_EVIDENCE_FIELDS = (
    "evidence_id",
    "dimension",
    "subdimension",
    "evidence_scope",
    "country_specificity",
    "supporting_quote",
    "evidence_statement",
    "reasoning_identification",
    "interpretation_boundary",
    "source_file",
    "source_url",
    "page_number",
    "use_in_country_assessment",
)


def frontmatter_value(text: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}:\s*[\"']?(.*?)[\"']?\s*$", text, re.MULTILINE)
    return match.group(1).strip().strip("\"'") if match else ""


def chunk_metadata(path: Path, text: str, chunks_root: Path) -> dict[str, str]:
    source_id = frontmatter_value(text, "source_id") or path.parent.name.split("_", 1)[0]
    source_file = frontmatter_value(text, "source_file") or path.name
    source_url = frontmatter_value(text, "source_url")
    processing_unit_id = path.stem
    return {
        "source_id": source_id,
        "source_file": source_file,
        "source_url": source_url,
        "processing_unit_id": processing_unit_id,
        "relative_path": path.relative_to(chunks_root).as_posix(),
    }


def input_with_metadata(metadata: dict[str, str], text: str) -> str:
    header = (
        "<!-- pipeline_metadata\n"
        f"source_id: {metadata['source_id']}\n"
        f"source_file: {metadata['source_file']}\n"
        f"source_url: {metadata['source_url']}\n"
        f"processing_unit_id: {metadata['processing_unit_id']}\n"
        "-->\n\n"
    )
    return header + text


def artifact_path_component(value: str) -> str:
    """Create a bounded, non-traversing path component with collision suffix."""
    readable = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-") or "item"
    return f"{readable[:80]}-{sha256_text(value)[:10]}"


def combine_evidence_items(
    base_items: list[dict[str, Any]],
    extracted_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Create the canonical evidence sequence and enforce unique, nonblank IDs."""
    combined = [dict(item) for item in base_items] + [dict(item) for item in extracted_items]
    identifiers = [str(item.get("evidence_id", "")).strip() for item in combined]
    blanks = [index for index, value in enumerate(identifiers) if not value]
    counts: dict[str, int] = {}
    for identifier in identifiers:
        counts[identifier] = counts.get(identifier, 0) + 1
    duplicates = sorted(identifier for identifier, count in counts.items() if identifier and count > 1)
    if blanks or duplicates:
        raise ValueError(
            f"Combined evidence IDs invalid: blanks={blanks}, duplicates={duplicates}"
        )
    return combined


def validate_stage1(
    data: dict[str, Any],
    source_text: str,
    metadata: dict[str, str],
    *,
    prompt_name: str = EXTRACTION_PROMPT_NAME,
    prompt_version: int = EXTRACTION_PROMPT_VERSION,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    rows = data.get("dema_evidence_rows")
    if not isinstance(rows, list):
        raise ValueError("Stage 1 output lacks a dema_evidence_rows array")
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, row in enumerate(rows, start=1):
        reasons: list[str] = []
        if not isinstance(row, dict):
            rejected.append({"row_index": index, "row": row, "reasons": ["not_an_object"]})
            continue
        missing = sorted(field for field in STAGE1_REQUIRED_ROW_FIELDS if field not in row)
        if missing:
            reasons.append("missing_fields:" + ",".join(missing))
        quote = row.get("supporting_quote")
        if not isinstance(quote, str) or not quote:
            reasons.append("empty_quote")
        elif quote not in source_text:
            reasons.append("quote_not_exact_contiguous_substring")
        if reasons:
            rejected.append({"row_index": index, "row": row, "reasons": reasons})
            continue
        normalized = dict(row)
        normalized.update(
            {
                "source_id": metadata["source_id"],
                "source_file": metadata["source_file"],
                "source_url": metadata["source_url"],
                "processing_unit_id": metadata["processing_unit_id"],
                "source_chunk": metadata["relative_path"],
                "stage1_prompt_name": prompt_name,
                "stage1_prompt_version": prompt_version,
            }
        )
        accepted.append(normalized)
    if data.get("source_id") not in (None, "", metadata["source_id"]):
        errors.append("top_level_source_id_mismatch")
    if data.get("processing_unit_id") not in (None, "", metadata["processing_unit_id"]):
        errors.append("top_level_processing_unit_id_mismatch")
    return accepted, rejected, errors


def cache_key_matches(record: dict[str, Any], expected: dict[str, Any]) -> bool:
    """Require an exact cache identity; legacy or partial records are stale."""
    return record.get("cache_key") == expected


def extract_scoring_scope(stage2_text: str) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    # Some source headings contain a trailing full stop after the code, and the
    # dash glyph may be represented differently across API/console encodings.
    pattern = re.compile(
        r"^INDICATOR\s+([ABC]\.?\d+\.\d+[a-z]?)[.]?\s+\S\s+(.+?)\s*$",
        re.MULTILINE,
    )
    for match in pattern.finditer(stage2_text):
        code = match.group(1)
        if not code.startswith(("A.", "B.", "C.")):
            code = code[0] + "." + code[1:]
        code = code.rstrip(".")
        if code not in seen:
            seen.add(code)
            found.append({"indicator_code": code, "indicator_name": match.group(2).strip()})
    if not found:
        raise ValueError("No indicator definitions found in Stage 2 prompt")
    return found


def build_scoring_batches(
    scoring_scope: list[dict[str, str]],
) -> list[list[dict[str, str]]]:
    """Preserve the validated batching strategy used by the frozen P5 run."""
    batches: list[list[dict[str, str]]] = []
    a_scope = [item for item in scoring_scope if item["indicator_code"].startswith("A.")]
    batches.append(a_scope[:4])
    batches.extend(a_scope[index:index + 2] for index in range(4, len(a_scope), 2))
    for dimension in ("B", "C"):
        dimension_scope = [
            item
            for item in scoring_scope
            if item["indicator_code"].startswith(dimension + ".")
        ]
        batches.extend(
            dimension_scope[index:index + 2]
            for index in range(0, len(dimension_scope), 2)
        )
    # This targeted replacement is part of the frozen run: the original A.1.3
    # reasoning was shorter than the prompt's required 180 words.
    batches.append(
        [next(item for item in a_scope if item["indicator_code"] == "A.1.3")]
    )
    return batches


def validate_stage2(
    data: dict[str, Any], scoring_scope: list[dict[str, str]], evidence_ids: set[str]
) -> list[str]:
    assessments = data.get("indicator_assessments")
    if not isinstance(assessments, list):
        raise ValueError("Stage 2 output lacks indicator_assessments")
    expected = [item["indicator_code"] for item in scoring_scope]
    received = [item.get("indicator_code") for item in assessments if isinstance(item, dict)]
    if len(received) != len(set(received)) or set(received) != set(expected):
        raise ValueError(f"Stage 2 indicator mismatch: expected {expected}, received {received}")
    warnings: list[str] = []
    for item in assessments:
        code = item["indicator_code"]
        if type(item.get("phase_score")) is not int or not 1 <= item["phase_score"] <= 5:
            raise ValueError(f"Invalid phase score for {code}")
        for field in ("evidence_supporting_score", "contrary_or_limiting_evidence"):
            ids = item.get(field)
            if not isinstance(ids, list):
                raise ValueError(f"{code}.{field} is not an array")
            unknown = [value for value in ids if value not in evidence_ids]
            if unknown:
                raise ValueError(f"{code}.{field} has unknown IDs: {unknown}")
        checks = item.get("assigned_phase_requirement_checks")
        if not isinstance(checks, list):
            raise ValueError(f"{code} lacks assigned_phase_requirement_checks")
        bad = [check for check in checks if not isinstance(check, dict) or check.get("status") != "SUPPORTED"]
        if bad:
            # P5 also mandates Phase 1 when no maturity criterion is evidenced.
            # In that documentary-gap case the model may truthfully mark the
            # negative Phase-1 descriptors NOT_DEMONSTRATED. Preserve and flag
            # that tension instead of converting missing evidence into support.
            gap_fallback = (
                item.get("phase_score") == 1
                and not item.get("evidence_supporting_score")
                and all(isinstance(check, dict) and check.get("status") == "NOT_DEMONSTRATED" for check in bad)
            )
            if gap_fallback:
                warnings.append(
                    f"{code}: Phase 1 documentary-gap fallback has NOT_DEMONSTRATED requirement checks"
                )
            else:
                raise ValueError(f"{code} contains non-SUPPORTED assigned-phase checks")
        reasoning = str(item.get("score_reasoning", ""))
        words = len(re.findall(r"\b\w+\b", reasoning, flags=re.UNICODE))
        if words < 180 or words > 350:
            warnings.append(f"{code}: score_reasoning has {words} words (expected 180-350)")
    return warnings


def repair_evidence_id_padding(
    value: Any,
    evidence_ids: set[str],
    *,
    prefix: str,
    match_suffix: bool = False,
) -> tuple[Any, list[dict[str, str]]]:
    """Repair only unambiguous numeric zero-padding omissions."""
    repairs: list[dict[str, str]] = []
    pattern = re.compile(rf"{re.escape(prefix)}-(\d{{1,4}})(?!\d)")

    def repair_text(text: str) -> str:
        if match_suffix and text not in evidence_ids:
            suffix_matches = [candidate for candidate in evidence_ids if candidate and text.endswith(candidate)]
            if len(suffix_matches) == 1:
                canonical = suffix_matches[0]
                repairs.append({"from": text, "to": canonical})
                return canonical

        def replace(match: re.Match[str]) -> str:
            original = match.group(0)
            if original in evidence_ids:
                return original
            canonical = f"{prefix}-{int(match.group(1)):04d}"
            if canonical in evidence_ids:
                repairs.append({"from": original, "to": canonical})
                return canonical
            return original
        return pattern.sub(replace, text)

    def walk(item: Any) -> Any:
        if isinstance(item, str):
            return repair_text(item)
        if isinstance(item, list):
            return [walk(child) for child in item]
        if isinstance(item, dict):
            return {key: walk(child) for key, child in item.items()}
        return item

    repaired = walk(value)
    unique_repairs = [dict(pair) for pair in {tuple(sorted(item.items())) for item in repairs}]
    return repaired, unique_repairs


def remove_redundant_source_locator_citations(
    data: dict[str, Any], evidence_lookup: dict[str, dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Remove a source locator used as an ID only when a cited row covers it."""
    evidence_ids = set(evidence_lookup)
    repairs: list[dict[str, str]] = []
    for assessment in data.get("indicator_assessments", []):
        if not isinstance(assessment, dict):
            continue
        removed: list[str] = []
        for field in ("evidence_supporting_score", "contrary_or_limiting_evidence"):
            references = assessment.get(field)
            if not isinstance(references, list):
                continue
            valid = [reference for reference in references if reference in evidence_ids]
            locators = {
                str(evidence_lookup[reference].get(locator, ""))
                for reference in valid
                for locator in ("source_chunk", "source_file")
                if evidence_lookup[reference].get(locator)
            }
            cleaned: list[Any] = []
            for reference in references:
                if isinstance(reference, str) and reference not in evidence_ids and reference in locators:
                    repairs.append({"from": reference, "to": "removed_redundant_source_locator"})
                    removed.append(reference)
                else:
                    cleaned.append(reference)
            assessment[field] = cleaned
        if removed:
            for key, value in list(assessment.items()):
                if not isinstance(value, str):
                    continue
                for locator in removed:
                    value = value.replace(", " + locator, "").replace(locator + ", ", "")
                assessment[key] = value
    return data, repairs


def run_assessment(
    *,
    env_path: Path,
    chunks_path: Path,
    base_bank_path: Path,
    output_path: Path,
    country: str = "Togo",
    stage2_max_output_tokens: int = 32768,
    progress_callback: Callable[[str], None] | None = None,
) -> Path:
    from dotenv import load_dotenv

    load_dotenv(env_path, override=False)
    langfuse = get_langfuse_client()
    stage1_prompt = get_extraction_prompt(langfuse)
    stage2_prompt = get_scoring_prompt(langfuse)
    stage1_prompt_sha256 = sha256_text(stage1_prompt.prompt)
    stage2_prompt_sha256 = sha256_text(stage2_prompt.prompt)
    stage2_prompt_crlf_sha256 = sha256_text(
        stage2_prompt.prompt.replace("\r\n", "\n").replace("\n", "\r\n")
    )
    print(
        f"PROMPTS VERIFIED | stage1=v{stage1_prompt.version} "
        f"{stage1_prompt_sha256[:12]} | stage2=P5/v{stage2_prompt.version} "
        f"{stage2_prompt_sha256[:12]}",
        flush=True,
    )
    client = build_model_client()
    model = model_name()
    runtime_identity = model_runtime_identity(model)
    chunks_root = chunks_path.resolve()
    chunks = sorted(chunks_root.rglob("*.md"))
    if not chunks:
        raise ValueError(f"No held-out chunks found in {chunks_path}")
    if progress_callback:
        progress_callback("Extracting evidence")
    base_bank_path = base_bank_path.resolve()
    base_bank = read_json(base_bank_path)
    base_items = base_bank.get("evidence_items")
    if not isinstance(base_items, list):
        raise ValueError("Base bank lacks evidence_items")
    base_bank_sha256 = hashlib.sha256(base_bank_path.read_bytes()).hexdigest()
    invocation = {
        "country": country,
        "model_runtime": runtime_identity,
        "stage1_prompt_sha256": stage1_prompt_sha256,
        "stage2_prompt_sha256": stage2_prompt_sha256,
        "stage2_max_output_tokens": stage2_max_output_tokens,
        "base_bank_sha256": base_bank_sha256,
        "chunks": [
            {
                "relative_path": path.relative_to(chunks_root).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in chunks
        ],
    }
    invocation_sha256 = sha256_text(
        json.dumps(invocation, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )

    output = output_path.resolve()
    output_preexisted = output.exists()
    stage1_dir = output / "stage1"
    stage1_dir.mkdir(parents=True, exist_ok=True)
    if not output_preexisted:
        atomic_write_text(
            output / ".gitignore",
            "# Run artifacts may contain restricted source and model data.\n*\n!.gitignore\n",
        )
    atomic_write_json(output / "prompt_stage1.json", {
        "name": stage1_prompt.name, "version": stage1_prompt.version,
        "sha256": sha256_text(stage1_prompt.prompt), "config": stage1_prompt.config,
        "prompt": stage1_prompt.prompt,
    })
    atomic_write_json(output / "prompt_stage2.json", scoring_prompt_snapshot(stage2_prompt))

    run_id = datetime.now(timezone.utc).strftime("dema-%Y%m%dT%H%M%S%fZ")
    manifest_path = output / "manifest.json"
    previous_manifest = read_json(manifest_path) if manifest_path.exists() else {}
    if previous_manifest.get("invocation_sha256") == invocation_sha256:
        run_id = previous_manifest.get("run_id", run_id)
        started_at = previous_manifest.get("started_at", utc_now())
    else:
        started_at = utc_now()
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "started_at": started_at,
        "status": "stage1_running",
        "invocation_sha256": invocation_sha256,
        "invocation": invocation,
        "country": country,
        "model": model,
        "held_out_chunk_count": len(chunks),
        "base_evidence_count": len(base_items),
        "stage1": {
            "prompt": stage1_prompt.name,
            "version": stage1_prompt.version,
            "sha256": stage1_prompt_sha256,
        },
        "stage2": {
            "prompt": stage2_prompt.name,
            "version": stage2_prompt.version,
            "sha256": stage2_prompt_sha256,
            "sha256_crlf": stage2_prompt_crlf_sha256,
        },
        "chunks": [],
    }
    atomic_write_json(manifest_path, manifest)

    all_new_items: list[dict[str, Any]] = []
    all_rejected: list[dict[str, Any]] = []
    total_usage = {"input": 0, "output": 0, "total": 0}
    for index, chunk_path in enumerate(chunks, start=1):
        original_text = chunk_path.read_text(encoding="utf-8-sig")
        metadata = chunk_metadata(chunk_path, original_text, chunks_root)
        model_input = input_with_metadata(metadata, original_text)
        input_hash = sha256_text(model_input)
        compiled = stage1_prompt.compile(Country=country, input_text=model_input)
        stage1_cache_key = {
            "country": country,
            "model_runtime": runtime_identity,
            "input_sha256": input_hash,
            "compiled_prompt_sha256": sha256_text(compiled),
            "prompt_sha256": stage1_prompt_sha256,
        }
        prefix = (
            stage1_dir
            / artifact_path_component(metadata["source_id"])
            / artifact_path_component(chunk_path.stem)
        )
        audit_path = prefix.with_suffix(".validation.json")
        cache_ok = False
        if audit_path.exists():
            audit = read_json(audit_path)
            cache_ok = (
                audit.get("status") == "validated"
                and cache_key_matches(audit, stage1_cache_key)
            )
            if cache_ok:
                accepted = audit.get("accepted_rows", [])
                rejected = audit.get("rejected_rows", [])
                call_meta = audit.get("call", {})
                print(f"STAGE 1 [{index:02d}/{len(chunks)}] RESUME {metadata['relative_path']} | "
                      f"accepted={len(accepted)} rejected={len(rejected)}", flush=True)
        if not cache_ok:
            print(f"STAGE 1 [{index:02d}/{len(chunks)}] START  {metadata['relative_path']}", flush=True)
            data, call_meta = call_model_json(
                client=client, langfuse=langfuse, prompt_object=stage1_prompt,
                compiled_prompt=compiled, stage_name="dema-stage1-held-out-extraction",
                model=model, temperature=0, max_output_tokens=int(stage1_prompt.config.get("max_output_tokens", 32768)),
                metadata={"run_id": manifest["run_id"], **metadata, "chunk_index": index,
                          "chunk_total": len(chunks), "input_sha256": input_hash},
                artifact_prefix=prefix,
            )
            accepted, rejected, envelope_errors = validate_stage1(
                data,
                original_text,
                metadata,
                prompt_name=stage1_prompt.name,
                prompt_version=stage1_prompt.version,
            )
            audit = {
                "status": "invalid" if envelope_errors else "validated",
                "validated_at": utc_now(),
                "cache_key": stage1_cache_key,
                "input_sha256": input_hash,
                "prompt_sha256": stage1_prompt_sha256,
                "metadata": metadata,
                "generated_row_count": len(data.get("dema_evidence_rows", [])),
                "accepted_count": len(accepted),
                "rejected_count": len(rejected),
                "envelope_errors": envelope_errors,
                "accepted_rows": accepted,
                "rejected_rows": rejected,
                "call": call_meta,
            }
            atomic_write_json(audit_path, audit)
            if envelope_errors:
                raise ValueError(
                    f"Stage 1 envelope mismatch for {metadata['relative_path']}: "
                    f"{envelope_errors}"
                )
            print(f"STAGE 1 [{index:02d}/{len(chunks)}] DONE   {metadata['relative_path']} | "
                  f"accepted={len(accepted)} rejected={len(rejected)} | "
                  f"{call_meta['elapsed_seconds']:.1f}s", flush=True)
        all_new_items.extend(accepted)
        all_rejected.extend({"chunk": metadata["relative_path"], **item} for item in rejected)
        for key, value in call_meta.get("usage", {}).items():
            total_usage[key] = total_usage.get(key, 0) + int(value)
        manifest["chunks"].append({
            **metadata, "input_sha256": input_hash, "accepted": len(accepted),
            "rejected": len(rejected), "call": call_meta,
        })
        manifest["stage1_completed"] = index
        manifest["stage1_accepted_rows"] = len(all_new_items)
        manifest["stage1_rejected_rows"] = len(all_rejected)
        atomic_write_json(manifest_path, manifest)

    if progress_callback:
        progress_callback("Validating evidence")
    combined_items = combine_evidence_items(base_items, all_new_items)
    if progress_callback:
        progress_callback("Building evidence bank")
    identifiers = [str(item.get("evidence_id", "")) for item in combined_items]
    evidence_lookup = {str(item["evidence_id"]): item for item in combined_items}
    scoring_scope = extract_scoring_scope(stage2_prompt.prompt)
    combined_bank = {
        "dataset_name": "combined_v4_indicator_defined_plus_held_out_frozen_stage1",
        # Stable for an identical invocation so it does not perturb Stage 2
        # prompts or invalidate otherwise reusable, verified model responses.
        "created_at_utc": manifest["started_at"],
        "country": country,
        "scoring_scope": scoring_scope,
        "instruction": "Score every indicator in scoring_scope exactly once using only evidence_items.",
        "base_bank": {
            "file_name": base_bank_path.name,
            "sha256": base_bank_sha256,
            "evidence_count": len(base_items),
        },
        "held_out_stage1": {
            "chunk_count": len(chunks), "accepted_evidence_count": len(all_new_items),
            "rejected_evidence_count": len(all_rejected),
        },
        "evidence_item_count": len(combined_items),
        "evidence_items": combined_items,
    }
    combined_path = output / "combined_evidence_bank.json"
    atomic_write_json(combined_path, combined_bank)
    atomic_write_json(output / "stage1_rejected_rows.json", all_rejected)
    manifest.update({
        "status": "stage2_running",
        "stage1_usage": total_usage,
        "combined_evidence_count": len(combined_items),
        "scoring_indicator_count": len(scoring_scope),
    })
    atomic_write_json(manifest_path, manifest)
    print(f"COMBINED BANK | base={len(base_items)} + new={len(all_new_items)} = "
          f"{len(combined_items)} evidence items | indicators={len(scoring_scope)}", flush=True)

    # P5 explicitly scores only the indicators named by scoring_scope. Small
    # batches prevent the model from abbreviating a 31-indicator response while
    # preserving the exact frozen prompt. Every batch receives the complete bank
    # because P5 requires relevance to be decided from substance, not metadata.
    stage2_items = [
        {field: item[field] for field in SCORING_EVIDENCE_FIELDS if field in item}
        for item in combined_items
    ]
    scoring_batches = build_scoring_batches(scoring_scope)
    if progress_callback:
        progress_callback("Scoring indicators")

    final_assessments: list[dict[str, Any]] = []
    batch_summaries: list[str] = []
    warnings: list[str] = []
    stage2_calls: list[dict[str, Any]] = []
    for batch_index, batch_scope in enumerate(scoring_batches, start=1):
        relevant_items = stage2_items
        codes = [item["indicator_code"] for item in batch_scope]
        batch_instruction = "Score every indicator in scoring_scope exactly once using only evidence_items."
        if codes == ["A.1.3"]:
            batch_instruction = (
                "Score A.1.3 exactly once using only evidence_items. Follow the frozen P5 JSON schema "
                "exactly: phase_score must be an integer; score_reasoning must be 180-350 words; "
                "evidence_supporting_score and contrary_or_limiting_evidence must each be JSON arrays "
                "containing only the few evidence_id strings actually cited (use [] when none). "
                "Do not enumerate the bank."
            )
        batch_bank = {
            **{key: value for key, value in combined_bank.items() if key not in {"scoring_scope", "evidence_items"}},
            "scoring_scope": batch_scope,
            "instruction": batch_instruction,
            "evidence_item_count": len(relevant_items),
            "evidence_items": relevant_items,
        }
        databank = json.dumps(batch_bank, ensure_ascii=False, indent=2)
        compiled_stage2 = stage2_prompt.compile(databank=databank)
        stage2_cache_key = {
            "country": country,
            "model_runtime": runtime_identity,
            "scope": codes,
            "databank_sha256": sha256_text(databank),
            "compiled_prompt_sha256": sha256_text(compiled_stage2),
            "prompt_sha256": stage2_prompt_sha256,
            "max_output_tokens": stage2_max_output_tokens,
        }
        batch_slug = (
            f"batch_{batch_index:02d}_{codes[0].replace('.', '_')}_to_"
            f"{codes[-1].replace('.', '_')}_fullbank"
        )
        if codes == ["A.1.3"]:
            batch_slug += "_schema_retry"
        batch_prefix = output / "stage2" / batch_slug
        validated_path = batch_prefix.with_suffix(".validated.json")
        validated_cache_ok = False
        if validated_path.exists():
            cached_validation = read_json(validated_path)
            validated_cache_ok = cache_key_matches(cached_validation, stage2_cache_key)
        if validated_cache_ok:
            batch_result = cached_validation["result"]
            batch_warnings = cached_validation.get("warnings", [])
            batch_meta = cached_validation.get("call", {})
            validate_stage2(batch_result, batch_scope, set(identifiers))
            print(f"STAGE 2 [{batch_index:02d}/{len(scoring_batches)}] RESUME "
                  f"{','.join(codes)}", flush=True)
        else:
            parsed_path = batch_prefix.with_suffix(".json")
            response_path = batch_prefix.with_suffix(".response.json")
            request_path = batch_prefix.with_suffix(".request.json")
            request_record = read_json(request_path) if request_path.exists() else {}
            reusable_response = (
                parsed_path.exists()
                and response_path.exists()
                and request_record.get("model") == model
                and request_record.get("max_output_tokens") == stage2_max_output_tokens
                and request_record.get("compiled_prompt_sha256")
                == stage2_cache_key["compiled_prompt_sha256"]
                and request_record.get("metadata", {}).get("country") == country
                and request_record.get("metadata", {}).get("scoring_scope") == codes
                and request_record.get("metadata", {}).get("combined_bank_sha256")
                == stage2_cache_key["databank_sha256"]
            )
            if reusable_response:
                batch_result = read_json(parsed_path)
                response_record = read_json(response_path)
                batch_meta = {
                    "response_id": response_record.get("id"),
                    "usage": response_record.get("usage", {}),
                    "elapsed_seconds": 0,
                    "reused_completed_response": True,
                }
                print(f"STAGE 2 [{batch_index:02d}/{len(scoring_batches)}] REUSE  "
                      f"{','.join(codes)}", flush=True)
            else:
                print(f"STAGE 2 [{batch_index:02d}/{len(scoring_batches)}] START  "
                      f"{','.join(codes)} | evidence={len(relevant_items)} | "
                      f"input_chars={len(compiled_stage2):,}", flush=True)
                batch_result, batch_meta = call_model_json(
                    client=client, langfuse=langfuse, prompt_object=stage2_prompt,
                    compiled_prompt=compiled_stage2, stage_name="dema-stage2-final-maturity-scoring-p5",
                    model=model, temperature=0, max_output_tokens=stage2_max_output_tokens,
                    metadata={"run_id": manifest["run_id"], "country": country,
                              "batch_index": batch_index, "batch_total": len(scoring_batches),
                              "scoring_scope": codes, "evidence_count": len(relevant_items),
                              "combined_bank_sha256": sha256_text(databank)},
                    artifact_prefix=batch_prefix, json_mode=True,
                )
            batch_result, citation_repairs = repair_evidence_id_padding(
                batch_result,
                set(identifiers),
                prefix="V4ID",
                match_suffix=True,
            )
            batch_result, locator_repairs = remove_redundant_source_locator_citations(
                batch_result, evidence_lookup
            )
            citation_repairs.extend(locator_repairs)
            batch_warnings = validate_stage2(batch_result, batch_scope, set(identifiers))
            atomic_write_json(validated_path, {
                "validated_at": utc_now(), "warnings": batch_warnings,
                "citation_repairs": citation_repairs, "call": batch_meta,
                "cache_key": stage2_cache_key,
                "result": batch_result,
            })
            print(f"STAGE 2 [{batch_index:02d}/{len(scoring_batches)}] DONE   "
                  f"{','.join(codes)} | {batch_meta['elapsed_seconds']:.1f}s | "
                  f"warnings={len(batch_warnings)} repairs={len(citation_repairs)}", flush=True)
        final_assessments.extend(batch_result["indicator_assessments"])
        summary = batch_result.get("assessment_summary")
        if isinstance(summary, str) and summary.strip():
            batch_summaries.append(summary.strip())
        warnings.extend(f"batch {batch_index}: {warning}" for warning in batch_warnings)
        stage2_calls.append({"batch": batch_index, "scope": codes, **batch_meta})
        manifest["stage2_batches_completed"] = batch_index
        manifest["stage2_calls"] = stage2_calls
        atomic_write_json(manifest_path, manifest)

    # A later targeted batch intentionally replaces an earlier assessment with
    # the same code. Restore authoritative framework order after last-write-wins.
    assessments_by_code = {
        assessment["indicator_code"]: assessment for assessment in final_assessments
    }
    final_assessments = [
        assessments_by_code[item["indicator_code"]] for item in scoring_scope
    ]
    retry_batch_number = len(scoring_batches)
    warnings = [
        warning for warning in warnings
        if "A.1.3:" not in warning or warning.startswith(f"batch {retry_batch_number}:")
    ]
    final_score = {
        "country": country,
        "framework_version": "current DEMA maturity framework supplied in frozen Stage 2 P5",
        "assessment_summary": "\n\n".join(batch_summaries),
        "indicator_assessments": final_assessments,
    }
    # Revalidate the combined result for completeness and citation integrity;
    # batch warnings are already retained with their batch context above.
    validate_stage2(final_score, scoring_scope, set(identifiers))
    stage2_prefix = output / "stage2" / "final_score"
    atomic_write_json(stage2_prefix.with_suffix(".json"), final_score)
    atomic_write_json(stage2_prefix.with_suffix(".validated.json"), {
        "validated_at": utc_now(), "warnings": warnings, "result": final_score,
    })
    manifest.update({
        "status": "complete", "completed_at": utc_now(), "stage2_calls": stage2_calls,
        "stage2_validation_warnings": warnings,
    })
    atomic_write_json(manifest_path, manifest)
    langfuse.flush()
    print(f"STAGE 2 DONE | assessments={len(final_score['indicator_assessments'])} | "
          f"batches={len(scoring_batches)} | warnings={len(warnings)}", flush=True)
    print(f"COMPLETE | {stage2_prefix.with_suffix('.validated.json')}", flush=True)
    return stage2_prefix.with_suffix(".validated.json")
