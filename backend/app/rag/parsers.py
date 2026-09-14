"""Document text extraction.

Each supported format is reduced to a list of ``TextSegment``s — a piece of text
plus an optional locator (page number, slide, sheet) used later for citations.
Parsing is dispatched by file extension; unknown text-like files fall back to a
plain UTF-8 read so code and config files "just work".
"""

from __future__ import annotations

import csv
import io
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
    ".txt", ".md", ".markdown", ".rst", ".log",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".h", ".cpp", ".hpp",
    ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala", ".sh",
    ".sql", ".r", ".m", ".lua", ".pl",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env", ".xml",
}


def supported_extension(filename: str) -> bool:
    ext = Path(filename).suffix.lower()
    return ext in _TEXT_EXTENSIONS or ext in {
        ".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".html", ".htm",
    }


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
            return _parse_csv(path)
        if ext in {".html", ".htm"}:
            return _parse_html(path)
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


def _parse_pdf(path: str) -> list[TextSegment]:
    from pypdf import PdfReader

    reader = PdfReader(path)
    segments: list[TextSegment] = []
    for i, page in enumerate(reader.pages, start=1):
        text = _clean(page.extract_text() or "")
        if text:
            segments.append(TextSegment(text=text, locator=f"p. {i}"))
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


def _parse_csv(path: str) -> list[TextSegment]:
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
        sample = fh.read()
    reader = csv.reader(io.StringIO(sample))
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
