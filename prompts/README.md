# Production prompts

These two text files are the complete prompts used by the pipeline:

- `stage1-evidence-extraction.txt`: extract documentary evidence from one
  reviewed Markdown chunk at a time.
- `stage2-maturity-scoring.txt`: score the in-scope maturity indicators from
  the validated combined evidence bank.

The pipeline reads these files directly. Red Cross staff do not need Langfuse
access to run the assessment.

## Runtime inputs

Stage 1 has two placeholders:

- `{{Country}}` receives the `--country` command-line value.
- `{{input_text}}` receives one complete Markdown chunk, preceded by a short
  traceability header containing its source and processing-unit metadata.

Stage 2 has one placeholder:

- `{{databank}}` receives the complete combined evidence-bank JSON for the
  current scoring batch, including its `scoring_scope`.

`manifest.json` records each prompt's original Langfuse name and version,
expected variables, file name, and SHA-256 hash. The application verifies both
the variables and hash before any model call. An accidental prompt edit will
therefore stop the run instead of silently changing the methodology.

## Updating a prompt

Prompt changes are methodological changes. An authorized maintainer should:

1. replace the relevant `.txt` file with the reviewed prompt;
2. update its name/version, expected variables, and SHA-256 in `manifest.json`;
3. run the complete unit suite and a reviewed end-to-end assessment;
4. commit the prompt, manifest, and review record together.

Langfuse may still be enabled for optional tracing, but it is not a prompt
source and does not control which prompt text is executed.
