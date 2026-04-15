"""
Knowledge Base API Routes — Access and manage the vector database.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


class AddDocumentRequest(BaseModel):
    """Request to add a document to the knowledge base."""
    collection: str
    doc_id: str
    content: str
    metadata: Optional[Dict[str, Any]] = None


class SearchRequest(BaseModel):
    """Request to search the knowledge base."""
    query: str
    collection: str = "all"
    limit: int = 5


@router.get("", summary="Health check")
def kb_health():
    """Check knowledge base status."""
    from knowledge_base.vector_store import get_vector_store
    
    vs = get_vector_store()
    collections = vs.list_collections()
    
    return {
        "status": "ok",
        "collections": collections,
        "total_collections": len(collections),
    }


@router.get("/collections", summary="List collections")
def list_collections():
    """List all available collections."""
    from knowledge_base.vector_store import get_vector_store
    
    vs = get_vector_store()
    collections = vs.list_collections()
    
    return {
        "collections": collections,
        "total": len(collections),
    }


@router.get("/collections/{collection_name}/stats", summary="Get collection stats")
def get_collection_stats(collection_name: str):
    """Get statistics for a collection."""
    from knowledge_base.vector_store import get_vector_store
    
    vs = get_vector_store()
    stats = vs.get_collection_stats(collection_name)
    
    if not stats:
        raise HTTPException(status_code=404, detail=f"Collection '{collection_name}' not found.")
    
    return stats


@router.post("/search", summary="Search knowledge base")
def search_kb(request: SearchRequest):
    """Search the knowledge base using semantic search."""
    from knowledge_base.vector_store import get_vector_store
    
    vs = get_vector_store()
    
    # Determine collections to search
    if request.collection == "all":
        collections = [c["name"] for c in vs.list_collections()]
    else:
        collections = [request.collection]
    
    all_results = []
    
    for coll in collections:
        try:
            results = vs.search(
                collection_name=coll,
                query=request.query,
                limit=request.limit,
            )
            for doc in results:
                all_results.append({
                    "collection": coll,
                    "doc_id": doc["id"],
                    "content": doc["content"],
                    "relevance": round(1.0 - doc.get("distance", 0), 3),
                    "metadata": doc.get("metadata", {}),
                })
        except Exception as e:
            logger.debug(f"Search in {coll} failed: {e}")
    
    # Sort by relevance
    all_results.sort(key=lambda x: x["relevance"], reverse=True)
    
    return {
        "query": request.query,
        "total_results": len(all_results),
        "results": all_results[:request.limit * len(collections)],
    }


@router.post("/documents", summary="Add document")
def add_document(request: AddDocumentRequest):
    """Add a document to the knowledge base."""
    from knowledge_base.vector_store import get_vector_store
    
    vs = get_vector_store()
    
    try:
        vs.add_document(
            collection_name=request.collection,
            doc_id=request.doc_id,
            content=request.content,
            metadata=request.metadata,
        )
        return {
            "status": "added",
            "doc_id": request.doc_id,
            "collection": request.collection,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents/{collection}/{doc_id}", summary="Delete document")
def delete_document(collection: str, doc_id: str):
    """Delete a document from the knowledge base."""
    from knowledge_base.vector_store import get_vector_store
    
    vs = get_vector_store()
    
    if vs.delete_document(collection, doc_id):
        return {"status": "deleted", "doc_id": doc_id, "collection": collection}
    else:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")


@router.get("/documents/{collection}/{doc_id}", summary="Get document")
def get_document(collection: str, doc_id: str):
    """Retrieve a specific document."""
    from knowledge_base.vector_store import get_vector_store
    
    vs = get_vector_store()
    
    try:
        # Search for the document
        results = vs.search(
            collection_name=collection,
            query=f"id:{doc_id}",  # Attempt ID-based search
            limit=1,
        )
        
        if results and results[0]["id"] == doc_id:
            return results[0]
        
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


import logging
logger = logging.getLogger(__name__)
