"""Document text extraction: each format -> TextSegments (text + citation locator).

OCR (scanned PDFs and images) and a few formats rely on optional dependencies; if
they're missing, parsing raises a clear ParseError telling the user what to install
rather than failing silently.
"""

from __future__ import annotations

import csv
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path


class ParseError(RuntimeError):
    """Raised when a document cannot be parsed."""


@dataclass(slots=True)
class TextSegment:
    text: str
    locator: str | None = None


# Extensions treated as plain text (read directly). Covers code + config + prose.
_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".rst",
    ".log",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cs",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".scala",
    ".sh",
    ".sql",
    ".r",
    ".m",
    ".lua",
    ".pl",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".env",
    ".xml",
}

# Parsed by a dedicated handler below.
_DOC_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".csv",
    ".tsv",
    ".html",
    ".htm",
    ".rtf",
    ".odt",
    ".epub",
}

# Image formats read via OCR.
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp", ".gif"}


def supported_extension(filename: str) -> bool:
    ext = Path(filename).suffix.lower()
    return ext in _TEXT_EXTENSIONS or ext in _DOC_EXTENSIONS or ext in _IMAGE_EXTENSIONS


def extract_segments(path: str, filename: str) -> list[TextSegment]:
    """Extract text segments from a file on disk."""

    ext = Path(filename).suffix.lower()
    try:
        if ext == ".pdf":
            return _parse_pdf(path)
        if ext == ".docx":
            return _parse_docx(path)
        if ext == ".pptx":
            return _parse_pptx(path)
        if ext == ".xlsx":
            return _parse_xlsx(path)
        if ext == ".csv":
            return _parse_delimited(path, ",")
        if ext == ".tsv":
            return _parse_delimited(path, "\t")
        if ext in {".html", ".htm"}:
            return _parse_html(path)
        if ext == ".rtf":
            return _parse_rtf(path)
        if ext == ".odt":
            return _parse_odt(path)
        if ext == ".epub":
            return _parse_epub(path)
        if ext in _IMAGE_EXTENSIONS:
            return _parse_image(path)
        if ext in _TEXT_EXTENSIONS:
            return _parse_text(path)
    except ParseError:
        raise
    except Exception as exc:  # normalize any library-specific failure
        raise ParseError(f"Failed to parse {filename}: {exc}") from exc

    raise ParseError(f"Unsupported file type: {ext or filename}")


def _clean(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def _parse_text(path: str) -> list[TextSegment]:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return [TextSegment(text=_clean(fh.read()))]


# --- OCR (optional: needs the `tesseract` binary + pytesseract/pillow) -------- #
def _ocr_available() -> bool:
    if shutil.which("tesseract") is None:
        return False
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return True


def _ocr_image(path: str) -> str:
    import pytesseract
    from PIL import Image

    with Image.open(path) as img:
        return _clean(pytesseract.image_to_string(img))


def _parse_image(path: str) -> list[TextSegment]:
    if not _ocr_available():
        raise ParseError(
            "Reading text from images needs OCR. Install it with: "
            "brew install tesseract && pip install -r requirements-ocr.txt"
        )
    text = _ocr_image(path)
    return [TextSegment(text=text)] if text else []


def _ocr_pdf_pages(path: str, pages: list[int]) -> list[tuple[int, str]]:
    """OCR specific PDF pages (needs pdf2image + the poppler binary)."""

    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        return []
    out: list[tuple[int, str]] = []
    for i in pages:
        try:
            images = convert_from_path(path, first_page=i, last_page=i, dpi=200)
        except Exception:
            break  # poppler missing or render failure — stop trying
        for img in images:
            out.append((i, _clean(pytesseract.image_to_string(img))))
    return out


def _parse_pdf(path: str) -> list[TextSegment]:
    from pypdf import PdfReader

    reader = PdfReader(path)
    segments: list[TextSegment] = []
    scanned: list[int] = []
    for i, page in enumerate(reader.pages, start=1):
        text = _clean(page.extract_text() or "")
        if text:
            segments.append(TextSegment(text=text, locator=f"p. {i}"))
        else:
            scanned.append(i)

    # Pages with no embedded text are likely scanned — OCR them if we can.
    if scanned and _ocr_available():
        for i, text in _ocr_pdf_pages(path, scanned):
            if text:
                segments.append(TextSegment(text=text, locator=f"p. {i} (OCR)"))
    return segments


def _parse_docx(path: str) -> list[TextSegment]:
    import docx

    document = docx.Document(path)
    parts = [p.text for p in document.paragraphs if p.text.strip()]
    # Include table cell text, which python-docx keeps outside `paragraphs`.
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    text = _clean("\n".join(parts))
    return [TextSegment(text=text)] if text else []


def _parse_pptx(path: str) -> list[TextSegment]:
    from pptx import Presentation

    prs = Presentation(path)
    segments: list[TextSegment] = []
    for i, slide in enumerate(prs.slides, start=1):
        lines: list[str] = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    line = "".join(run.text for run in para.runs).strip()
                    if line:
                        lines.append(line)
        text = _clean("\n".join(lines))
        if text:
            segments.append(TextSegment(text=text, locator=f"slide {i}"))
    return segments


def _parse_xlsx(path: str) -> list[TextSegment]:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    segments: list[TextSegment] = []
    for sheet in wb.worksheets:
        rows: list[str] = []
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None]
            if cells:
                rows.append(" | ".join(cells))
        text = _clean("\n".join(rows))
        if text:
            segments.append(TextSegment(text=text, locator=sheet.title))
    wb.close()
    return segments


def _parse_delimited(path: str, delimiter: str) -> list[TextSegment]:
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.reader(fh, delimiter=delimiter)
        rows = [" | ".join(cell for cell in row) for row in reader if any(row)]
    text = _clean("\n".join(rows))
    return [TextSegment(text=text)] if text else []


def _parse_html(path: str) -> list[TextSegment]:
    from bs4 import BeautifulSoup

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        soup = BeautifulSoup(fh.read(), "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = _clean(soup.get_text(separator="\n"))
    return [TextSegment(text=text)] if text else []


def _parse_rtf(path: str) -> list[TextSegment]:
    try:
        from striprtf.striprtf import rtf_to_text
    except ImportError as exc:
        raise ParseError(
            "Reading .rtf files needs an extra library: pip install striprtf"
        ) from exc
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = _clean(rtf_to_text(fh.read()))
    return [TextSegment(text=text)] if text else []


def _parse_odt(path: str) -> list[TextSegment]:
    from bs4 import BeautifulSoup

    with zipfile.ZipFile(path) as zf:
        content = zf.read("content.xml").decode("utf-8", errors="replace")
    soup = BeautifulSoup(content, "html.parser")
    text = _clean(soup.get_text(separator="\n"))
    return [TextSegment(text=text)] if text else []


def _parse_epub(path: str) -> list[TextSegment]:
    from bs4 import BeautifulSoup

    segments: list[TextSegment] = []
    with zipfile.ZipFile(path) as zf:
        names = [
            n for n in zf.namelist() if n.lower().endswith((".xhtml", ".html", ".htm"))
        ]
        for name in sorted(names):
            soup = BeautifulSoup(zf.read(name), "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()
            text = _clean(soup.get_text(separator="\n"))
            if text:
                segments.append(TextSegment(text=text, locator=Path(name).name))
    return segments
