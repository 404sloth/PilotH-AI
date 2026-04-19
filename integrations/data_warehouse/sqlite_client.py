"""
SQLite Client — Central connection manager and schema initializer.

ALL SQL execution is contained within the DAL modules (vendor_db.py, etc.).
This module only creates/maintains the connection and defines the schema.
"""

import sqlite3
import os
import contextlib
import logging
from typing import Iterator

logger = logging.getLogger(__name__)

# Allow override via env var for testing/docker; default to workspace root
_DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "pilot_db.sqlite",
)
DB_PATH: str = os.environ.get("SQLITE_DB_PATH", _DEFAULT_DB_PATH)


@contextlib.contextmanager
def get_db_connection() -> Iterator[sqlite3.Connection]:
    """
    Context manager that yields a configured SQLite connection.
    Automatically closes the connection on exit.
    Enables WAL mode for concurrent reads and foreign key enforcement.
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA cache_size = -64000")  # ~64 MB page cache
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# BCNF-Normalised Schema
# ---------------------------------------------------------------------------
_DDL = [
    # --- Lookup / Reference tables ---
    """CREATE TABLE IF NOT EXISTS service_categories (
        id   INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    )""",
    """CREATE TABLE IF NOT EXISTS industries (
        id   INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    )""",
    # --- Core vendor entity ---
    """CREATE TABLE IF NOT EXISTS vendors (
        id               TEXT    PRIMARY KEY,          -- e.g. "V-12345"
        name             TEXT    NOT NULL,
        category_id      INTEGER NOT NULL REFERENCES service_categories(id),
        industry_id      INTEGER NOT NULL REFERENCES industries(id),
        country          TEXT    NOT NULL DEFAULT 'US',
        primary_email    TEXT,
        phone            TEXT,
        website          TEXT,
        contract_status  TEXT    NOT NULL DEFAULT 'active',   -- active | expired | pending | suspended
        tier             TEXT    NOT NULL DEFAULT 'standard', -- preferred | standard | trial
        registered_at    TEXT    NOT NULL DEFAULT (datetime('now')),
        UNIQUE(name)
    )""",
    # --- Capabilities / services each vendor provides ---
    """CREATE TABLE IF NOT EXISTS vendor_services (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_id   TEXT    NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
        service_tag TEXT    NOT NULL,   -- e.g. "cloud_hosting", "devops", "data_analytics"
        UNIQUE(vendor_id, service_tag)
    )""",
    # --- Aggregated historical performance (one row per vendor) ---
    """CREATE TABLE IF NOT EXISTS vendor_performance (
        id                         INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_id                  TEXT    NOT NULL UNIQUE REFERENCES vendors(id) ON DELETE CASCADE,
        avg_delivery_days          REAL    DEFAULT 0,
        on_time_rate               REAL    DEFAULT 0,   -- 0..1
        quality_score              REAL    DEFAULT 0,   -- 0..100
        communication_score        REAL    DEFAULT 0,   -- 0..100
        innovation_score           REAL    DEFAULT 0,   -- 0..100
        cost_competitiveness       REAL    DEFAULT 0,   -- 0..100  (higher = cheaper)
        defect_rate                REAL    DEFAULT 0,   -- 0..1
        total_projects_completed   INTEGER DEFAULT 0,
        avg_client_rating          REAL    DEFAULT 0,   -- 1..5
        last_reviewed_at           TEXT    DEFAULT (datetime('now'))
    )""",
    # --- Pricing  (decomposed from vendor to avoid multi-value dependency) ---
    """CREATE TABLE IF NOT EXISTS vendor_pricing (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_id       TEXT    NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
        service_tag     TEXT    NOT NULL,
        rate_type       TEXT    NOT NULL,  -- hourly | fixed | monthly | per_unit
        amount          REAL    NOT NULL,
        currency        TEXT    NOT NULL DEFAULT 'USD',
        valid_from      TEXT,
        valid_until     TEXT,
        UNIQUE(vendor_id, service_tag, rate_type)
    )""",
    # --- Contracts ---
    """CREATE TABLE IF NOT EXISTS contracts (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_id           TEXT    NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
        contract_reference  TEXT    NOT NULL UNIQUE,
        effective_date      TEXT    NOT NULL,
        expiration_date     TEXT    NOT NULL,
        total_value         REAL    NOT NULL,
        currency            TEXT    NOT NULL DEFAULT 'USD',
        payment_terms       TEXT,
        auto_renewal        INTEGER NOT NULL DEFAULT 0,  -- boolean
        termination_clause  TEXT,
        renewal_terms       TEXT,
        summary             TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS contract_deliverables (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
        deliverable TEXT    NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS contract_conditions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
        condition   TEXT    NOT NULL
    )""",
    # --- Projects & Milestones ---
    """CREATE TABLE IF NOT EXISTS projects (
        id          TEXT    PRIMARY KEY,   -- e.g. "PRJ-001"
        vendor_id   TEXT    NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
        name        TEXT    NOT NULL,
        description TEXT,
        status      TEXT    NOT NULL DEFAULT 'active',  -- active | completed | paused | cancelled
        started_at  TEXT,
        due_at      TEXT,
        budget      REAL
    )""",
    """CREATE TABLE IF NOT EXISTS milestones (
        id                    TEXT    PRIMARY KEY,
        project_id            TEXT    NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        name                  TEXT    NOT NULL,
        due_date              TEXT    NOT NULL,
        status                TEXT    NOT NULL DEFAULT 'not_started',
        completion_percentage REAL    NOT NULL DEFAULT 0 CHECK(completion_percentage BETWEEN 0 AND 100),
        notes                 TEXT,
        days_overdue          INTEGER DEFAULT 0
    )""",
    # --- SLA definitions & records ---
    """CREATE TABLE IF NOT EXISTS sla_definitions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_id   TEXT    NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
        metric_name TEXT    NOT NULL,
        target      REAL    NOT NULL,
        unit        TEXT    NOT NULL,
        UNIQUE(vendor_id, metric_name)
    )""",
    """CREATE TABLE IF NOT EXISTS sla_records (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_id    TEXT    NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
        period_start TEXT    NOT NULL,
        period_end   TEXT    NOT NULL,
        recorded_at  TEXT    NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS sla_metrics (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        sla_record_id INTEGER NOT NULL REFERENCES sla_records(id) ON DELETE CASCADE,
        metric_name   TEXT    NOT NULL,
        target        REAL    NOT NULL,
        actual        REAL    NOT NULL,
        unit          TEXT    NOT NULL,
        compliant     INTEGER NOT NULL DEFAULT 1,   -- boolean
        trend         TEXT    NOT NULL DEFAULT 'stable'  -- improving | declining | stable
    )""",
    # --- Project → Vendor selection decisions (the key new business entity) ---
    """CREATE TABLE IF NOT EXISTS client_projects (
        id               TEXT    PRIMARY KEY,   -- e.g. "CP-001"
        client_name      TEXT    NOT NULL,
        project_name     TEXT    NOT NULL,
        service_required TEXT    NOT NULL,      -- service_tag to match
        budget_max       REAL,
        start_date       TEXT,
        end_date         TEXT,
        priority         TEXT    NOT NULL DEFAULT 'medium',   -- low | medium | high | critical
        region           TEXT,                  -- optional geographic constraint
        created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS client_project_requirements (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        client_project_id  TEXT    NOT NULL REFERENCES client_projects(id) ON DELETE CASCADE,
        requirement_key    TEXT    NOT NULL,   -- e.g. "min_quality_score"
        requirement_value  TEXT    NOT NULL    -- stored as string, typed by key
    )""",
    """CREATE TABLE IF NOT EXISTS vendor_selections (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        client_project_id  TEXT    NOT NULL REFERENCES client_projects(id) ON DELETE CASCADE,
        vendor_id          TEXT    NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
        fit_score          REAL    NOT NULL,   -- 0..100 composite
        selected           INTEGER NOT NULL DEFAULT 0,  -- boolean
        selection_reason   TEXT,
        selected_at        TEXT    DEFAULT (datetime('now')),
        UNIQUE(client_project_id, vendor_id)
    )""",
    # --- Indexes for fast multi-table JOINs ---
    "CREATE INDEX IF NOT EXISTS idx_vendor_services_tag    ON vendor_services(service_tag)",
    "CREATE INDEX IF NOT EXISTS idx_vendor_performance_vid ON vendor_performance(vendor_id)",
    "CREATE INDEX IF NOT EXISTS idx_milestones_project     ON milestones(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_sla_metrics_record     ON sla_metrics(sla_record_id)",
    "CREATE INDEX IF NOT EXISTS idx_sla_records_vendor     ON sla_records(vendor_id)",
    "CREATE INDEX IF NOT EXISTS idx_vendor_selections_cp   ON vendor_selections(client_project_id)",
    "CREATE INDEX IF NOT EXISTS idx_contracts_vendor       ON contracts(vendor_id)",
]


def init_db(seed: bool = True) -> None:
    """
    Create all tables (vendor + meeting) and optionally seed representative data.
    Safe to call multiple times — uses IF NOT EXISTS guards.
    """
    logger.info("Initialising database at: %s", DB_PATH)
    with get_db_connection() as conn:
        cur = conn.cursor()
        for stmt in _DDL:
            cur.execute(stmt)
        conn.commit()

        if seed:
            cur.execute("SELECT COUNT(*) FROM vendors")
            if cur.fetchone()[0] == 0:
                logger.info("Seeding vendor mock data…")
                _seed(conn)

    # Create meeting / person tables (separate DDL in meeting_db)
    from integrations.data_warehouse.meeting_db import (
        create_meeting_tables,
        seed_meeting_data,
    )

    create_meeting_tables()
    if seed:
        seed_meeting_data()

    logger.info("Database ready.")


# ---------------------------------------------------------------------------
# Seed helpers — rich, BCNF-compliant data
# ---------------------------------------------------------------------------
def _seed(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    # Service categories
    cats = [
        "IT Services", "Cloud & Infrastructure", "Data Analytics", 
        "DevOps & CI/CD", "Cybersecurity", "Manufacturing", 
        "Logistics", "Marketing & Design", "Legal & Compliance",
        "AI Research", "Sustainable Energy", "Hardware Ops",
        "Strategic Consulting", "Staff Augmentation", "Remote Infrastructure"
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO service_categories(name) VALUES(?)", [(c,) for c in cats]
    )

    # Industries
    inds = [
        "Technology", "Finance", "Healthcare", "Retail", 
        "Manufacturing", "Government", "Automotive", "Energy"
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO industries(name) VALUES(?)", [(i,) for i in inds]
    )

    def cat_id(name):
        cur.execute("SELECT id FROM service_categories WHERE name=?", (name,))
        res = cur.fetchone()
        return res[0] if res else 1

    def ind_id(name):
        cur.execute("SELECT id FROM industries WHERE name=?", (name,))
        res = cur.fetchone()
        return res[0] if res else 1

    # Vendors (Expanding from 8 to 25)
    vendors = [
        ("V-001", "Acme Cloud Solutions", cat_id("Cloud & Infrastructure"), ind_id("Technology"), "US", "sales@acme.cloud", "+1-555-0101", "https://acme.cloud", "active", "preferred"),
        ("V-002", "Globex Technologies", cat_id("IT Services"), ind_id("Technology"), "US", "contact@globex.tech", "+1-555-0202", "https://globex.tech", "active", "standard"),
        ("V-003", "Initech DevOps Ltd", cat_id("DevOps & CI/CD"), ind_id("Technology"), "UK", "hello@initech.dev", "+44-20-0303", "https://initech.dev", "active", "preferred"),
        ("V-004", "Umbrella Data Corp", cat_id("Data Analytics"), ind_id("Finance"), "US", "info@umbrelladata.com", "+1-555-0404", "https://umbrelladata.com", "active", "standard"),
        ("V-005", "SkyNet Security", cat_id("Cybersecurity"), ind_id("Government"), "US", "ops@skynet.sec", "+1-555-0505", "https://skynet.sec", "active", "preferred"),
        ("V-006", "FastTrack Logistics", cat_id("Logistics"), ind_id("Retail"), "US", "dispatch@fasttrack.co", "+1-555-0606", "https://fasttrack.co", "active", "standard"),
        ("V-007", "Vertex Analytics", cat_id("Data Analytics"), ind_id("Technology"), "IN", "team@vertexai.in", "+91-98-0707", "https://vertexai.in", "active", "trial"),
        ("V-008", "Nexus Cloud Co", cat_id("Cloud & Infrastructure"), ind_id("Healthcare"), "SG", "info@nexuscloud.sg", "+65-6800-08", "https://nexuscloud.sg", "active", "standard"),
        # New Vendors
        ("V-009", "SolarEdge Systems", cat_id("Sustainable Energy"), ind_id("Energy"), "DE", "energy@solaredge.de", "+49-30-0909", "https://solaredge.de", "active", "preferred"),
        ("V-010", "Tokyo Precision", cat_id("Manufacturing"), ind_id("Automotive"), "JP", "support@tokyo-p.jp", "+81-3-0101", "https://tokyo-p.jp", "active", "standard"),
        ("V-011", "Sydney WebWorks", cat_id("Marketing & Design"), ind_id("Retail"), "AU", "gday@sydneyweb.au", "+61-2-1111", "https://sydneyweb.au", "active", "standard"),
        ("V-012", "Berlin BlockChain", cat_id("Cybersecurity"), ind_id("Finance"), "DE", "node@berlin-bc.de", "+49-30-1212", "https://berlin-bc.de", "pending", "trial"),
        ("V-013", "CyberMantle UK", cat_id("Cybersecurity"), ind_id("Technology"), "UK", "shield@cybermantle.uk", "+44-20-1313", "https://cybermantle.uk", "active", "preferred"),
        ("V-014", "Deccan Data", cat_id("Data Analytics"), ind_id("Technology"), "IN", "ops@deccan.in", "+91-80-1414", "https://deccan.in", "active", "standard"),
        ("V-015", "Nordic Infrastructure", cat_id("Cloud & Infrastructure"), ind_id("Manufacturing"), "SE", "infra@nordic.se", "+46-8-1515", "https://nordic.se", "active", "standard"),
        ("V-016", "Amazon Web Services", cat_id("Cloud & Infrastructure"), ind_id("Technology"), "US", "enterprise@aws.com", "+1-800-AWS", "https://aws.com", "active", "preferred"),
        ("V-017", "Google Cloud", cat_id("Cloud & Infrastructure"), ind_id("Technology"), "US", "support@gcp.com", "+1-800-GCP", "https://cloud.google.com", "active", "preferred"),
        ("V-018", "Azure Corp", cat_id("Cloud & Infrastructure"), ind_id("Technology"), "US", "sales@azure.com", "+1-800-AZURE", "https://azure.com", "active", "preferred"),
        ("V-019", "Kyoto Robotics", cat_id("Hardware Ops"), ind_id("Manufacturing"), "JP", "bot@kyoto-robot.jp", "+81-75-1919", "https://kyoto-robot.jp", "active", "preferred"),
        ("V-020", "Melbourne Labs", cat_id("AI Research"), ind_id("Healthcare"), "AU", "research@melbourne.au", "+61-3-2020", "https://melbourne.au", "active", "standard"),
        ("V-021", "Zurich Assurance", cat_id("Legal & Compliance"), ind_id("Finance"), "CH", "compliance@zurich.ch", "+41-44-2121", "https://zurich.ch", "active", "preferred"),
        ("V-022", "Shenzhen Circuits", cat_id("Manufacturing"), ind_id("Technology"), "CN", "factory@shenzhen.cn", "+86-755-2222", "https://shenzhen.cn", "active", "standard"),
        ("V-023", "Rio Logistics", cat_id("Logistics"), ind_id("Retail"), "BR", "cargo@rio.br", "+55-21-2323", "https://rio.br", "suspended", "standard"),
        ("V-024", "Tel Aviv Tech", cat_id("AI Research"), ind_id("Technology"), "IL", "info@telaviv.io", "+972-3-2424", "https://telaviv.io", "active", "preferred"),
        ("V-025", "Nairobi Green", cat_id("Sustainable Energy"), ind_id("Government"), "KE", "solar@nairobi.ke", "+254-20-2525", "https://nairobi.ke", "active", "standard"),
        ("V-026", "Cloud Native Partners", cat_id("Cloud & Infrastructure"), ind_id("Technology"), "US", "contact@cloudnative.com", "+1-555-8888", "https://cloudnative.com", "active", "preferred"),
        ("V-027", "Azure Specialized Ltd", cat_id("Cloud & Infrastructure"), ind_id("Healthcare"), "UK", "info@azurespec.co.uk", "+44-20-8277", "https://azurespec.co.uk", "active", "standard"),
        ("V-028", "GCP Experts Group", cat_id("Cloud & Infrastructure"), ind_id("Finance"), "US", "hello@gcpexperts.com", "+1-555-9999", "https://gcpexperts.com", "active", "preferred"),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO vendors(id,name,category_id,industry_id,country,primary_email,phone,website,contract_status,tier) VALUES(?,?,?,?,?,?,?,?,?,?)",
        vendors,
    )

    # Performance
    perf = [
        ("V-001", 3.2, 0.97, 92.0, 90.0, 85.0, 75.0, 0.01, 150, 4.8),
        ("V-003", 2.0, 0.98, 95.0, 92.0, 92.0, 68.0, 0.01, 220, 4.9),
        ("V-005", 1.5, 0.99, 94.0, 88.0, 88.0, 62.0, 0.00, 100, 4.9),
        ("V-007", 5.8, 0.86, 82.0, 78.0, 90.0, 94.0, 0.05, 60, 4.1),
        ("V-009", 4.0, 0.94, 89.0, 85.0, 95.0, 70.0, 0.02, 45, 4.6),
        ("V-013", 2.2, 0.97, 93.0, 94.0, 86.0, 65.0, 0.01, 75, 4.7),
        ("V-016", 1.0, 0.99, 98.0, 85.0, 98.0, 55.0, 0.00, 1500, 4.9),
        ("V-017", 1.1, 0.99, 97.0, 84.0, 99.0, 54.0, 0.00, 1400, 4.8),
        ("V-019", 6.5, 0.92, 91.0, 80.0, 94.0, 72.0, 0.03, 30, 4.5),
        ("V-021", 5.0, 0.95, 88.0, 98.0, 75.0, 50.0, 0.01, 80, 4.4),
        ("V-024", 2.5, 0.98, 96.0, 92.0, 98.0, 68.0, 0.01, 120, 4.9),
    ]
    cur.executemany(
        """INSERT OR IGNORE INTO vendor_performance
           (vendor_id, avg_delivery_days, on_time_rate, quality_score, communication_score,
            innovation_score, cost_competitiveness, defect_rate, total_projects_completed, avg_client_rating)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        perf,
    )

    # Simplified Services and Pricing for brevity in seed
    services = [
        ("V-001", "cloud_hosting"), ("V-001", "managed_kubernetes"),
        ("V-003", "ci_cd_pipelines"), ("V-016", "cloud_hosting"),
        ("V-016", "edge_computing"), ("V-017", "cloud_hosting"),
        ("V-017", "ai_model_training"), ("V-024", "ai_research"),
        ("V-026", "cloud_hosting"), ("V-026", "serverless_ops"),
        ("V-027", "cloud_hosting"), ("V-028", "managed_gcp")
    ]
    cur.executemany("INSERT OR IGNORE INTO vendor_services(vendor_id, service_tag) VALUES(?,?)", services)

    # Contracts
    contracts = [
        (1, "V-001", "CTR-24-X1", "2024-01-01", "2025-12-31", 120000.0, "USD", "Net 30", 1, "90 days notice", "Standard", "Primary cloud hosting"),
        (2, "V-016", "CTR-24-AWS", "2024-02-15", "2026-02-14", 450000.0, "USD", "Net 45", 1, "30 days notice", "Enterprise", "Global infrastructure backup"),
        (3, "V-024", "CTR-24-AIR", "2024-05-01", "2025-04-30", 85000.0, "USD", "Net 15", 0, "60 days notice", "Nil", "AI research collaboration"),
        (4, "V-026", "CTR-24-CN", "2024-01-10", "2025-01-09", 150000.0, "USD", "Net 30", 1, "30 days notice", "Standard", "Cloud native serverless support"),
        (5, "V-028", "CTR-24-GCP", "2024-03-01", "2025-03-01", 300000.0, "USD", "Net 30", 1, "60 days notice", "Standard", "GCP managed services for Finance")
    ]
    cur.executemany(
        """INSERT OR IGNORE INTO contracts
           (id,vendor_id,contract_reference,effective_date,expiration_date,total_value,currency,
            payment_terms,auto_renewal,termination_clause,renewal_terms,summary)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        contracts,
    )

    # SLA
    sla_defs = [
        ("V-001", "Uptime", 99.9, "percent"),
        ("V-016", "Uptime", 99.99, "percent"),
        ("V-024", "Model Accuracy", 95.0, "percent")
    ]
    cur.executemany("INSERT OR IGNORE INTO sla_definitions(vendor_id,metric_name,target,unit) VALUES(?,?,?,?)", sla_defs)

    conn.commit()
