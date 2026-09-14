"""Text chunking.

Retrieval quality hinges on chunk size: too large and a chunk mixes unrelated
ideas (diluting the embedding); too small and it loses context. We target
~1000-character chunks with a 150-character overlap so ideas that straddle a
boundary still appear whole in at least one chunk. Chunking is paragraph-aware —
it packs whole paragraphs together and only hard-splits paragraphs that exceed
the size on their own.
"""

from __future__ import annotations

from dataclasses import dataclass

from .parsers import TextSegment

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_OVERLAP = 150


@dataclass(slots=True)
class TextChunk:
    content: str
    locator: str | None
    ordinal: int


def _split_paragraph(paragraph: str, size: int) -> list[str]:
    """Hard-split an oversized paragraph on word boundaries."""

    words = paragraph.split()
    pieces: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > size:
            pieces.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        pieces.append(current)
    return pieces


def chunk_segments(
    segments: list[TextSegment],
    size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[TextChunk]:
    """Turn parsed segments into ordered, overlapping chunks."""

    chunks: list[TextChunk] = []
    ordinal = 0

    for segment in segments:
        # Break the segment into paragraph units, splitting any that are huge.
        units: list[str] = []
        for para in segment.text.split("\n\n"):
            para = para.strip()
            if not para:
                continue
            if len(para) > size:
                units.extend(_split_paragraph(para, size))
            else:
                units.append(para)

        current = ""
        for unit in units:
            if current and len(current) + 2 + len(unit) > size:
                chunks.append(
                    TextChunk(current.strip(), segment.locator, ordinal)
                )
                ordinal += 1
                # Seed the next chunk with the overlap tail for continuity.
                tail = current[-overlap:] if overlap else ""
                current = f"{tail}\n\n{unit}" if tail else unit
            else:
                current = f"{current}\n\n{unit}" if current else unit

        if current.strip():
            chunks.append(TextChunk(current.strip(), segment.locator, ordinal))
            ordinal += 1

    return chunks
