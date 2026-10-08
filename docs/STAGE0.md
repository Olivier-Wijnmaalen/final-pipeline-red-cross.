# Stage 0: document preparation

Stage 0 converts local PDF, HTML, and DOCX source documents to Markdown, accepts
reviewed Markdown directly, and prepares
the chunks consumed by Stage 1. It is optional: staff who already have reviewed
Markdown chunks can start directly at Stage 1.

## Deliberate boundaries

- `.pdf`, `.html`, `.htm`, `.docx`, `.md`, and `.markdown` are accepted.
- OCR is always disabled. PDF text must already be selectable/embedded.
- A scanned PDF can therefore produce no text and will be reported as a
  failure. Stage 0 never silently changes methodology by enabling OCR.
- PDF chunks contain pages 1–10, 11–20, and so on. The final chunk may contain
  fewer than ten pages.
- HTML, DOCX, and Markdown do not have stable PDF pages, so each becomes one
  logical chunk.
- Input files, converted Markdown, chunks, and manifests stay outside Git.

Docling handles PDF, HTML, and DOCX input and Markdown export. Reviewed
Markdown is copied without conversion. The PDF configuration
sets `do_ocr=False` and uses the native PDF text backend. Page and picture image
generation and code/formula enrichment are disabled to keep preparation lean.
Table structure processing remains enabled because tables can contain relevant
assessment evidence.

## Install

Use a dedicated virtual environment, then install the optional Stage 0
dependencies:

```powershell
python -m pip install -r requirements-stage0.txt
```

The core `requirements.txt` intentionally excludes Docling so staff who start
from reviewed Markdown do not install its document-processing dependencies.
The first Docling conversion can take longer while its processing components
initialize.

## Run

Place approved local documents in `source_documents/`, then run:

```powershell
python prepare_documents.py
```

This creates a new ignored `prepared_data/` directory:

```text
prepared_data/
  converted/     full Markdown conversions
  chunks/        non-overlapping Stage 1 inputs
  manifest.json  hashes, versions, page ranges, and conversion status
```

The output directory must be new or empty. This prevents old chunks from an
earlier conversion being mixed into a new assessment.

To try the fictional HTML example:

```powershell
python prepare_documents.py `
  --input examples\stage0\source `
  --output synthetic_prepared
```

## Mandatory review

Before Stage 1, review the converted Markdown against each source, especially
headings, reading order, tables, page boundaries, and missing text. Resolve all
manifest failures. HTML conversions can retain menus, feedback controls,
related-content links, and site footers; remove that boilerplate from the
reviewed chunks before Stage 1. Then run Stage 1 and Stage 2 with:

```powershell
python main.py `
  --chunks prepared_data\chunks `
  --base-bank C:\approved\base_evidence_bank.json `
  --output dema_run `
  --country Togo
```
