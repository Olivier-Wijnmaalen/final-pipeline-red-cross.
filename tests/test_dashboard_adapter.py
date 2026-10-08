import unittest
from pathlib import Path
from dashboard_adapter import build_dashboard_data

ROOT = Path(__file__).resolve().parents[1]

class DashboardAdapterTests(unittest.TestCase):
    def setUp(self):
        self.prompt = (ROOT / "prompts/stage2-maturity-scoring.txt").read_text(encoding="utf-8")
        self.bank = {"evidence_items": [{"evidence_id": "E-1", "supporting_quote": "Exact quote", "source_file": "sample.md"}]}
        self.manifest = {"run_id": "dema-test", "status": "complete", "assessment_mode": "document_only"}

    def test_contract_contains_full_framework_and_unscored_indicators(self):
        stage2 = {"result": {"country": "Synthetic", "indicator_assessments": [{"indicator_code": "A.1.1", "phase_score": 1, "evidence_supporting_score": ["E-1"], "contrary_or_limiting_evidence": [], "assigned_phase_requirement_checks": [{"status": "SUPPORTED"}]}]}}
        data = build_dashboard_data(stage2, self.bank, self.manifest, self.prompt)
        indicators = [i for d in data["dimensions"] for s in d["subdimensions"] for i in s["indicators"]]
        self.assertEqual(len(data["dimensions"]), 3)
        self.assertEqual(sum(len(d["subdimensions"]) for d in data["dimensions"]), 8)
        self.assertEqual(len(indicators), 31)
        self.assertEqual(data["run"]["assessment_mode"], "document_only")
        self.assertEqual(indicators[0]["supporting_evidence"][0]["supporting_quote"], "Exact quote")
        self.assertEqual(indicators[1]["score_status"], "insufficient_evidence")

    def test_unknown_evidence_id_fails(self):
        stage2 = {"indicator_assessments": [{"indicator_code": "A.1.1", "phase_score": 1, "evidence_supporting_score": ["MISSING"], "contrary_or_limiting_evidence": []}]}
        with self.assertRaisesRegex(ValueError, "unknown evidence"):
            build_dashboard_data(stage2, self.bank, self.manifest, self.prompt)

if __name__ == "__main__": unittest.main()
