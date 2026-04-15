"""
Vector Store — ChromaDB-backed semantic search for knowledge base.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ChromaDB is optional for now, but recommended for production
try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logger.warning("ChromaDB not installed. Install with: pip install chromadb")


@dataclass
class Collection:
    """Represents a collection of documents in the vector store."""
    name: str
    description: str = ""
    metadata: Dict[str, Any] = None


class VectorStore:
    """
    Production-grade vector database for PilotH knowledge base.
    
    Collections:
    - agreements: Contracts, NDAs, SLAs
    - communications: Emails, Slack messages, meeting notes
    - vendor_data: Vendor profiles, case studies, performance data
    - financial: Budgets, invoices, financial reports
    - custom: User-defined domain-specific data
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize vector store. Falls back to in-memory if ChromaDB unavailable."""
        self.db_path = db_path or "chroma_db"
        self.collections: Dict[str, Any] = {}
        self._init_chroma()
        self._init_collections()
    
    def _init_chroma(self) -> None:
        """Initialize ChromaDB client."""
        if not CHROMA_AVAILABLE:
            logger.warning("[KB] ChromaDB not available. Using in-memory fallback.")
            self.client = None
            self._in_memory_docs: Dict[str, List[Dict]] = {}
            return
        
        try:
            os.makedirs(self.db_path, exist_ok=True)
            settings = Settings(
                is_persistent=True,
                persist_directory=self.db_path,
                anonymized_telemetry=False,
            )
            self.client = chromadb.Client(settings)
            logger.info(f"[KB] ChromaDB initialized at: {self.db_path}")
        except Exception as e:
            logger.error(f"[KB] ChromaDB init failed: {e}. Using in-memory fallback.")
            self.client = None
            self._in_memory_docs = {}
    
    def _init_collections(self) -> None:
        """Create default collections."""
        default_collections = [
            Collection(
                name="agreements",
                description="Contracts, NDAs, SLAs, and legal agreements"
            ),
            Collection(
                name="communications",
                description="Emails, Slack messages, meeting notes, transcripts"
            ),
            Collection(
                name="vendor_data",
                description="Vendor profiles, case studies, performance metrics"
            ),
            Collection(
                name="financial",
                description="Financial reports, budgets, invoices, forecasts"
            ),
            Collection(
                name="internal_policies",
                description="Company policies, procedures, guidelines"
            ),
        ]
        
        for coll in default_collections:
            self.create_collection_if_missing(coll)
    
    def create_collection_if_missing(self, collection: Collection) -> None:
        """Create a new collection if it doesn't exist."""
        if collection.name in self.collections:
            return
        
        if self.client is None:
            self.collections[collection.name] = {
                "name": collection.name,
                "description": collection.description,
                "documents": []
            }
            logger.info(f"[KB] Created in-memory collection: {collection.name}")
        else:
            try:
                self.client.get_or_create_collection(
                    name=collection.name,
                    metadata={"description": collection.description}
                )
                logger.info(f"[KB] Created collection: {collection.name}")
            except Exception as e:
                logger.error(f"[KB] Failed to create collection {collection.name}: {e}")
    
    def add_document(
        self,
        collection_name: str,
        doc_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None,
    ) -> None:
        """Add a document to a collection."""
        if self.client is None:
            # In-memory fallback
            if collection_name not in self.collections:
                self.collections[collection_name] = {"documents": []}
            self.collections[collection_name]["documents"].append({
                "id": doc_id,
                "content": content,
                "metadata": metadata or {}
            })
            logger.debug(f"[KB] Added doc {doc_id} to {collection_name} (in-memory)")
            return
        
        try:
            collection = self.client.get_collection(name=collection_name)
            collection.add(
                ids=[doc_id],
                documents=[content],
                metadatas=[metadata or {}],
                embeddings=[embedding] if embedding else None,
            )
            logger.debug(f"[KB] Added doc {doc_id} to {collection_name}")
        except Exception as e:
            logger.error(f"[KB] Failed to add document: {e}")
    
    def search(
        self,
        collection_name: str,
        query: str,
        limit: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search documents in a collection by semantic similarity.
        
        Args:
            collection_name: Name of the collection
            query: Search query (text)
            limit: Max results to return
            where: Metadata filter (e.g., {"type": "contract"})
        
        Returns:
            List of documents with similarity scores
        """
        if self.client is None:
            # Simple in-memory text search
            results = []
            if collection_name in self.collections:
                docs = self.collections[collection_name].get("documents", [])
                query_lower = query.lower()
                for doc in docs:
                    if query_lower in doc["content"].lower():
                        results.append({
                            "id": doc["id"],
                            "content": doc["content"][:500],  # Preview
                            "distance": 0.0,
                            "metadata": doc.get("metadata", {})
                        })
            return results[:limit]
        
        try:
            collection = self.client.get_collection(name=collection_name)
            results = collection.query(
                query_texts=[query],
                n_results=limit,
                where=where,
            )
            
            # Format as list of dicts
            documents = []
            if results and results["ids"] and len(results["ids"]) > 0:
                for i, doc_id in enumerate(results["ids"][0]):
                    documents.append({
                        "id": doc_id,
                        "content": results["documents"][0][i],
                        "distance": results["distances"][0][i],
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    })
            return documents
        except Exception as e:
            logger.error(f"[KB] Search failed: {e}")
            return []
    
    def delete_document(self, collection_name: str, doc_id: str) -> bool:
        """Delete a document from a collection."""
        if self.client is None:
            if collection_name in self.collections:
                self.collections[collection_name]["documents"] = [
                    d for d in self.collections[collection_name]["documents"]
                    if d["id"] != doc_id
                ]
            return True
        
        try:
            collection = self.client.get_collection(name=collection_name)
            collection.delete(ids=[doc_id])
            logger.debug(f"[KB] Deleted doc {doc_id} from {collection_name}")
            return True
        except Exception as e:
            logger.error(f"[KB] Failed to delete document: {e}")
            return False
    
    def list_collections(self) -> List[Dict[str, Any]]:
        """List all collections."""
        if self.client is None:
            return [
                {"name": name, "doc_count": len(data.get("documents", []))}
                for name, data in self.collections.items()
            ]
        
        try:
            colls = self.client.list_collections()
            return [
                {"name": c.name, "metadata": c.metadata}
                for c in colls
            ]
        except Exception as e:
            logger.error(f"[KB] Failed to list collections: {e}")
            return []
    
    def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """Get statistics for a collection."""
        if self.client is None:
            doc_count = len(self.collections.get(collection_name, {}).get("documents", []))
            return {"collection": collection_name, "document_count": doc_count}
        
        try:
            collection = self.client.get_collection(name=collection_name)
            count = collection.count()
            return {
                "collection": collection_name,
                "document_count": count,
                "metadata": collection.metadata
            }
        except Exception as e:
            logger.error(f"[KB] Failed to get stats: {e}")
            return {}


# ── Singleton ─────────────────────────────────────────────────────────────────

_vector_store: Optional[VectorStore] = None


def get_vector_store(db_path: Optional[str] = None) -> VectorStore:
    """Return the process-global VectorStore singleton."""
    global _vector_store
    if _vector_store is None:
        db_path = db_path or os.environ.get("CHROMA_DB_PATH", "chroma_db")
        _vector_store = VectorStore(db_path=db_path)
    return _vector_store
