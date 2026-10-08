# DEMA documentary pre-assessment pipeline and visualizer

A reproducible implementation of the two-stage DEMA documentary pre-assessment
pipeline. It was prepared for a Togo pre-assessment and is intended for an
access-controlled Red Cross production and research environment.

The generated assessment is decision support, not an autonomous finding. A
qualified reviewer must inspect source traceability, rejected evidence,
validation warnings, and maturity reasoning before results are used or shared.

## Method

```text
Local PDF/HTML sources
  -> Stage 0: Docling conversion, OCR disabled, 10-page PDF chunks
  -> reviewed Markdown chunks
  -> Stage 1: evidence extraction
  -> validated combined evidence bank
  -> Stage 2: maturity scoring
  -> validated assessment
  -> Stage 3: dashboard adapter and internal visualizer
```

Stage 0 is optional when reviewed Markdown chunks already exist. The evidence
bank is an explicit methodological boundary: extraction and scoring are never
combined into a single model call. Each call stores request metadata, the raw
response, parsed JSON, validation results, prompt identity, and token usage.
Optional Langfuse tracing can also be enabled. Validated work can be resumed.

## Repository contents

- `main.py`: command-line entry point.
- `prepare_documents.py`: optional PDF/HTML-to-Markdown Stage 0 entry point.
- `dema/stage0.py`: OCR-disabled conversion and 10-page PDF chunking.
- `dema/pipeline.py`: orchestration and validation for both stages.
- `dema/prompts.py`: verified loading of the committed local prompts.
- `dema/llm.py`: OpenAI Responses API calls.
- `dema/config.py`: default paths and pinned prompt identities.
- `dema/storage.py`: atomic persistence and hashing helpers.
- `dashboard_adapter/`: validated outputs to the stable dashboard-data contract.
- `build_dashboard.py`: rebuild Stage 3 data for an existing completed run.
- `web/`: empty-by-default internal upload application and visualizer.
- `tests/`: credential-free unit and mocked orchestration tests.
- `examples/synthetic/`: fictional inputs and an illustrative output.
- `prompts/`: approved Stage 1 and Stage 2 prompt text, staff notes, and a
  provenance manifest.
- `docs/CONFIGURATION.md`: configuration-template and runtime-setting guide.
- `docs/STAGE0.md`: plain-language conversion, review, and chunking notes.
- `docs/architecture.md`: application and job-runner boundaries.
- `docs/dashboard-data-contract.md`: the Stage 3 input contract.
- `docs/deployment.md`: local and Red Cross-managed Vercel setup.
- `docs/security-and-data-handling.md`: upload, retention, and access decisions.
- `requirements-stage0.txt`: optional pinned Docling installation.
- `requirements-tracing.txt`: optional Langfuse tracing installation.
- `data/README.md`: real-input format and publication boundary.
- `SECURITY.md`: credential, disclosure, and data-handling guidance.

Research experiments, thesis documents, real generated outputs, downloaded
source documents, and the presentation dashboard are outside this repository.

## Requirements

- Python 3.12 (the version exercised in CI; newer versions may also work)
- an Azure OpenAI or OpenAI API deployment supporting the Responses API
- the two approved prompt files already committed under `prompts/`
- reviewed Markdown chunks and a base evidence bank

Docling is optional and deliberately excluded from the core requirements. It
is needed only when staff must create reviewed Markdown from PDF or HTML.

The committed prompt files are the pipeline's source of truth:

- `prompts/stage1-evidence-extraction.txt`: Stage 1 evidence extraction;
- `prompts/stage2-maturity-scoring.txt`: Stage 2 maturity scoring.

Stage 1 substitutes the country into `{{Country}}` and one complete reviewed
Markdown chunk into `{{input_text}}`. Stage 2 substitutes the combined evidence
bank JSON into `{{databank}}`. The manifest records the original Langfuse names
and versions and pins the files by SHA-256 hash, so accidental changes stop the
run. Red Cross staff do not need Langfuse access to inspect or use the prompts.
See [the prompt notes](prompts/README.md).

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill in `.env` locally. Never commit it. Place approved inputs at the default
locations documented in `data/README.md`, or provide explicit paths. See
`docs/CONFIGURATION.md` for every setting and an explanation of configuration
templates.

To include Stage 0 in the installation:

```powershell
python -m pip install -r requirements-stage0.txt
```

To send optional traces to an approved Langfuse project:

```powershell
python -m pip install -r requirements-tracing.txt
```

## Stage 0: prepare documents

Place approved PDF or HTML files in the ignored `source_documents/` directory:

```powershell
python prepare_documents.py
```

Stage 0 converts PDF, HTML, and DOCX locally with Docling, accepts reviewed
Markdown directly, never enables OCR, and writes full
Markdown plus non-overlapping PDF chunks of pages 1–10, 11–20, and so on to
the ignored `prepared_data/` directory. HTML has no stable page model, so each
HTML file becomes one logical chunk.

OCR-disabled conversion only works for PDFs with an embedded text layer. A
scanned PDF that produces no text is reported as a failure and must not proceed
to Stage 1. Staff must compare converted Markdown with its source before use.
See [the Stage 0 notes](docs/STAGE0.md) for the exact boundary and review steps.

