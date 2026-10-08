# Synthetic input example

These files demonstrate the input layout without containing Red Cross data,
personal data, or real assessment evidence. They are intentionally too small
to support a substantive maturity assessment.

The automated orchestration test uses these inputs with mocked Langfuse and
model clients. This verifies the complete two-stage control flow, persistence,
validation, resumption, and cache invalidation without credentials or network
calls.

`expected/final_score.validated.json` is a short, human-readable shape example.
It is deliberately marked synthetic and is not used as a substantive expected
score. The automated test generates and validates complete 180-word reasoning.

Running these files through the real models would incur API usage and should
only be done in an approved test project:

```powershell
python main.py `
  --chunks examples\synthetic\chunks `
  --base-bank examples\synthetic\base_evidence_bank.json `
  --output synthetic_run `
  --country Synthetic
```

`synthetic_run/` is ignored by Git through the general `*_run/` rule.
