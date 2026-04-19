"""
Knowledge Base Agent — Semantic search and document retrieval.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Type

from pydantic import BaseModel

from agents.base_agent import BaseAgent
from config.settings import Settings
from human_loop.manager import HITLManager
from langchain_core.runnables import RunnableConfig


class KnowledgeBaseInput(BaseModel):
    """Input schema for knowledge base queries."""
    action: str = "search"
    query: str = ""
    collection: str = "all"
    limit: int = 5


class KnowledgeBaseOutput(BaseModel):
    """Output schema for knowledge base results."""
    success: bool
    results: Dict[str, Any] = {}
    error: Optional[str] = None


class KnowledgeBaseAgent(BaseAgent):
    """
    Knowledge Base Agent.

    Capabilities:
    ─────────────
    • search — semantic search across knowledge base collections
    """

    name: str = "knowledge_base"

    def __init__(
        self,
        config: Settings,
        tool_registry=None,
        hitl_manager: Optional[HITLManager] = None,
    ):
        super().__init__(config, tool_registry, hitl_manager)
        self._register_tools()

    def _register_tools(self) -> None:
        """Register knowledge base tools."""
        # For now, we'll handle KB search directly without separate tools
        pass

    @property
    def input_schema(self) -> Type[BaseModel]:
        return KnowledgeBaseInput

    @property
    def output_schema(self) -> Type[BaseModel]:
        return KnowledgeBaseOutput

    def get_subgraph(self):
        # Simple agent - no complex graph needed
        return None

    def execute(self, input_data: Dict[str, Any], config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
        """
        Execute knowledge base search.
        """
        from observability.logger import get_logger
        from observability.pii_sanitizer import PIISanitizer

        logger = get_logger("knowledge_base_agent")

        try:
            # Sanitize input
            safe_input = PIISanitizer.sanitize_dict(input_data)

            action = safe_input.get("action", "search")
            query = safe_input.get("query", "")
            collection = safe_input.get("collection", "all")
            limit = safe_input.get("limit", 5)

            logger.info("KB search initiated", data={
                "action": action,
                "query_length": len(query),
                "collection": collection,
                "limit": limit
            })

            if action == "search":
                results = self._perform_search(query, collection, limit)
                return {
                    "success": True,
                    "results": results
                }
            else:
                return {
                    "success": False,
                    "error": f"Unknown action: {action}"
                }

        except Exception as e:
            logger.error("KB search failed", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }

    def _perform_search(self, query: str, collection: str, limit: int) -> Dict[str, Any]:
        """Perform semantic search across knowledge base."""
        from knowledge_base.vector_store import get_vector_store

        try:
            vs = get_vector_store()

            # Determine collections to search
            if collection == "all":
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
                collections = [collection_map.get(collection, "vendor_data")]

            results = {
                "query": query,
                "collections_searched": collections,
                "documents": [],
                "total_results": 0,
            }

            # Search each collection
            for coll_name in collections:
                try:
                    search_results = vs.search(
                        collection_name=coll_name,
                        query=query,
                        limit=limit,
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
                    # Log but continue with other collections
                    continue

            results["total_results"] = len(results["documents"])

            # Sort by relevance
            results["documents"].sort(key=lambda x: x["relevance_score"], reverse=True)

            return results

        except Exception as e:
            return {
                "error": f"Search failed: {str(e)}",
                "documents": [],
                "total_results": 0
            }