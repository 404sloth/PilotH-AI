"""
Schema Provider — extracts and formats DDL for LLM context.
"""

import logging
from typing import List

logger = logging.getLogger(__name__)

def get_full_schema_ddl() -> str:
    """Concatenates all table definitions into a single string."""
    try:
        from integrations.data_warehouse.sqlite_client import _DDL as VENDOR_DDL
        from integrations.data_warehouse.meeting_db import MEETING_DDL
        
        all_stmts = VENDOR_DDL + MEETING_DDL
        # Filter only CREATE TABLE statements for brevity in context
        table_stmts = [s for s in all_stmts if "CREATE TABLE" in s]
        return "\n\n".join(table_stmts)
    except Exception as e:
        logger.error(f"Failed to extract schema DDL: {e}")
        return ""

def get_minified_schema() -> str:
    """Returns a dense, single-line-per-table schema representation."""
    import re
    full_ddl = get_full_schema_ddl()
    
    # Extract table name and content within parentheses
    table_pattern = re.compile(r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\)", re.DOTALL | re.IGNORECASE)
    
    minified = []
    for table_name, content in table_pattern.findall(full_ddl):
        # Extract column names (first word of each line)
        cols = []
        for line in content.split(','):
            line = line.strip()
            if not line or line.upper().startswith(("PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "CHECK", "CONSTRAINT")):
                continue
            col_name = line.split()[0].strip('"\'')
            cols.append(col_name)
        
        minified.append(f"{table_name}({', '.join(cols)})")
        
    return "\n".join(minified)

def get_db_relationships() -> str:
    """Summaries of key foreign key relationships for JOIN guidance."""
    return """
Key Relationships:
- vendors.category_id -> service_categories.id
- vendors.industry_id -> industries.id
- vendor_services.vendor_id -> vendors.id
- vendor_performance.vendor_id -> vendors.id
- vendor_pricing.vendor_id -> vendors.id
- contracts.vendor_id -> vendors.id
- projects.vendor_id -> vendors.id
- rfps.project_id -> projects.id
- vendor_responses.rfp_id -> rfps.id
- vendor_responses.vendor_id -> vendors.id
- sows.project_id -> projects.id
- sows.vendor_id -> vendors.id
- lifecycle_milestones.sow_id -> sows.id
- daily_status.milestone_id -> lifecycle_milestones.id
- client_projects.id -> client_project_requirements.client_project_id
- vendor_selections.client_project_id -> client_projects.id
- vendor_selections.vendor_id -> vendors.id
"""


def get_schema_summary() -> str:
    """Provides a high-level summary of available tables and their purpose."""
    return """
Strategic Database Summary:
1. Vendor Ecosystem:
   - vendors: Master record. Use for 'contract_status' and 'tier'.
   - vendor_services: List of capabilities. JOIN with vendors to filter by service type.
   - vendor_performance: Critical metrics (quality_score, on_time_rate, communication_score).
   - vendor_pricing: Rates and currencies for various services.

2. Contractual & Compliance:
   - contracts: Legal summaries, total_value, and expiration dates.
   - sla_definitions/metrics: Performance targets and real-time compliance (recorded_at).

3. Project Lifecycle (Strategic Pulse):
   - projects: High-level work streams.
   - rfps & vendor_responses: The procurement and bid process.
   - sows & lifecycle_milestones: The detailed execution plan and current progress.
   - daily_status: Tactical task-level progress (pending/completed).

4. Operations:
   - meetings: Context from transcripts and attendees.
   - communications: Sentiment analysis and interaction logs.
"""
