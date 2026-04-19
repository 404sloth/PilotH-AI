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

def get_schema_summary() -> str:
    """Provides a high-level summary of available tables and their purpose."""
    return """
Available Databases:
1. Vendor Management System:
   - vendors: Core vendor details (name, tier, industry, country).
   - vendor_services: Services/capabilities provided by vendors.
   - vendor_performance: Historical metrics (SLA, quality, cost).
   - contracts: Legal agreements and values.
   - projects/milestones: Active work and deadlines.
   - sla_definitions/metrics: Performance targets and actuals.

2. Communication & Meetings:
   - persons: Employee directory with roles and departments.
   - meetings: Scheduled and past meetings.
   - meeting_attendees: Who attended which meeting.
   - meeting_action_items: Tasks assigned during meetings.
   - communications: Log of emails/slack with sentiment analysis.
"""
