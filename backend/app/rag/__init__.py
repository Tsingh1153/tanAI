"""Retrieval-Augmented Generation subsystem.

Pipeline: parse documents into text -> split into overlapping chunks -> embed
each chunk -> store vectors -> at query time retrieve the most relevant chunks
(hybrid semantic + keyword) and ground the model's answer in them with citations.
"""

from .embeddings import EmbeddingProvider, OllamaEmbeddingProvider
from .ingest_service import IngestionService
from .rag_service import RagService

__all__ = [
    "EmbeddingProvider",
    "OllamaEmbeddingProvider",
    "IngestionService",
    "RagService",
]
