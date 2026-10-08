"""Stage 0: convert local PDF/HTML/DOCX/Markdown and create reviewable chunks."""

from __future__ import annotations

import hashlib
import json
import re
from importlib.metadata import version
from pathlib import Path
from typing import Any

from .storage import atomic_write_json, atomic_write_text, sha256_text, utc_now


SUPPORTED_SUFFIXES = {".pdf", ".html", ".htm", ".docx", ".md", ".markdown"}
CHUNK_SIZE_PAGES = 10


def source_id_for(path: Path) -> str:
    """Return a readable source identifier that is safe as one path component."""
    source_id = re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem).strip("._-")
    if not source_id:
        raise ValueError(f"Cannot derive a source ID from {path.name!r}")
    return source_id


def source_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frontmatter(
    *,
    source_id: str,
    source_file: str,
    input_sha256: str,
    page_start: int,
    page_end: int,
    conversion_tool: str = "docling",
) -> str:
    values: dict[str, Any] = {
        "source_id": source_id,
        "source_file": source_file,
        "source_url": "",
        "page_start": page_start,
        "page_end": page_end,
        "conversion_tool": conversion_tool,
        "ocr_enabled": False,
        "input_sha256": input_sha256,
    }
    lines = ["---"]
    lines.extend(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in values.items())
    lines.extend(["---", ""])
    return "\n".join(lines)


def markdown_chunks(document: Any, suffix: str) -> list[tuple[int, int, str]]:
    """Export PDF pages in groups of ten; treat other formats as one unit."""
    if suffix.lower() != ".pdf":
        markdown = document.export_to_markdown().strip()
        return [(1, 1, markdown)]

    page_count = len(document.pages)
    if page_count < 1:
        raise ValueError("PDF conversion produced no pages")
    chunks: list[tuple[int, int, str]] = []
    for page_start in range(1, page_count + 1, CHUNK_SIZE_PAGES):
        page_end = min(page_start + CHUNK_SIZE_PAGES - 1, page_count)
        pages = [
            document.export_to_markdown(page_no=page_number).strip()
            for page_number in range(page_start, page_end + 1)
        ]
        markdown = "\n\n<!-- page break -->\n\n".join(pages).strip()
        chunks.append((page_start, page_end, markdown))
    return chunks


def build_converter() -> Any:
    """Build the deliberately small Docling configuration with OCR disabled."""
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pdf_options = PdfPipelineOptions()
    pdf_options.do_ocr = False
    pdf_options.generate_page_images = False
    pdf_options.generate_picture_images = False
    pdf_options.do_code_enrichment = False
    pdf_options.do_formula_enrichment = False
    return DocumentConverter(
        allowed_formats=[InputFormat.PDF, InputFormat.HTML, InputFormat.DOCX],
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pdf_options,
                backend=PyPdfiumDocumentBackend,
            )
        },
    )


