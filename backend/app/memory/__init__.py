"""Memory & context-management subsystem.

Two cooperating pieces:

* ``Summarizer`` — compresses the oldest turns of a long conversation into a
  rolling summary so the live prompt stays within the model's context window.
* ``MemoryService`` — stores durable facts/preferences across conversations,
  retrieves them semantically, injects them into the prompt, and extracts new
  ones automatically after each exchange.

Both reuse the embedding + vector infrastructure introduced for RAG.
"""

from .memory_service import MemoryService
from .summarizer import Summarizer

__all__ = ["MemoryService", "Summarizer"]
