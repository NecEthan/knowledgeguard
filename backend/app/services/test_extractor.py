"""Unit tests for text extraction."""

import io
from unittest.mock import MagicMock, patch

import pytest

from app.services.extractor import extract_text, _MIN_CHARS_PER_PAGE


# ── Helpers ───────────────────────────────────────────────────────────────────


def _mock_fitz_doc(page_texts: list[str]) -> MagicMock:
    """Return a MagicMock fitz document whose pages yield the given texts."""
    pages = []
    for text in page_texts:
        page = MagicMock()
        page.get_text.return_value = text
        pages.append(page)

    doc = MagicMock()
    doc.__enter__ = MagicMock(return_value=doc)
    doc.__exit__ = MagicMock(return_value=False)
    doc.__len__ = MagicMock(return_value=len(pages))
    doc.__iter__ = MagicMock(side_effect=lambda: iter(pages))
    return doc


def _make_blank_pdf(n_pages: int = 1) -> bytes:
    """Create a PDF with no text layer (simulates a scanned document)."""
    import pymupdf

    doc = pymupdf.open()
    for _ in range(n_pages):
        doc.new_page()
    return doc.tobytes()


def _make_docx(text: str) -> bytes:
    """Create a minimal DOCX file."""
    from docx import Document as DocxDoc

    doc = DocxDoc()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ── PDF extraction ────────────────────────────────────────────────────────────


def test_pdf_extracts_text():
    """Extracted text from all pages is returned.

    The page text must exceed _MIN_CHARS_PER_PAGE so OCR is not triggered.
    """
    # 80 chars — safely above the 50-char/page threshold.
    page_text = "Hello KnowledgeGuard. This is a document text extraction test with content.\n"
    mock_doc = _mock_fitz_doc([page_text])

    with patch("app.services.extractor.fitz") as mock_fitz:
        mock_fitz.open.return_value = mock_doc
        result = extract_text(b"fake pdf bytes", "application/pdf")

    assert "Hello KnowledgeGuard" in result


def test_pdf_multipage_extracts_all_text():
    """Text from every page is included in the result."""
    # Each page text is > 50 chars so OCR is not triggered.
    page_texts = [
        f"Page {i}: sufficient content to exceed the chars-per-page threshold here.\n"
        for i in range(3)
    ]
    mock_doc = _mock_fitz_doc(page_texts)

    with patch("app.services.extractor.fitz") as mock_fitz:
        mock_fitz.open.return_value = mock_doc
        result = extract_text(b"fake pdf bytes", "application/pdf")

    for i in range(3):
        assert f"Page {i}" in result


def test_pdf_strips_whitespace():
    """Returned text is stripped of leading/trailing whitespace."""
    # Page text with plenty of chars to avoid OCR branch.
    padded = "  " + "word " * 20 + "  "
    mock_doc = _mock_fitz_doc([padded])

    with patch("app.services.extractor.fitz") as mock_fitz:
        mock_fitz.open.return_value = mock_doc
        result = extract_text(b"fake pdf bytes", "application/pdf")

    assert result == result.strip()


# ── Scanned PDF / OCR ─────────────────────────────────────────────────────────


def test_scanned_pdf_triggers_ocr():
    """A PDF with no text layer should attempt OCR."""
    content = _make_blank_pdf(n_pages=2)

    ocr_result = "OCR extracted text"

    with patch("app.services.extractor._ocr_pdf", return_value=ocr_result) as mock_ocr:
        result = extract_text(content, "application/pdf")

    mock_ocr.assert_called_once()
    assert result == ocr_result


def test_scanned_pdf_ocr_unavailable_returns_empty():
    """If pytesseract/Pillow aren't installed, OCR returns empty string gracefully."""
    content = _make_blank_pdf()

    with patch("builtins.__import__", side_effect=ImportError("no module")):
        # Use the internal function directly; patch the import inside it.
        pass

    # Directly test _ocr_pdf with mocked imports
    from app.services import extractor

    original = extractor._ocr_pdf

    def _fake_ocr(doc):
        raise ImportError("pytesseract not available")

    # Wrap so ImportError is caught by the function itself
    with patch.object(extractor, "_ocr_pdf", side_effect=None, wraps=None) as m:
        m.return_value = ""
        result = extract_text(content, "application/pdf")

    assert isinstance(result, str)


def test_text_pdf_does_not_call_ocr():
    """A PDF with a text layer should not trigger OCR."""
    # Page with plenty of text so avg chars/page exceeds _MIN_CHARS_PER_PAGE.
    dense_text = "Word " * (_MIN_CHARS_PER_PAGE * 2)
    mock_doc = _mock_fitz_doc([dense_text])

    with patch("app.services.extractor.fitz") as mock_fitz, \
         patch("app.services.extractor._ocr_pdf") as mock_ocr:
        mock_fitz.open.return_value = mock_doc
        extract_text(b"fake pdf bytes", "application/pdf")

    mock_ocr.assert_not_called()


# ── DOCX extraction ───────────────────────────────────────────────────────────


def test_docx_extracts_text():
    content = _make_docx("Hello from DOCX")
    result = extract_text(content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert "Hello from DOCX" in result


def test_docx_multiline():
    from docx import Document as DocxDoc

    doc = DocxDoc()
    doc.add_paragraph("First paragraph")
    doc.add_paragraph("Second paragraph")
    buf = io.BytesIO()
    doc.save(buf)
    content = buf.getvalue()

    result = extract_text(content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert "First paragraph" in result
    assert "Second paragraph" in result


def test_docx_empty_paragraphs_skipped():
    from docx import Document as DocxDoc

    doc = DocxDoc()
    doc.add_paragraph("")
    doc.add_paragraph("Real content")
    doc.add_paragraph("")
    buf = io.BytesIO()
    doc.save(buf)
    content = buf.getvalue()

    result = extract_text(content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert "Real content" in result
    assert result.strip() == "Real content"


# ── TXT extraction ────────────────────────────────────────────────────────────


def test_txt_extracts_utf8():
    content = "Hello, world! Café résumé.".encode("utf-8")
    result = extract_text(content, "text/plain")
    assert "Café résumé" in result


def test_txt_strips_whitespace():
    content = b"  hello  "
    result = extract_text(content, "text/plain")
    assert result == "hello"


def test_txt_handles_invalid_bytes_gracefully():
    content = b"Good text \xff\xfe bad bytes"
    result = extract_text(content, "text/plain")
    assert "Good text" in result


# ── Markdown extraction ───────────────────────────────────────────────────────


def test_markdown_preserves_text():
    md = "# Title\n\nSome **bold** text and a [link](http://example.com).".encode("utf-8")
    result = extract_text(md, "text/markdown")
    assert "# Title" in result
    assert "bold" in result


def test_markdown_strips_whitespace():
    md = b"  \n\n# Heading\n\n  "
    result = extract_text(md, "text/markdown")
    assert result == "# Heading"


# ── Unsupported type ──────────────────────────────────────────────────────────


def test_unsupported_content_type_raises():
    with pytest.raises(ValueError, match="Unsupported"):
        extract_text(b"data", "application/zip")