def prepare_sources(input_path: Path, output_path: Path) -> Path:
    """Convert a fresh input directory and return its manifest path."""
    input_root = input_path.resolve()
    output_root = output_path.resolve()
    if not input_root.is_dir():
        raise ValueError(f"Stage 0 input directory does not exist: {input_path}")
    sources = sorted(
        path
        for path in input_root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )
    if not sources:
        raise ValueError(f"No PDF, HTML, DOCX, or Markdown files found in {input_path}")
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError(
            f"Stage 0 output must be new or empty to prevent stale chunks: {output_path}"
        )

    source_ids = [source_id_for(path) for path in sources]
    duplicates = sorted({value for value in source_ids if source_ids.count(value) > 1})
    if duplicates:
        raise ValueError(f"Duplicate source IDs after filename normalization: {duplicates}")

    # Initialize Docling before creating output so a missing optional install
    # does not leave behind a directory that blocks the next clean attempt.
    converter = build_converter() if any(path.suffix.lower() not in {".md", ".markdown"} for path in sources) else None
    output_root.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        output_root / ".gitignore",
        "# Converted source material stays outside version control.\n*\n!.gitignore\n",
    )
    records: list[dict[str, Any]] = []
    failures: list[str] = []

    for source, source_id in zip(sources, source_ids, strict=True):
        relative_source = source.relative_to(input_root).as_posix()
        digest = source_sha256(source)
        try:
            conversion_tool = "markdown_passthrough" if source.suffix.lower() in {".md", ".markdown"} else "docling"
            if source.suffix.lower() in {".md", ".markdown"}:
                full_markdown = source.read_text(encoding="utf-8-sig").strip()
                chunks = [(1, 1, full_markdown)]
                status = "source_markdown"
            else:
                assert converter is not None
                result = converter.convert(source)
                status = getattr(result.status, "value", str(result.status)).lower()
                if status not in {"success", "partial_success"}:
                    raise RuntimeError(f"Docling conversion status is {status}")
                chunks = markdown_chunks(result.document, source.suffix)
                full_markdown = result.document.export_to_markdown().strip()
            if not any(markdown.strip() for _, _, markdown in chunks):
                raise ValueError(
                    "conversion produced no text; the document may be scanned, "
                    "and OCR is intentionally disabled"
                )

            converted_text = frontmatter(
                source_id=source_id,
                source_file=source.name,
                input_sha256=digest,
                page_start=1,
                page_end=max(end for _, end, _ in chunks),
                conversion_tool=conversion_tool,
            ) + full_markdown + "\n"
            converted_path = output_root / "converted" / f"{source_id}.md"
            atomic_write_text(converted_path, converted_text)

            chunk_records: list[dict[str, Any]] = []
            for index, (page_start, page_end, markdown) in enumerate(chunks, start=1):
                chunk_name = (
                    f"{source_id}_chunk_{index:03d}_pages_"
                    f"{page_start:03d}-{page_end:03d}.md"
                )
                chunk_path = output_root / "chunks" / source_id / chunk_name
                chunk_text = frontmatter(
                    source_id=source_id,
                    source_file=source.name,
                    input_sha256=digest,
                    page_start=page_start,
                    page_end=page_end,
                    conversion_tool=conversion_tool,
                ) + markdown + "\n"
                atomic_write_text(chunk_path, chunk_text)
                chunk_records.append(
                    {
                        "path": chunk_path.relative_to(output_root).as_posix(),
                        "page_start": page_start,
                        "page_end": page_end,
                        "sha256": sha256_text(chunk_text),
                    }
                )

            records.append(
                {
                    "source_id": source_id,
                    "input_file": relative_source,
                    "input_sha256": digest,
                    "format": source.suffix.lower().lstrip("."),
                    "docling_status": status,
                    "converted_path": converted_path.relative_to(output_root).as_posix(),
                    "converted_sha256": sha256_text(converted_text),
                    "chunks": chunk_records,
                }
            )
            print(
                f"STAGE 0 OK | {relative_source} | chunks={len(chunk_records)}",
                flush=True,
            )
        except Exception as exc:
            failures.append(f"{relative_source}: {type(exc).__name__}: {exc}")
            print(f"STAGE 0 ERROR | {failures[-1]}", flush=True)

    manifest_path = output_root / "manifest.json"
    atomic_write_json(
        manifest_path,
        {
            "stage": 0,
            "created_at_utc": utc_now(),
            "tool": "docling",
            "docling_version": version("docling") if converter is not None else None,
            "ocr_enabled": False,
            "chunk_size_pages": CHUNK_SIZE_PAGES,
            "source_count": len(sources),
            "success_count": len(records),
            "failure_count": len(failures),
            "sources": records,
            "failures": failures,
        },
    )
    if failures:
        raise RuntimeError(
            f"Stage 0 completed with {len(failures)} failure(s); see {manifest_path}"
        )
    return manifest_path
