"""Document parser tests for the newer formats + OCR guard. No Ollama needed."""

from __future__ import annotations

import zipfile

from app.rag.parsers import ParseError, extract_segments, supported_extension


def _write(tmp_path, name, content, mode="w"):
    p = tmp_path / name
    if mode == "w":
        p.write_text(content, encoding="utf-8")
    else:
        p.write_bytes(content)
    return str(p)


def test_supported_extensions() -> None:
    for name in ("a.tsv", "b.rtf", "c.odt", "d.epub", "e.png", "f.jpg", "g.pdf"):
        assert supported_extension(name), name


def test_tsv(tmp_path) -> None:
    path = _write(tmp_path, "data.tsv", "name\trole\nAda\tEngineer\n")
    segs = extract_segments(path, "data.tsv")
    text = " ".join(s.text for s in segs)
    assert "Ada" in text and "Engineer" in text


def test_rtf(tmp_path) -> None:
    path = _write(tmp_path, "note.rtf", r"{\rtf1\ansi Hello from RTF.}")
    segs = extract_segments(path, "note.rtf")
    assert "Hello from RTF" in " ".join(s.text for s in segs)


def test_odt(tmp_path) -> None:
    path = str(tmp_path / "doc.odt")
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "content.xml",
            "<office><text><p>ODT body text here.</p></text></office>",
        )
    segs = extract_segments(path, "doc.odt")
    assert "ODT body text here" in " ".join(s.text for s in segs)


def test_epub(tmp_path) -> None:
    path = str(tmp_path / "book.epub")
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "chapter1.xhtml",
            "<html><body><p>Chapter one content.</p></body></html>",
        )
    segs = extract_segments(path, "book.epub")
    joined = " ".join(s.text for s in segs)
    assert "Chapter one content" in joined
    assert segs[0].locator == "chapter1.xhtml"


def test_image_without_ocr_raises_clearly(tmp_path, monkeypatch) -> None:
    # Force the "OCR unavailable" path and check the message is actionable.
    monkeypatch.setattr("app.rag.parsers._ocr_available", lambda: False)
    path = str(tmp_path / "scan.png")
    (tmp_path / "scan.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    try:
        extract_segments(path, "scan.png")
        raise AssertionError("expected ParseError")
    except ParseError as exc:
        assert "OCR" in str(exc)
