"""
Knowledge Base Search Tool — Query vendor documents, agreements, and communications.

Provides semantic search across:
  - Agreements and contracts
  - Communications (emails, meeting notes)
  - Vendor data and profiles
  - Financial reports
  - Policy documentation
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool

logger = logging.getLogger(__name__)


class KnowledgeBaseSearchInput(BaseModel):
    """Input schema for knowledge base search."""
    query: str = Field(..., description="Search query")
    collection: str = Field("vendors", description="Collection to search: vendors, agreements, communications, financial, or all")
    limit: int = Field(5, ge=1, le=20, description="Maximum number of results")


from langchain_core.runnables import RunnableConfig


class KnowledgeBaseSearchTool(StructuredTool):
    """Search knowledge base for relevant documents and information."""
    
    name: str = "knowledge_base_search"
    description: str = "Search and retrieve relevant documents from the knowledge base using semantic search"
    args_schema: type[BaseModel] = KnowledgeBaseSearchInput
    
    def execute(
        self,
        validated_input: KnowledgeBaseSearchInput,
        config: Optional[RunnableConfig] = None,
    ) -> Dict[str, Any]:
        """Execute knowledge base search."""
        try:
            from knowledge_base.vector_store import get_vector_store
            
            vs = get_vector_store()
            
            # Determine collections to search
            if validated_input.collection == "all":
                collections = ["agreements", "communications", "vendor_data", "financial", "internal_policies"]
            else:
                # Map friendly names to actual collection names
                collection_map = {
                    "vendors": "vendor_data",
                    "agreements": "agreements",
                    "communications": "communications",
                    "financial": "financial",
                    "policies": "internal_policies",
                }
                collections = [collection_map.get(validated_input.collection, "vendor_data")]
            
            results = {
                "query": validated_input.query,
                "collections_searched": collections,
                "documents": [],
                "total_results": 0,
            }
            
            # Search each collection
            for coll_name in collections:
                try:
                    search_results = vs.search(
                        collection_name=coll_name,
                        query=validated_input.query,
                        limit=validated_input.limit,
                    )
                    
                    for doc in search_results:
                        results["documents"].append({
                            "id": doc["id"],
                            "collection": coll_name,
                            "content_preview": doc["content"][:300] + "..." if len(doc["content"]) > 300 else doc["content"],
                            "full_content": doc["content"],
                            "relevance_score": round(1.0 - doc.get("distance", 0), 3),
                            "metadata": doc.get("metadata", {}),
                        })
                except Exception as e:
                    logger.debug(f"[KB] Search in {coll_name} failed: {e}")
            
            results["total_results"] = len(results["documents"])
            
            # Sort by relevance
            results["documents"].sort(key=lambda x: x["relevance_score"], reverse=True)
            
            return results
        except Exception as e:
            logger.error(f"[Tool] {self.name} failed: {e}")
            return {"success": False, "error": str(e)}
