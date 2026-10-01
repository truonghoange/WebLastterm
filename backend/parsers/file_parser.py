"""Parse uploads, paths or bytes into CVDocument. No UI dependencies or OCR."""
import logging
from io import BytesIO
from pathlib import Path

from backend.exceptions import DocumentParseError
from backend.models import CVDocument

logger = logging.getLogger(__name__)


class FileParser:
    def parse(self, source, filename: str | None = None) -> CVDocument:
        try:
            if isinstance(source, (str, Path)):
                path = Path(source)
                filename = filename or path.name
                data = path.read_bytes()
            elif isinstance(source, bytes):
                data = source
            elif hasattr(source, "getvalue"):
                filename = filename or getattr(source, "name", None)
                data = source.getvalue()
            elif hasattr(source, "read"):
                filename = filename or getattr(source, "name", None)
                data = source.read()
            else:
                raise DocumentParseError("UNSUPPORTED_FILE", "Supply a PDF, DOCX or TXT file.")
        except DocumentParseError:
            raise
        except Exception:
            raise DocumentParseError("FILE_READ_FAILED", "The file could not be read.") from None

        suffix = Path(filename or "").suffix.lower()
        if suffix not in {".pdf", ".docx", ".txt"}:
            raise DocumentParseError("UNSUPPORTED_FILE", "Only PDF, DOCX and TXT are supported.")
        if not data:
            raise DocumentParseError("EMPTY_DOCUMENT", "The document is empty.")
        page_count = None
        try:
            if suffix == ".txt":
                try:
                    text = data.decode("utf-8-sig")
                except UnicodeDecodeError:
                    text = data.decode("latin-1")
            elif suffix == ".pdf":
                # Reject non-PDF bytes before pypdf can log their raw header.
                if not data.startswith(b"%PDF-"):
                    raise ValueError("Invalid PDF header")
                from pypdf import PdfReader
                reader = PdfReader(BytesIO(data))
                page_count = len(reader.pages) or None
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
            else:
                from docx import Document
                doc = Document(BytesIO(data))
                # iter_inner_content preserves paragraphs and tables in reading order.
                chunks = []
                for block in doc.iter_inner_content():
                    if hasattr(block, "text"):
                        chunks.append(block.text)
                    else:
                        chunks.extend(" | ".join(cell.text for cell in row.cells) for row in block.rows)
                text = "\n".join(chunks)
        except Exception:
            code = {".pdf": "PDF_TEXT_EXTRACTION_FAILED", ".docx": "DOCX_TEXT_EXTRACTION_FAILED",
                    ".txt": "TEXT_EXTRACTION_FAILED"}[suffix]
            raise DocumentParseError(code, "Text extraction failed. Try another file or paste the CV text.") from None
        if not text.strip():
            raise DocumentParseError("EMPTY_DOCUMENT", "No text was extracted. A scanned PDF may require OCR; try DOCX/TXT or paste text.")
        printable = sum(char.isprintable() or char.isspace() for char in text) / len(text)
        low = (suffix == ".pdf" and len(text.strip()) < 100 * (page_count or 1)) or printable < .95 or "\ufffd" in text
        document = CVDocument(raw_text=text.strip(), source_type=suffix[1:], filename=filename,
                              page_count=page_count, extraction_quality="low" if low else "good")
        logger.info("Document parsed (type=%s, quality=%s)", document.source_type, document.extraction_quality)
        return document
