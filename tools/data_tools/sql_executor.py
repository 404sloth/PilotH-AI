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

class DynamicSQLExecutorTool(StructuredTool):
    name: str = "dynamic_sql_executor"
    description: str = (
        "Powerful tool to query the enterprise database for vendors, communications, and projects. "
        "Use this for complex filtering, aggregations, or cross-domain lookups that aren't covered by simpler tools. "
        "Input should be a specific natural language data request."
    )
    args_schema: Type[BaseModel] = DynamicSQLInput

    def execute(self, validated_input: DynamicSQLInput) -> Dict[str, Any]:
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

        system_prompt = f"""You are a Text-to-SQL engine for PilotH.
SCHEMA:
{schema_min}

SUMMARY:
{schema_summary}

RULES:
1. ONLY SELECT.
2. FETCH ONLY NECESSARY COLUMNS.
3. Use INNER/LEFT JOINs if needed.
4. LIMIT 50 unless specified.
5. Return ONLY SQL string. No markdown.
"""
        
        try:
            llm = get_llm(temperature=0) # Deterministic for SQL
            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Generate SQL for: {nl_query}")
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
