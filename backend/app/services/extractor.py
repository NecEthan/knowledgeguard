"""Text extraction from supported document types."""

import io
import logging

import pymupdf as fitz  # noqa: F401 — imported so tests can patch app.services.extractor.fitz
from docx import Document as DocxDocument

logger = logging.getLogger(__name__)

# Average characters per page below which a PDF is treated as scanned.
_MIN_CHARS_PER_PAGE = 50


def extract_text(content: bytes, content_type: str) -> str:
    """Extract plain text from document bytes.

    Supported content_types:
        application/pdf
        application/vnd.openxmlformats-officedocument.wordprocessingml.document
        text/plain
        text/markdown
    """
    if content_type == "application/pdf":
        return _extract_pdf(content)
    if content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return _extract_docx(content)
    if content_type in ("text/plain", "text/markdown"):
        return content.decode("utf-8", errors="replace").strip()
    raise ValueError(f"Unsupported content type for extraction: {content_type}")


def _extract_pdf(content: bytes) -> str:
    with fitz.open(stream=content, filetype="pdf") as doc:
        page_texts = [page.get_text("text") for page in doc]
        full_text = "\n".join(page_texts).strip()

        # If average chars/page is too low, the PDF is probably scanned.
        if len(doc) > 0 and len(full_text) / len(doc) < _MIN_CHARS_PER_PAGE:
            logger.info(
                "PDF has sparse text (%.1f chars/page); attempting OCR",
                len(full_text) / len(doc),
            )
            full_text = _ocr_pdf(doc)

    return full_text


def _ocr_pdf(doc) -> str:
    """OCR fallback for scanned PDFs. Returns empty string if unavailable."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        logger.warning("pytesseract/Pillow not installed; OCR unavailable")
        return ""

    texts = []
    try:
        for page in doc:
            pix = page.get_pixmap(dpi=300)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            texts.append(pytesseract.image_to_string(img))
    except Exception:
        logger.exception("OCR failed")
        return ""

    return "\n".join(texts).strip()


def _extract_docx(content: bytes) -> str:
    doc = DocxDocument(io.BytesIO(content))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)
