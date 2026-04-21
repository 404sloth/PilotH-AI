"""
Dynamic SQL Executor — generates and runs SQL SELECT statements from natural language.
"""

import logging
import sqlite3
import re
from typing import Any, Dict, List, Type, Optional

from pydantic import BaseModel, Field
from tools.base_tool import StructuredTool
from integrations.data_warehouse.sqlite_client import get_db_connection
from integrations.data_warehouse.schema_provider import get_full_schema_ddl, get_schema_summary

logger = logging.getLogger(__name__)

class DynamicSQLInput(BaseModel):
    natural_language_query: str = Field(
        ..., 
        description="The user's data request in natural language (e.g., 'What are the top 5 vendors by quality score in the UK?')"
    )

from langchain_core.runnables import RunnableConfig


class DynamicSQLExecutorTool(StructuredTool):
    name: str = "dynamic_sql_executor"
    description: str = (
        "Powerful tool to query the enterprise database for vendors, communications, and projects. "
        "Use this for complex filtering, aggregations, or cross-domain lookups that aren't covered by simpler tools. "
        "Input should be a specific natural language data request."
    )
    args_schema: Type[BaseModel] = DynamicSQLInput

    def execute(
        self,
        validated_input: DynamicSQLInput,
        config: Optional[RunnableConfig] = None,
    ) -> Dict[str, Any]:
        """
        1. Generates SQL from natural language using internal LLM.
        2. Validates SQL (only SELECT).
        3. Executes and returns results.
        """
        from llm.model_factory import get_llm
        from langchain_core.messages import HumanMessage, SystemMessage
        import json

        nl_query = validated_input.natural_language_query
        schema_min = get_minified_schema()
        schema_summary = get_schema_summary()
        relationships = get_db_relationships()

        system_prompt = f"""You are an Expert Text-to-SQL engine for the PilotH Enterprise Platform.
Your goal is to translate natural language requests into precise, optimized SQLite queries.

DATABASES SCHEMA (minified):
{schema_min}

RELATIONSHIPS (JOIN Guide):
{relationships}

STRATEGIC SUMMARY:
{schema_summary}

SQL GENERATION RULES:
1. ONLY generate SELECT statements.
2. OPTIMIZATION: Fetch ONLY necessary columns to avoid data bloat.
3. COMPLEXITY: Heavily use INNER/LEFT JOINs when cross-referencing tables (e.g., vendors + performance).
4. FILTERING: Leverage complex WHERE clauses with AND/OR, LIKE, and range filters (e.g., quality_score > 90).
5. AGGREGATIONS: Use SUM, AVG, COUNT when requesting statistics.
6. LIMIT: Always LIMIT to 50 rows unless explicitly asked for more.
7. FORMAT: Return ONLY the raw SQL string. No markdown, no triple backticks, no explanations.

REASONING:
Before generating the final SQL, think step-by-step about which tables contain the required data and how they link.
Produce the SQL immediately after your internal reasoning.
"""
        
        try:
            llm = get_llm(temperature=0) # Deterministic for SQL
            from integrations.data_warehouse.schema_provider import get_db_relationships
            
            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Request: {nl_query}\n\nThink about the JOINs and WHERE clauses, then provide the SQL.")
            ])
            
            sql = response.content.strip()
            # Clean up markdown if LLM ignored instructions
            sql = re.sub(r'```sql\n?|```', '', sql).strip()
            
            # Security Guardrail: Only SELECT
            if not sql.upper().startswith("SELECT"):
                return {"error": "Only SELECT operations are permitted for security reasons.", "generated_sql": sql}

            logger.info(f"Generated SQL: {sql}")
            
            results = self._run_query(sql)
            
            return {
                "results": results,
                "count": len(results),
                "generated_sql": sql,
                "query_explanation": f"Retrieved data based on request: {nl_query}"
            }

        except Exception as e:
            logger.error(f"Dynamic SQL Tool failed: {e}")
            return {"error": str(e), "step": "sql_generation_or_execution"}

    def _run_query(self, sql: str) -> List[Dict[str, Any]]:
        """Executes the SQL against the local SQLite database."""
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql)
            rows = cur.fetchall()
            return [dict(row) for row in rows]
