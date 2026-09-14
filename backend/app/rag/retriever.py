"""Hybrid retrieval over chunk embeddings: semantic (cosine) blended with keyword."""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from ..models import Chunk


def pack_vector(vector: list[float]) -> tuple[bytes, int]:
    """Pack a float vector into compact float32 bytes; return (blob, dim)."""

    arr = np.asarray(vector, dtype=np.float32)
    return arr.tobytes(), int(arr.shape[0])


def unpack_vector(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


@dataclass(slots=True)
class ScoredChunk:
    chunk: Chunk
    score: float


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _minmax(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    lo, hi = float(values.min()), float(values.max())
    if hi - lo < 1e-9:
        return np.zeros_like(values)
    return (values - lo) / (hi - lo)


def retrieve(
    query_embedding: list[float],
    query_text: str,
    chunks: list[Chunk],
    top_k: int = 5,
    alpha: float = 0.65,
) -> list[ScoredChunk]:
    """Return the ``top_k`` most relevant chunks for a query."""

    if not chunks:
        return []

    # --- Semantic scores ---
    query = np.asarray(query_embedding, dtype=np.float32)
    query_norm = query / (np.linalg.norm(query) + 1e-9)

    matrix = np.vstack([unpack_vector(c.embedding) for c in chunks])
    norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
    matrix_norm = matrix / norms
    semantic = matrix_norm @ query_norm  # cosine similarity per chunk

    # --- Lexical scores ---
    q_terms = _tokens(query_text)
    if q_terms:
        lexical = np.array(
            [len(q_terms & _tokens(c.content)) / len(q_terms) for c in chunks],
            dtype=np.float32,
        )
    else:
        lexical = np.zeros(len(chunks), dtype=np.float32)

    # --- Blend ---
    combined = alpha * _minmax(semantic) + (1.0 - alpha) * _minmax(lexical)

    order = np.argsort(-combined)[:top_k]
    return [ScoredChunk(chunk=chunks[i], score=float(combined[i])) for i in order]
