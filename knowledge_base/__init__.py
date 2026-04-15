"""
Knowledge Base System — Vector DB for enterprise documents.

Supports:
  - Agreement/Contract storage and search
  - Communication/Email archive with tagging
  - Financial data and reports
  - Vendor documentation and case studies
  - Custom domain-specific collections

Features:
  - ChromaDB for vector operations
  - Multi-tenancy (session-based collections)
  - Metadata tagging and filtering
  - Full-text + semantic search
  - Automatic chunking and embedding
"""

from knowledge_base.vector_store import (
    get_vector_store,
    VectorStore,
    Collection,
)

__all__ = [
    "get_vector_store",
    "VectorStore",
    "Collection",
]