## Run

Using the default Togo configuration:

```powershell
python main.py
```

Using explicit inputs and output location:

```powershell
python main.py `
  --chunks prepared_data\chunks `
  --base-bank C:\path\to\base_evidence_bank.json `
  --output C:\path\to\run-output `
  --country Togo
```

The default output directory is `dema_run/`. It is intentionally ignored by
Git because it can contain source quotations, model responses, trace
identifiers, and other material requiring review. Newly created run directories
also receive their own deny-by-default `.gitignore` file.

Use a new output directory for an intentionally separate assessment. Reusing
an output directory is supported only for resuming the same invocation. Cache
records are verified against the country, model, source input, evidence bank,
compiled prompt, prompt version, and relevant generation settings. Incomplete,
legacy, or mismatched cache records are regenerated.

## Test

```powershell
python -m unittest discover -s tests -v
```

The visualizer has its own reproducible checks:

```powershell
cd web
npm ci
npm run typecheck
npm test
npm run build
```

## Stage 3: internal visualizer

The visualizer starts empty. It never includes the historical 2 September
assessment. A result appears only after the fictional sample is selected or a
new run completes using this repository's approved prompts.

To start it locally:

```powershell
python -m pip install -r requirements-stage0.txt
cd web
npm ci
npm run dev
```

Open `http://localhost:3000`. **Run synthetic sample** works without provider
credentials or paid calls. Live mode accepts one approved PDF, DOCX, or
Markdown file (maximum 25 MB), stores it under ignored `runs/<run-id>/`, and
starts the authoritative Python pipeline. Configure the root `.env` first.

Two evidence modes are explicit:

- **Document only** uses an empty baseline bank and leaves unsupported
  indicators unscored.
- **Baseline plus uploaded document** requires `DEMA_BASELINE_BANK` to point to
  an approved bank; the interface labels the resulting provenance.

The adapter combines `stage2/final_score.validated.json`,
`combined_evidence_bank.json`, and `manifest.json` into `dashboard-data.json`.
The visualizer reads only this versioned contract. See
[the architecture](docs/architecture.md) and
[dashboard contract](docs/dashboard-data-contract.md).

For Vercel, use the private GitHub repository with `web` as the root directory.
The sample can run there directly; live processing requires an approved remote
worker and durable run storage. Full settings and protection requirements are
in [the deployment guide](docs/deployment.md).

**Internal demo URL:** _add the Red Cross-managed protected URL after deployment_.

The same command runs in GitHub Actions. Verification has two layers:

- a mocked end-to-end test exercises both stages, persistence, resume behavior,
  and cache invalidation with `examples/synthetic/` and no credentials;
- Stage 0 unit tests verify deterministic 10-page boundaries, HTML handling,
  metadata, and safe source identifiers without loading Docling models;
- a real end-to-end run requires approved inputs and model API credentials;
  Langfuse is optional and is used only for tracing when explicitly enabled.

CI also compiles the Python sources and checks the installed package set for
dependency conflicts. Dependabot monitors Python and GitHub Actions versions.

## Reproducibility record

Every real run directory contains prompt snapshots, request metadata, raw and
parsed model responses, validation artifacts, the evidence-bank hash, per-call
usage, and a manifest with a complete invocation fingerprint. The fingerprint
prevents outputs from another country, model, input set, or prompt compilation
from being silently resumed.

Exact model outputs can still vary when a provider changes the implementation
behind a deployment name. Preserve the provider and deployment configuration,
run manifest, and reviewed result together when archiving a research result.

## Data protection

Real source chunks, evidence banks, generated results, `.env`, and Langfuse
exports are excluded from Git by default. Treat model responses and quotations
as potentially sensitive. Follow [SECURITY.md](SECURITY.md) and complete the
applicable Red Cross review before adding any non-synthetic artifact.

The ignored `source_documents/` and `prepared_data/` directories are the Stage
0 confidentiality boundary. Only the fictional example under `examples/` is
intended for Git.

## Known methodological boundaries

- Documentary absence is not proof that a capability or practice is absent.
- With OCR disabled, scanned/image-only text is outside the pipeline scope.
- Docling conversion and page chunking require source-to-Markdown review.
- Evidence extraction and scoring remain model-assisted and require review.
- Stage 2 receives the full evidence bank in each scoring batch; this improves
  substantive matching but increases token usage.
- Validation checks structure, citation identifiers, exact Stage 1 quotations,
  score range, and scoring coverage. It cannot establish whether an
  interpretation is substantively correct.

## Before internal handover

1. Create a private repository in the approved Red Cross GitHub organization.
2. Confirm the approved copyright/license or internal-use notice.
3. Review and commit both locally frozen prompt files and their manifest.
4. Perform one real end-to-end run with approved inputs and archive its
   manifest and reviewed result outside Git.
5. Review the staged file list and Git history for credentials or restricted
   data, then require the GitHub Actions checks before merging.
6. Record the repository owner and private security contact in GitHub.

No credentials, real source corpus, generated assessment, or personal
filesystem paths are included in this repository. The only committed input is
explicitly fictional synthetic test data.
