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
    "pilot_db.sqlite"
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
    conn.execute("PRAGMA cache_size = -64000")   # ~64 MB page cache
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
    from integrations.data_warehouse.meeting_db import create_meeting_tables, seed_meeting_data
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
        "Logistics", "Marketing & Design", "Legal & Compliance"
    ]
    cur.executemany("INSERT OR IGNORE INTO service_categories(name) VALUES(?)", [(c,) for c in cats])

    # Industries
    inds = ["Technology", "Finance", "Healthcare", "Retail", "Manufacturing", "Government"]
    cur.executemany("INSERT OR IGNORE INTO industries(name) VALUES(?)", [(i,) for i in inds])

    def cat_id(name):
        cur.execute("SELECT id FROM service_categories WHERE name=?", (name,))
        return cur.fetchone()[0]

    def ind_id(name):
        cur.execute("SELECT id FROM industries WHERE name=?", (name,))
        return cur.fetchone()[0]

    # Vendors
    vendors = [
        ("V-001", "Acme Cloud Solutions",   cat_id("Cloud & Infrastructure"), ind_id("Technology"),  "US", "sales@acme.cloud",       "+1-555-0101", "https://acme.cloud",      "active",    "preferred"),
        ("V-002", "Globex Technologies",    cat_id("IT Services"),             ind_id("Technology"),  "US", "contact@globex.tech",    "+1-555-0202", "https://globex.tech",     "active",    "standard"),
        ("V-003", "Initech DevOps Ltd",     cat_id("DevOps & CI/CD"),          ind_id("Technology"),  "UK", "hello@initech.dev",      "+44-20-0303", "https://initech.dev",     "active",    "preferred"),
        ("V-004", "Umbrella Data Corp",     cat_id("Data Analytics"),          ind_id("Finance"),     "US", "info@umbrelladata.com",  "+1-555-0404", "https://umbrelladata.com","active",    "standard"),
        ("V-005", "SkyNet Security",        cat_id("Cybersecurity"),           ind_id("Government"),  "US", "ops@skynet.sec",         "+1-555-0505", "https://skynet.sec",      "active",    "preferred"),
        ("V-006", "FastTrack Logistics",    cat_id("Logistics"),               ind_id("Retail"),      "US", "dispatch@fasttrack.co",  "+1-555-0606", "https://fasttrack.co",    "active",    "standard"),
        ("V-007", "Vertex Analytics",       cat_id("Data Analytics"),          ind_id("Technology"),  "IN", "team@vertexai.in",       "+91-98-0707", "https://vertexai.in",     "active",    "trial"),
        ("V-008", "Nexus Cloud Co",         cat_id("Cloud & Infrastructure"),  ind_id("Healthcare"),  "SG", "info@nexuscloud.sg",     "+65-6800-08", "https://nexuscloud.sg",   "active",    "standard"),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO vendors(id,name,category_id,industry_id,country,primary_email,phone,website,contract_status,tier) VALUES(?,?,?,?,?,?,?,?,?,?)",
        vendors
    )

    # Services per vendor
    vendor_services = [
        ("V-001", "cloud_hosting"), ("V-001", "cloud_storage"), ("V-001", "managed_kubernetes"),
        ("V-002", "it_consulting"), ("V-002", "managed_services"), ("V-002", "cloud_hosting"),
        ("V-003", "ci_cd_pipelines"), ("V-003", "devops_consulting"), ("V-003", "infrastructure_as_code"),
        ("V-004", "data_analytics"), ("V-004", "bi_dashboards"), ("V-004", "etl_pipelines"),
        ("V-005", "penetration_testing"), ("V-005", "soc_monitoring"), ("V-005", "compliance_audit"),
        ("V-006", "last_mile_delivery"), ("V-006", "warehousing"), ("V-006", "freight_forwarding"),
        ("V-007", "data_analytics"), ("V-007", "ml_engineering"), ("V-007", "etl_pipelines"),
        ("V-008", "cloud_hosting"), ("V-008", "cloud_storage"), ("V-008", "managed_kubernetes"),
    ]
    cur.executemany("INSERT OR IGNORE INTO vendor_services(vendor_id, service_tag) VALUES(?,?)", vendor_services)

    # Performance (higher = better unless noted)
    perf = [
        #  vid        del   on_t  qual   comm   inno   cost   defect  proj  rating
        ("V-001",  3.5, 0.96,  91.0,  88.0,  82.0,  74.0,  0.02,  142,  4.7),
        ("V-002",  7.0, 0.88,  83.0,  80.0,  68.0,  80.0,  0.05,  98,   4.2),
        ("V-003",  2.0, 0.98,  94.0,  92.0,  90.0,  65.0,  0.01,  210,  4.9),
        ("V-004",  5.5, 0.91,  87.0,  85.0,  78.0,  77.0,  0.03,  176,  4.5),
        ("V-005",  4.0, 0.95,  93.0,  87.0,  85.0,  60.0,  0.01,  88,   4.8),
        ("V-006",  2.5, 0.93,  86.0,  81.0,  70.0,  88.0,  0.04,  320,  4.3),
        ("V-007",  6.0, 0.85,  80.0,  76.0,  88.0,  92.0,  0.06,  55,   4.0),
        ("V-008",  4.5, 0.90,  85.0,  83.0,  75.0,  78.0,  0.04,  120,  4.4),
    ]
    cur.executemany(
        """INSERT OR IGNORE INTO vendor_performance
           (vendor_id, avg_delivery_days, on_time_rate, quality_score, communication_score,
            innovation_score, cost_competitiveness, defect_rate, total_projects_completed, avg_client_rating)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        perf
    )

    # Pricing
    pricing = [
        ("V-001", "cloud_hosting",    "monthly",  4500.0,  "USD"),
        ("V-001", "managed_kubernetes","monthly", 6200.0,  "USD"),
        ("V-002", "managed_services", "monthly",  3800.0,  "USD"),
        ("V-002", "cloud_hosting",    "monthly",  5100.0,  "USD"),
        ("V-003", "ci_cd_pipelines",  "monthly",  2500.0,  "USD"),
        ("V-003", "devops_consulting","hourly",   195.0,   "USD"),
        ("V-004", "data_analytics",   "monthly",  4200.0,  "USD"),
        ("V-004", "etl_pipelines",    "fixed",    28000.0, "USD"),
        ("V-005", "soc_monitoring",   "monthly",  8500.0,  "USD"),
        ("V-006", "warehousing",      "monthly",  1800.0,  "USD"),
        ("V-007", "data_analytics",   "monthly",  2900.0,  "USD"),
        ("V-007", "ml_engineering",   "hourly",   85.0,    "USD"),
        ("V-008", "cloud_hosting",    "monthly",  3900.0,  "USD"),
        ("V-008", "managed_kubernetes","monthly", 5400.0,  "USD"),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO vendor_pricing(vendor_id,service_tag,rate_type,amount,currency) VALUES(?,?,?,?,?)",
        pricing
    )

    # Contracts
    contracts = [
        (1, "V-001", "CTR-2024-001", "2024-01-01", "2025-12-31", 108000.0, "USD", "Net 30", 1,
         "90 days written notice", "Auto-renews for 1 year unless cancelled 90 days prior",
         "Annual cloud hosting contract with Acme Cloud Solutions."),
        (2, "V-003", "CTR-2024-002", "2024-03-01", "2025-02-28",  60000.0, "USD", "Net 15", 0,
         "30 days written notice", "No auto-renewal",
         "DevOps pipeline setup and ongoing support with Initech DevOps Ltd."),
        (3, "V-004", "CTR-2024-003", "2024-06-01", "2025-05-31",  50400.0, "USD", "Net 30", 1,
         "60 days written notice", "Auto-renews unless cancelled 60 days prior",
         "Data analytics subscription with Umbrella Data Corp."),
    ]
    cur.executemany(
        """INSERT OR IGNORE INTO contracts
           (id,vendor_id,contract_reference,effective_date,expiration_date,total_value,currency,
            payment_terms,auto_renewal,termination_clause,renewal_terms,summary)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        contracts
    )

    contract_deliverables = [
        (1, "Monthly cloud infrastructure report"),
        (1, "99.95% uptime guarantee"),
        (1, "24/7 support SLA"),
        (2, "CI/CD pipeline setup for 3 projects"),
        (2, "Monthly DevOps health report"),
        (3, "Weekly BI dashboard refresh"),
        (3, "Quarterly data quality audit"),
    ]
    cur.executemany("INSERT OR IGNORE INTO contract_deliverables(contract_id, deliverable) VALUES(?,?)", contract_deliverables)

    contract_conditions = [
        (1, "Volume discount: 10% after $100k spend"),
        (1, "Data residency in US regions only"),
        (2, "All code/IP owned by client"),
        (3, "Right to audit with 14 days notice"),
    ]
    cur.executemany("INSERT OR IGNORE INTO contract_conditions(contract_id, condition) VALUES(?,?)", contract_conditions)

    # Projects
    projects = [
        ("PRJ-001", "V-001", "Cloud Migration Wave 1",       "Migrating on-prem services to cloud", "active",    "2024-02-01", "2024-08-31",  95000.0),
        ("PRJ-002", "V-003", "DevOps Transformation",         "CI/CD and IaC rollout",               "active",    "2024-03-15", "2024-12-31",  55000.0),
        ("PRJ-003", "V-004", "Revenue Analytics Platform",    "Central KPI dashboard build",         "completed", "2024-01-01", "2024-06-30",  42000.0),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO projects(id,vendor_id,name,description,status,started_at,due_at,budget) VALUES(?,?,?,?,?,?,?,?)",
        projects
    )

    milestones = [
        # PRJ-001
        ("MS-001", "PRJ-001", "Assessment & Planning",   "2024-03-01", "completed",  100.0, None, 0),
        ("MS-002", "PRJ-001", "Dev Environment Lift",    "2024-04-30", "completed",  100.0, None, 0),
        ("MS-003", "PRJ-001", "Staging Migration",       "2024-06-15", "in_progress", 70.0, "On schedule", 0),
        ("MS-004", "PRJ-001", "Production Cutover",      "2024-08-15", "at_risk",     15.0, "Requires security sign-off", 0),
        # PRJ-002
        ("MS-005", "PRJ-002", "Pipeline Design",         "2024-04-30", "completed",  100.0, None, 0),
        ("MS-006", "PRJ-002", "Dev Pipeline Live",       "2024-06-30", "delayed",     30.0, "Blocked by infra access", 12),
        # PRJ-003
        ("MS-007", "PRJ-003", "Data Model Design",       "2024-02-15", "completed",  100.0, None, 0),
        ("MS-008", "PRJ-003", "Dashboard v1 Delivery",   "2024-04-30", "completed",  100.0, None, 0),
        ("MS-009", "PRJ-003", "UAT & Sign-off",          "2024-06-30", "completed",  100.0, None, 0),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO milestones(id,project_id,name,due_date,status,completion_percentage,notes,days_overdue) VALUES(?,?,?,?,?,?,?,?)",
        milestones
    )

    # SLA definitions
    sla_defs = [
        ("V-001", "Uptime",               99.9, "percent"),
        ("V-001", "Response Time (P95)",   4.0, "hours"),
        ("V-001", "Incident Resolution",  24.0, "hours"),
        ("V-003", "Deployment Success Rate", 99.0, "percent"),
        ("V-003", "Pipeline Lead Time",     2.0, "hours"),
        ("V-004", "Dashboard Refresh Lag",  6.0, "hours"),
        ("V-004", "Data Accuracy",         99.5, "percent"),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO sla_definitions(vendor_id,metric_name,target,unit) VALUES(?,?,?,?)",
        sla_defs
    )

    # SLA records and metrics
    cur.execute(
        "INSERT INTO sla_records(id,vendor_id,period_start,period_end) VALUES(1,'V-001','2024-03-01','2024-03-31')"
    )
    sla_metrics_v001 = [
        (1, "Uptime",              99.9,  99.95, "percent", 1, "improving"),
        (1, "Response Time (P95)",  4.0,   3.8,  "hours",   1, "stable"),
        (1, "Incident Resolution", 24.0,  28.5,  "hours",   0, "declining"),
    ]
    cur.executemany(
        "INSERT INTO sla_metrics(sla_record_id,metric_name,target,actual,unit,compliant,trend) VALUES(?,?,?,?,?,?,?)",
        sla_metrics_v001
    )

    cur.execute(
        "INSERT INTO sla_records(id,vendor_id,period_start,period_end) VALUES(2,'V-003','2024-03-01','2024-03-31')"
    )
    sla_metrics_v003 = [
        (2, "Deployment Success Rate", 99.0, 99.7, "percent", 1, "stable"),
        (2, "Pipeline Lead Time",       2.0,  1.8, "hours",   1, "improving"),
    ]
    cur.executemany(
        "INSERT INTO sla_metrics(sla_record_id,metric_name,target,actual,unit,compliant,trend) VALUES(?,?,?,?,?,?,?)",
        sla_metrics_v003
    )

    # Client projects (showcase: multiple vendors for same service)
    client_projects = [
        ("CP-001", "FinTech Innovations", "Cloud Infrastructure Upgrade",
         "cloud_hosting", 60000.0, "2024-09-01", "2025-08-31", "high", "US"),
        ("CP-002", "HealthCare Co",        "Real-time Analytics Platform",
         "data_analytics", 35000.0, "2024-10-01", "2025-03-31", "critical", "US"),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO client_projects(id,client_name,project_name,service_required,budget_max,start_date,end_date,priority,region) VALUES(?,?,?,?,?,?,?,?,?)",
        client_projects
    )

    cp_requirements = [
        # CP-001 cloud_hosting
        ("CP-001", "min_quality_score",       "85"),
        ("CP-001", "min_on_time_rate",         "0.90"),
        ("CP-001", "max_monthly_budget",       "5500"),
        ("CP-001", "required_tier",            "preferred"),
        # CP-002 data_analytics
        ("CP-002", "min_quality_score",        "85"),
        ("CP-002", "min_avg_client_rating",    "4.2"),
        ("CP-002", "max_monthly_budget",       "4500"),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO client_project_requirements(client_project_id,requirement_key,requirement_value) VALUES(?,?,?)",
        cp_requirements
    )

    conn.commit()
