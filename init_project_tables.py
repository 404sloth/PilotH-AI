import os
import sqlite3
import logging
from integrations.data_warehouse.sqlite_client import get_db_connection, DB_PATH

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def column_exists(cursor, table_name, column_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns

def run_migration():
    logger.info(f"Connecting to database: {DB_PATH}")
    
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # 1. Augment existing tables
        logger.info("Augmenting existing tables...")
        
        # Add created_at to projects
        if not column_exists(cur, 'projects', 'created_at'):
            logger.info("Adding 'created_at' to 'projects' table")
            cur.execute("ALTER TABLE projects ADD COLUMN created_at TEXT DEFAULT (datetime('now'))")
        
        # Add project_id to meetings
        if not column_exists(cur, 'meetings', 'project_id'):
            logger.info("Adding 'project_id' to 'meetings' table")
            cur.execute("ALTER TABLE meetings ADD COLUMN project_id TEXT REFERENCES projects(id)")

        # 2. Create new tables
        logger.info("Creating new lifecycle management tables...")
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS rfps (
                id         TEXT    PRIMARY KEY,
                project_id TEXT    NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                content    TEXT,
                created_at TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS vendor_responses (
                id            TEXT    PRIMARY KEY,
                rfp_id        TEXT    NOT NULL REFERENCES rfps(id) ON DELETE CASCADE,
                vendor_id     TEXT    NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
                response_text TEXT,
                score         REAL,
                submitted_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sows (
                id         TEXT    PRIMARY KEY,
                project_id TEXT    NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                vendor_id  TEXT    NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
                content    TEXT,
                created_at TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        
        # Using lifecycle_milestones to avoid conflict with existing milestones
        cur.execute("""
            CREATE TABLE IF NOT EXISTS lifecycle_milestones (
                id           TEXT    PRIMARY KEY,
                sow_id       TEXT    NOT NULL REFERENCES sows(id) ON DELETE CASCADE,
                title        TEXT    NOT NULL,
                due_date     TEXT    NOT NULL,
                status       TEXT    NOT NULL DEFAULT 'on-time',
                completed_at TEXT
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_status (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                milestone_id      TEXT    NOT NULL REFERENCES lifecycle_milestones(id) ON DELETE CASCADE,
                task_description  TEXT    NOT NULL,
                planned_date      TEXT    NOT NULL,
                actual_completion TEXT,
                status            TEXT    NOT NULL DEFAULT 'pending',
                notes             TEXT
            )
        """)
        
        # 3. Populate demo vendors
        logger.info("Populating demo vendor data...")
        
        demo_vendors = [
            ("V-D1", "BlueStar Tech", "IT Services", "contact@bluestar.tech", "Frontend Development"),
            ("V-D2", "DataFlow Systems", "Data Analytics", "ops@dataflow.io", "Big Data Analytics"),
            ("V-D3", "SecureNet", "Cybersecurity", "support@securenet.com", "Cybersecurity"),
            ("V-D4", "CloudScale", "Cloud & Infrastructure", "sales@cloudscale.net", "Infrastructure as Code"),
            ("V-D5", "AI-Logic", "AI Research", "team@ailogic.ai", "Machine Learning"),
            ("V-D6", "MobileFirst", "IT Services", "hello@mobilefirst.co", "iOS/Android Apps"),
            ("V-D7", "GreenEnergy IT", "Sustainable Energy", "energy@greenit.de", "Sustainable Cloud"),
            ("V-D8", "RapidDev", "Staff Augmentation", "dev@rapiddev.uk", "Agile Staffing"),
            ("V-D9", "QualityFirst", "IT Services", "qa@qualityfirst.in", "QA Automation"),
            ("V-D10", "InsightConsult", "Strategic Consulting", "info@insight.ch", "Strategic Advisory"),
        ]
        
        for vid, vname, cat_name, email, expertise in demo_vendors:
            # Get category_id
            cur.execute("SELECT id FROM service_categories WHERE name = ?", (cat_name,))
            row = cur.fetchone()
            cat_id = row[0] if row else 1
            
            # Insert vendor
            cur.execute("""
                INSERT OR IGNORE INTO vendors(id, name, category_id, industry_id, primary_email, contract_status, tier)
                VALUES(?,?,?,?,?,'active','standard')
            """, (vid, vname, cat_id, 1, email)) # industry_id defaulted to 1 (Technology)
            
            # Insert service tag as expertise
            service_tag = expertise.lower().replace(" ", "_").replace("/", "_")
            cur.execute("INSERT OR IGNORE INTO vendor_services(vendor_id, service_tag) VALUES(?,?)", (vid, service_tag))
            
        conn.commit()
        logger.info("✅ SUCCESS: Database migration and seeding complete.")

if __name__ == "__main__":
    run_migration()
