"""
Reflection memory store. 
Stores learning experiences (failures -> proposed solutions) in SQLite 
so agents can retrieve them as contextual few-shot examples for future runs.
"""

import json
from typing import List, Dict, Optional
from integrations.data_warehouse.sqlite_client import get_connection

def save_reflection(agent_name: str, task: str, failure_context: str, improved_plan: str) -> None:
    """Save an agent reflection so it can learn from mistakes."""
    conn = get_connection()
    try:
        # Create table if it doesn't exist
        conn.execute('''
            CREATE TABLE IF NOT EXISTS agent_reflections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT,
                task TEXT,
                failure_context TEXT,
                improved_plan TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.execute(
            '''INSERT INTO agent_reflections (agent_name, task, failure_context, improved_plan) 
               VALUES (?, ?, ?, ?)''',
            (agent_name, task, failure_context, improved_plan)
        )
        conn.commit()
    except Exception as e:
        import logging
        logging.error(f"Failed to save reflection for {agent_name}: {e}")
    finally:
        conn.close()

def get_reflections(agent_name: str, limit: int = 3) -> List[Dict[str, str]]:
    """Retrieve recent learnings for a specific agent to use as few-shot context."""
    conn = get_connection()
    try:
        conn.row_factory = lambda cursor, row: {
            "task": row[0],
            "failure_context": row[1],
            "improved_plan": row[2]
        }
        # SQLite doesn't error on missing table if we wrap in try, but better to ensure exists
        cur = conn.execute(
            """SELECT task, failure_context, improved_plan 
               FROM agent_reflections 
               WHERE agent_name = ? 
               ORDER BY timestamp DESC LIMIT ?""",
            (agent_name, limit)
        )
        return cur.fetchall()
    except Exception:
        # Safe fallback if table missing
        return []
    finally:
        conn.close()
