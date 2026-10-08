import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dema import prompts
from dema.storage import sha256_text


class FrozenPromptTests(unittest.TestCase):
    def test_local_prompt_is_hash_verified_and_compiled(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            text = "Assess {{ country }} using {{evidence}}."
            (root / "stage1.txt").write_text(text, encoding="utf-8", newline="\n")
            manifest = {
                "prompts": {
                    "stage1": {
                        "name": "stage1",
                        "version": 7,
                        "file": "stage1.txt",
                        "sha256": sha256_text(text),
                        "expected_variables": ["country", "evidence"],
                        "config": {"max_output_tokens": 100},
                    }
                }
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with patch.object(prompts, "PROMPT_ROOT", root), patch.object(
                prompts, "PROMPT_MANIFEST", manifest_path
            ):
                prompt = prompts.load_frozen_prompt("stage1")
                self.assertIsNotNone(prompt)
                self.assertEqual(
                    prompt.compile(country="Synthetic", evidence="E-1"),
                    "Assess Synthetic using E-1.",
                )

                (root / "stage1.txt").write_text("changed", encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "hash mismatch"):
                    prompts.load_frozen_prompt("stage1")

    def test_committed_prompts_accept_pipeline_inputs(self):
        stage1 = prompts.load_frozen_prompt("stage1")
        compiled_stage1 = stage1.compile(Country="Togo", input_text="CHUNK BODY")
        self.assertIn("CHUNK BODY", compiled_stage1)
        self.assertNotIn("{{Country}}", compiled_stage1)
        self.assertNotIn("{{input_text}}", compiled_stage1)

        stage2 = prompts.load_frozen_prompt("stage2")
        compiled_stage2 = stage2.compile(databank='{"evidence_items": []}')
        self.assertIn('"evidence_items": []', compiled_stage2)
        self.assertNotIn("{{databank}}", compiled_stage2)

    def test_unresolved_local_prompt_variables_fail(self):
        prompt = prompts.FrozenPrompt(
            name="test",
            version=1,
            prompt="{{known}} {{missing}}",
            config={},
        )
        with self.assertRaisesRegex(ValueError, "missing"):
            prompt.compile(known="value")

    def test_noop_langfuse_supports_offline_tracing_calls(self):
        client = prompts.NoopLangfuse()
        with client.start_as_current_observation(name="test") as generation:
            generation.update(output={"ok": True})
        client.flush()


if __name__ == "__main__":
    unittest.main()
