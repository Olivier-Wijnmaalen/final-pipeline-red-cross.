import unittest
from types import SimpleNamespace

from dema import config, pipeline
from dema.llm import parse_json_response
from dema.prompts import scoring_prompt_snapshot


class PipelineBoundaryTests(unittest.TestCase):
    def test_json_response_accepts_fenced_object(self):
        self.assertEqual(
            parse_json_response('```json\n{"ok": true}\n```'),
            {"ok": True},
        )

    def test_stage1_accepts_exact_quote_and_preserves_traceability(self):
        metadata = {
            "source_id": "001",
            "source_file": "001_chunk.md",
            "source_url": "https://example.test/source",
            "processing_unit_id": "001_chunk",
            "relative_path": "001/001_chunk.md",
        }
        row = {
            "evidence_id": "E-001",
            "subdimension": "A.1",
            "evidence_scope": "country",
            "country_specificity": "Togo",
            "supporting_quote": "Exact quotation",
            "evidence_statement": "A statement",
            "interpretation_boundary": "Documentary evidence only",
            "page_number": "1",
        }

        accepted, rejected, errors = pipeline.validate_stage1(
            {"dema_evidence_rows": [row]}, "Text with Exact quotation in it.", metadata
        )

        self.assertFalse(rejected)
        self.assertFalse(errors)
        self.assertEqual(accepted[0]["source_chunk"], "001/001_chunk.md")
        self.assertEqual(
            accepted[0]["stage1_prompt_version"],
            config.EXTRACTION_PROMPT_VERSION,
        )

    def test_stage1_rejects_non_verbatim_quote(self):
        metadata = {
            "source_id": "001",
            "source_file": "001_chunk.md",
            "source_url": "",
            "processing_unit_id": "001_chunk",
            "relative_path": "001/001_chunk.md",
        }
        row = {
            "evidence_id": "E-002",
            "subdimension": "A.1",
            "evidence_scope": "country",
            "country_specificity": "Togo",
            "supporting_quote": "Not present",
            "evidence_statement": "A statement",
            "interpretation_boundary": "Documentary evidence only",
            "page_number": "1",
        }

        accepted, rejected, _ = pipeline.validate_stage1(
            {"dema_evidence_rows": [row]}, "Different source text", metadata
        )

        self.assertFalse(accepted)
        self.assertIn("quote_not_exact_contiguous_substring", rejected[0]["reasons"])

    def test_stage1_does_not_accept_quote_from_injected_metadata(self):
        metadata = {
            "source_id": "metadata-only-value",
            "source_file": "001_chunk.md",
            "source_url": "https://example.test/source",
            "processing_unit_id": "001_chunk",
            "relative_path": "001/001_chunk.md",
        }
        row = {
            "evidence_id": "E-003",
            "subdimension": "A.1",
            "evidence_scope": "country",
            "country_specificity": "Togo",
            "supporting_quote": "metadata-only-value",
            "evidence_statement": "A statement",
            "interpretation_boundary": "Documentary evidence only",
            "page_number": "1",
        }

        accepted, rejected, _ = pipeline.validate_stage1(
            {"dema_evidence_rows": [row]}, "Actual source body", metadata
        )

        self.assertFalse(accepted)
        self.assertIn("quote_not_exact_contiguous_substring", rejected[0]["reasons"])

    def test_cache_keys_require_an_exact_match(self):
        expected = {"country": "Togo", "model": "deployment-a"}
        self.assertTrue(pipeline.cache_key_matches({"cache_key": expected}, expected))
        self.assertFalse(
            pipeline.cache_key_matches(
                {"cache_key": {"country": "Togo"}}, expected
            )
        )
        self.assertFalse(pipeline.cache_key_matches({}, expected))

    def test_artifact_path_components_cannot_traverse(self):
        component = pipeline.artifact_path_component("../../restricted/source")
        self.assertNotIn("/", component)
        self.assertNotIn("\\", component)
        self.assertNotIn("..", component)

    def test_scoring_scope_is_derived_from_prompt(self):
        prompt = (
            "INDICATOR A1.1 — Actor roles\n"
            "INDICATOR B.2.1. — Interoperability\n"
        )
        self.assertEqual(
            pipeline.extract_scoring_scope(prompt),
            [
                {"indicator_code": "A.1.1", "indicator_name": "Actor roles"},
                {"indicator_code": "B.2.1", "indicator_name": "Interoperability"},
            ],
        )

    def test_evidence_aggregation_preserves_items_and_rejects_duplicate_ids(self):
        base = [{"evidence_id": "BASE-1", "supporting_quote": "Base"}]
        extracted = [{"evidence_id": "NEW-1", "supporting_quote": "New"}]
        combined = pipeline.combine_evidence_items(base, extracted)
        self.assertEqual([item["evidence_id"] for item in combined], ["BASE-1", "NEW-1"])
        with self.assertRaisesRegex(ValueError, "duplicates"):
            pipeline.combine_evidence_items(base, [{"evidence_id": "BASE-1"}])

    def test_stage2_rejects_unknown_evidence_ids(self):
        result = {
            "indicator_assessments": [
                {
                    "indicator_code": "A.1.1",
                    "phase_score": 3,
                    "evidence_supporting_score": ["UNKNOWN"],
                    "contrary_or_limiting_evidence": [],
                    "assigned_phase_requirement_checks": [
                        {"status": "SUPPORTED"}
                    ],
                    "score_reasoning": "word " * 180,
                }
            ]
        }
        with self.assertRaisesRegex(ValueError, "unknown IDs"):
            pipeline.validate_stage2(
                result,
                [{"indicator_code": "A.1.1", "indicator_name": "Actor roles"}],
                {"E-001"},
            )

    def test_evidence_id_padding_repair_is_prefix_specific(self):
        repaired, repairs = pipeline.repair_evidence_id_padding(
            {"references": ["EV-7", "V4ID-7"]},
            {"EV-0007"},
            prefix="EV",
        )
        self.assertEqual(repaired, {"references": ["EV-0007", "V4ID-7"]})
        self.assertEqual(repairs, [{"from": "EV-7", "to": "EV-0007"}])

    def test_scoring_prompt_snapshot_preserves_reproducibility_fields(self):
        prompt = SimpleNamespace(
            name="scoring",
            version=3,
            prompt="Line 1\nLine 2",
            config={"temperature": 0},
        )
        snapshot = scoring_prompt_snapshot(prompt)
        self.assertEqual(snapshot["name"], "scoring")
        self.assertEqual(snapshot["version"], 3)
        self.assertEqual(snapshot["config"], {"temperature": 0})
        self.assertEqual(snapshot["prompt"], prompt.prompt)
        self.assertNotEqual(snapshot["api_sha256"], snapshot["crlf_sha256"])


if __name__ == "__main__":
    unittest.main()
