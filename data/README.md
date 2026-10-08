# Input data

Input material is deliberately excluded from this repository until its
redistribution rights and sensitivity have been reviewed.

If starting from PDF or HTML, use the optional Stage 0 command documented in
`docs/STAGE0.md`. It produces `prepared_data/chunks/`; pass that path to
`main.py --chunks`. Staff may skip Stage 0 when reviewed Markdown already
exists.

To run with the default paths, provide:

- `data/chunks/**/*.md`: prepared Markdown source chunks. Each chunk should
  include `source_id` and `source_url` fields in its metadata.
- `data/base_evidence_bank.json`: a JSON object containing an
  `evidence_items` array.

Alternatively, pass different locations with `--chunks` and `--base-bank`.
Do not commit confidential documents, API responses, or files containing
personal local paths.
