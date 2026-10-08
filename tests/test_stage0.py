import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dema.stage0 import CHUNK_SIZE_PAGES, frontmatter, markdown_chunks, prepare_sources, source_id_for


class FakeDocument:
    def __init__(self, page_count):
        self.pages = {page: object() for page in range(1, page_count + 1)}

    def export_to_markdown(self, page_no=None):
        if page_no is None:
            return "Whole HTML document"
        return f"Page {page_no}"


class Stage0Tests(unittest.TestCase):
    def test_pdf_is_grouped_into_ten_page_chunks(self):
        chunks = markdown_chunks(FakeDocument(25), ".pdf")

        self.assertEqual(CHUNK_SIZE_PAGES, 10)
        self.assertEqual([(start, end) for start, end, _ in chunks], [(1, 10), (11, 20), (21, 25)])
        self.assertIn("Page 1", chunks[0][2])
        self.assertIn("Page 10", chunks[0][2])
        self.assertNotIn("Page 11", chunks[0][2])

    def test_html_is_one_logical_chunk(self):
        self.assertEqual(
            markdown_chunks(FakeDocument(0), ".html"),
            [(1, 1, "Whole HTML document")],
        )

    def test_frontmatter_records_ocr_boundary_and_original_file(self):
        header = frontmatter(
            source_id="source-1",
            source_file="report.pdf",
            input_sha256="abc",
            page_start=1,
            page_end=10,
        )

        self.assertIn('source_file: "report.pdf"', header)
        self.assertIn("ocr_enabled: false", header)
        self.assertIn("page_end: 10", header)

    def test_source_identifier_is_safe_and_readable(self):
        self.assertEqual(source_id_for(Path("My report (final).pdf")), "My_report_final")

    def test_markdown_passthrough_needs_no_docling_converter(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "reviewed.md").write_text("# Reviewed\n\nExact text.", encoding="utf-8")
            with patch("dema.stage0.build_converter", side_effect=AssertionError("not needed")):
                manifest = prepare_sources(source, root / "prepared")
            chunk = next((root / "prepared/chunks").rglob("*.md")).read_text(encoding="utf-8")
            self.assertIn('conversion_tool: "markdown_passthrough"', chunk)
            self.assertIn("Exact text.", chunk)
            self.assertTrue(manifest.exists())


if __name__ == "__main__":
    unittest.main()
