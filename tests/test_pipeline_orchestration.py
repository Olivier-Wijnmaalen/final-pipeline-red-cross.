import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from dema import pipeline


class FakePrompt:
    def __init__(self, name, version, prompt):
        self.name = name
        self.version = version
        self.prompt = prompt
        self.config = {"max_output_tokens": 2048}

    def compile(self, **variables):
        return self.prompt + "\n" + json.dumps(variables, ensure_ascii=False, sort_keys=True)


class FakeLangfuse:
    def flush(self):
        return None


class PipelineOrchestrationTests(unittest.TestCase):
    def test_mocked_end_to_end_run_and_cache_invalidation(self):
        extraction_prompt = FakePrompt("extraction", 6, "Extract {{input_text}} for {{Country}}")
        scoring_prompt = FakePrompt(
            "scoring",
            1,
            "INDICATOR A.1.1 — Actor roles\nINDICATOR A.1.3 — Coordination\n{{databank}}",
        )
        calls = []

        def fake_call_model_json(**kwargs):
            calls.append((kwargs["stage_name"], kwargs["metadata"]))
            if kwargs["stage_name"].startswith("dema-stage1"):
                metadata = kwargs["metadata"]
                return (
                    {
                        "source_id": metadata["source_id"],
                        "processing_unit_id": metadata["processing_unit_id"],
                        "dema_evidence_rows": [
                            {
                                "evidence_id": "SYNTH-0002",
                                "subdimension": "A.1",
                                "evidence_scope": "country",
                                "country_specificity": "Synthetic",
                                "supporting_quote": "Synthetic evidence quotation.",
                                "evidence_statement": "A synthetic statement.",
                                "interpretation_boundary": "Demonstration data only.",
                                "page_number": "1",
                            }
                        ],
                    },
                    {"response_id": "stage1", "usage": {}, "elapsed_seconds": 0.01},
                )

            assessments = []
            for code in kwargs["metadata"]["scoring_scope"]:
                assessments.append(
                    {
                        "indicator_code": code,
                        "phase_score": 1,
                        "evidence_supporting_score": ["SYNTH-0001"],
                        "contrary_or_limiting_evidence": [],
                        "assigned_phase_requirement_checks": [{"status": "SUPPORTED"}],
                        "score_reasoning": "word " * 180,
                    }
                )
            return (
                {"assessment_summary": "Synthetic run.", "indicator_assessments": assessments},
                {"response_id": "stage2", "usage": {}, "elapsed_seconds": 0.01},
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            example_root = Path(__file__).resolve().parents[1] / "examples" / "synthetic"
            chunks = example_root / "chunks"
            bank = example_root / "base_evidence_bank.json"
            output = root / "output"

            patches = (
                patch.object(pipeline, "get_langfuse_client", return_value=FakeLangfuse()),
                patch.object(pipeline, "get_extraction_prompt", return_value=extraction_prompt),
                patch.object(pipeline, "get_scoring_prompt", return_value=scoring_prompt),
                patch.object(pipeline, "build_model_client", return_value=SimpleNamespace()),
                patch.object(pipeline, "model_name", return_value="test-model"),
                patch.object(pipeline, "call_model_json", side_effect=fake_call_model_json),
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
                result = pipeline.run_assessment(
                    env_path=root / ".env",
                    chunks_path=chunks,
                    base_bank_path=bank,
                    output_path=output,
                    country="Synthetic",
                )
                first_call_count = len(calls)
                self.assertTrue(result.exists())
                self.assertTrue((output / ".gitignore").exists())
                self.assertEqual(first_call_count, 3)

                pipeline.run_assessment(
                    env_path=root / ".env",
                    chunks_path=chunks,
                    base_bank_path=bank,
                    output_path=output,
                    country="Synthetic",
                )
                self.assertEqual(len(calls), first_call_count)

                pipeline.run_assessment(
                    env_path=root / ".env",
                    chunks_path=chunks,
                    base_bank_path=bank,
                    output_path=output,
                    country="Different country",
                )
                self.assertEqual(len(calls), first_call_count * 2)

            combined = json.loads((output / "combined_evidence_bank.json").read_text())
            self.assertNotIn("path", combined["base_bank"])
            self.assertEqual(combined["base_bank"]["file_name"], bank.name)


if __name__ == "__main__":
    unittest.main()
