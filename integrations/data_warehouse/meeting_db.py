"""
Meeting & Communication DAL — the ONLY place that executes SQL for meeting/person data.

Tables managed here:
  persons, person_skills, calendar_events, meetings, meeting_attendees,
  meeting_agendas, meeting_action_items, communications
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .sqlite_client import get_db_connection

logger = logging.getLogger(__name__)


# ============================================================
# Schema creation (called by sqlite_client.init_db)
# ============================================================

MEETING_DDL = [
    # People directory — disambiguates same names by dept/project/location
    """CREATE TABLE IF NOT EXISTS persons (
        id             TEXT    PRIMARY KEY,          -- e.g. "P-001"
        full_name      TEXT    NOT NULL,
        email          TEXT    NOT NULL UNIQUE,
        department     TEXT    NOT NULL,
        project        TEXT,
        role           TEXT    NOT NULL,
        location       TEXT    NOT NULL,             -- office location / city
        timezone       TEXT    NOT NULL DEFAULT 'UTC',
        manager_id     TEXT    REFERENCES persons(id),
        phone          TEXT,
        slack_handle   TEXT,
        bio            TEXT,                         -- short professional bio
        active         INTEGER NOT NULL DEFAULT 1   -- 1=active, 0=inactive
    )""",
    """CREATE TABLE IF NOT EXISTS person_skills (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id TEXT    NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
        skill     TEXT    NOT NULL,
        UNIQUE(person_id, skill)
    )""",
    # Calendar events (synced from Google Calendar or mocked)
    """CREATE TABLE IF NOT EXISTS calendar_events (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id      TEXT    NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
        external_id    TEXT,                         -- Google Calendar event ID
        title          TEXT    NOT NULL,
        start_time     TEXT    NOT NULL,             -- ISO 8601
        end_time       TEXT    NOT NULL,
        timezone       TEXT    NOT NULL DEFAULT 'UTC',
        is_blocked     INTEGER NOT NULL DEFAULT 1,   -- 1=busy, 0=free
        location       TEXT,
        description    TEXT
    )""",
    # Meetings
    """CREATE TABLE IF NOT EXISTS meetings (
        id             TEXT    PRIMARY KEY,          -- e.g. "MTG-001"
        title          TEXT    NOT NULL,
        organizer_id   TEXT    NOT NULL REFERENCES persons(id),
        start_time     TEXT,
        end_time       TEXT,
        timezone       TEXT    NOT NULL DEFAULT 'UTC',
        duration_mins  INTEGER DEFAULT 60,
        location       TEXT,
        description    TEXT,
        status         TEXT    NOT NULL DEFAULT 'scheduled',  -- scheduled|cancelled|completed
        meeting_type   TEXT    NOT NULL DEFAULT 'internal',   -- internal|external|hybrid
        google_event_id TEXT,
        created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS meeting_attendees (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        meeting_id  TEXT    NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
        person_id   TEXT    NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
        role        TEXT    NOT NULL DEFAULT 'attendee',  -- organizer|presenter|attendee|optional
        rsvp        TEXT    NOT NULL DEFAULT 'pending',   -- accepted|declined|pending
        UNIQUE(meeting_id, person_id)
    )""",
    """CREATE TABLE IF NOT EXISTS meeting_agendas (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        meeting_id   TEXT    NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
        topic        TEXT    NOT NULL,
        duration_mins INTEGER DEFAULT 10,
        presenter_id TEXT    REFERENCES persons(id),
        agenda_order INTEGER DEFAULT 0,
        notes        TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS meeting_action_items (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        meeting_id   TEXT    NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
        assignee_id  TEXT    REFERENCES persons(id),
        description  TEXT    NOT NULL,
        due_date     TEXT,
        priority     TEXT    NOT NULL DEFAULT 'medium',   -- low|medium|high|critical
        status       TEXT    NOT NULL DEFAULT 'open',     -- open|in_progress|done|cancelled
        created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
    )""",
    # Communication log (emails, slack, etc.) for sentiment analysis
    """CREATE TABLE IF NOT EXISTS communications (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id       TEXT    REFERENCES persons(id),
        recipient_id    TEXT    REFERENCES persons(id),
        channel         TEXT    NOT NULL DEFAULT 'email',  -- email|slack|teams
        subject         TEXT,
        content         TEXT,
        sentiment_score REAL,                               -- -1..+1
        sentiment_label TEXT,                               -- positive|negative|neutral
        meeting_id      TEXT    REFERENCES meetings(id),
        created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
    )""",
    # Indexes
    "CREATE INDEX IF NOT EXISTS idx_persons_email      ON persons(email)",
    "CREATE INDEX IF NOT EXISTS idx_persons_department ON persons(department)",
    "CREATE INDEX IF NOT EXISTS idx_cal_events_person  ON calendar_events(person_id)",
    "CREATE INDEX IF NOT EXISTS idx_cal_events_time    ON calendar_events(start_time, end_time)",
    "CREATE INDEX IF NOT EXISTS idx_meeting_attendees  ON meeting_attendees(meeting_id)",
    "CREATE INDEX IF NOT EXISTS idx_action_meeting     ON meeting_action_items(meeting_id)",
    "CREATE INDEX IF NOT EXISTS idx_comms_sender       ON communications(sender_id)",
]


def create_meeting_tables() -> None:
    """Create meeting-related tables. Called during init_db."""
    with get_db_connection() as conn:
        for stmt in MEETING_DDL:
            conn.execute(stmt)
        conn.commit()


def seed_meeting_data() -> None:
    """Seed representative persons and calendar data for testing."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM persons")
        if cur.fetchone()[0] > 0:
            return  # already seeded

        persons = [
            (
                "P-001",
                "Anil Yadav",
                "anil.yadav@company.com",
                "Engineering",
                "PilotH",
                "CTO",
                "Mumbai",
                "Asia/Kolkata",
                None,
                "+91-98765-00001",
                "@anil",
                "Chief Technology Officer leading the AI platform team.",
            ),
            (
                "P-002",
                "Priya Sharma",
                "priya.sharma@company.com",
                "Product",
                "PilotH",
                "Product Manager",
                "Mumbai",
                "Asia/Kolkata",
                "P-001",
                "+91-98765-00002",
                "@priya",
                "PM driving PilotH roadmap and stakeholder management.",
            ),
            (
                "P-003",
                "James Carter",
                "james.carter@company.com",
                "Engineering",
                "PilotH",
                "Senior Engineer",
                "New York",
                "America/New_York",
                "P-001",
                "+1-212-555-0003",
                "@james",
                "Backend engineer specialising in LangGraph orchestration.",
            ),
            (
                "P-004",
                "Mei Lin",
                "mei.lin@company.com",
                "Data Science",
                "Analytics",
                "Data Scientist",
                "Singapore",
                "Asia/Singapore",
                "P-001",
                "+65-9000-0004",
                "@mei",
                "Data scientist working on predictive analytics models.",
            ),
            (
                "P-005",
                "Anil Kumar",
                "anil.kumar@company.com",
                "Finance",
                "Budget",
                "Financial Analyst",
                "Delhi",
                "Asia/Kolkata",
                None,
                "+91-98765-00005",
                "@anilk",
                "Financial analyst — different person from Anil Yadav CTO.",
            ),
            (
                "P-006",
                "Sofia Martinez",
                "sofia.martinez@company.com",
                "Marketing",
                "Growth",
                "Marketing Lead",
                "London",
                "Europe/London",
                None,
                "+44-20-0006",
                "@sofia",
                "Marketing lead overseeing growth campaigns.",
            ),
            (
                "P-007",
                "David Kim",
                "david.kim@company.com",
                "Engineering",
                "PilotH",
                "DevOps Engineer",
                "Seoul",
                "Asia/Seoul",
                "P-001",
                "+82-10-0007",
                "@david",
                "DevOps engineer managing CI/CD and infrastructure.",
            ),
            (
                "P-008",
                "Rachel Green",
                "rachel.green@company.com",
                "Legal",
                "Compliance",
                "Legal Counsel",
                "New York",
                "America/New_York",
                "P-001",
                "+1-212-555-0008",
                "@rachel",
                "Legal counsel overseeing compliance and contracts.",
            ),
        ]
        cur.executemany(
            "INSERT OR IGNORE INTO persons(id,full_name,email,department,project,role,location,timezone,manager_id,phone,slack_handle,bio) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            persons,
        )

        skills = [
            ("P-001", "Python"),
            ("P-001", "LLM Engineering"),
            ("P-001", "System Architecture"),
            ("P-002", "Product Strategy"),
            ("P-002", "Agile"),
            ("P-002", "Stakeholder Management"),
            ("P-003", "Python"),
            ("P-003", "LangGraph"),
            ("P-003", "FastAPI"),
            ("P-004", "ML"),
            ("P-004", "Python"),
            ("P-004", "Tableau"),
            ("P-005", "Financial Modelling"),
            ("P-005", "Excel"),
            ("P-005", "SQL"),
            ("P-006", "SEO"),
            ("P-006", "Content Marketing"),
            ("P-006", "Analytics"),
            ("P-007", "Kubernetes"),
            ("P-007", "Terraform"),
            ("P-007", "GitHub Actions"),
            ("P-008", "Contract Law"),
            ("P-008", "GDPR"),
            ("P-008", "Risk Management"),
        ]
        cur.executemany(
            "INSERT OR IGNORE INTO person_skills(person_id, skill) VALUES(?,?)", skills
        )

        # Calendar events (busy blocks)
        now = datetime.utcnow()
        events = [
            (
                "P-001",
                None,
                "Team Standup",
                (now + timedelta(hours=2)).isoformat(),
                (now + timedelta(hours=2, minutes=30)).isoformat(),
                "Asia/Kolkata",
                1,
            ),
            (
                "P-001",
                None,
                "Board Review",
                (now + timedelta(hours=5)).isoformat(),
                (now + timedelta(hours=7)).isoformat(),
                "Asia/Kolkata",
                1,
            ),
            (
                "P-002",
                None,
                "Sprint Planning",
                (now + timedelta(hours=1)).isoformat(),
                (now + timedelta(hours=3)).isoformat(),
                "Asia/Kolkata",
                1,
            ),
            (
                "P-003",
                None,
                "Client Call",
                (now + timedelta(hours=3)).isoformat(),
                (now + timedelta(hours=4)).isoformat(),
                "America/New_York",
                1,
            ),
            (
                "P-004",
                None,
                "Data Review",
                (now + timedelta(hours=6)).isoformat(),
                (now + timedelta(hours=7)).isoformat(),
                "Asia/Singapore",
                1,
            ),
        ]
        cur.executemany(
            "INSERT OR IGNORE INTO calendar_events(person_id, external_id, title, start_time, end_time, timezone, is_blocked) VALUES(?,?,?,?,?,?,?)",
            events,
        )

        # Sample meeting
        cur.execute(
            "INSERT OR IGNORE INTO meetings(id, title, organizer_id, duration_mins, timezone, status, meeting_type) VALUES(?,?,?,?,?,?,?)",
            (
                "MTG-001",
                "PilotH Architecture Review",
                "P-001",
                60,
                "Asia/Kolkata",
                "completed",
                "internal",
            ),
        )
        attendees = [
            ("MTG-001", "P-001", "organizer", "accepted"),
            ("MTG-001", "P-002", "attendee", "accepted"),
            ("MTG-001", "P-003", "presenter", "accepted"),
            ("MTG-001", "P-007", "attendee", "accepted"),
        ]
        cur.executemany(
            "INSERT OR IGNORE INTO meeting_attendees(meeting_id,person_id,role,rsvp) VALUES(?,?,?,?)",
            attendees,
        )

        agenda = [
            ("MTG-001", "LangGraph Workflow Design", 15, "P-003", 1),
            ("MTG-001", "Vector Memory Integration", 15, "P-004", 2),
            ("MTG-001", "DevOps Pipeline Review", 15, "P-007", 3),
            ("MTG-001", "Open Q&A and Next Steps", 15, "P-001", 4),
        ]
        cur.executemany(
            "INSERT OR IGNORE INTO meeting_agendas(meeting_id,topic,duration_mins,presenter_id,agenda_order) VALUES(?,?,?,?,?)",
            agenda,
        )

        action_items = [
            (
                "MTG-001",
                "P-003",
                "Implement parallel graph execution",
                (now + timedelta(days=5)).date().isoformat(),
                "high",
            ),
            (
                "MTG-001",
                "P-007",
                "Setup monitoring stack with Grafana",
                (now + timedelta(days=7)).date().isoformat(),
                "medium",
            ),
            (
                "MTG-001",
                "P-001",
                "Finalise architecture decision record",
                (now + timedelta(days=3)).date().isoformat(),
                "high",
            ),
        ]
        cur.executemany(
            "INSERT OR IGNORE INTO meeting_action_items(meeting_id,assignee_id,description,due_date,priority) VALUES(?,?,?,?,?)",
            action_items,
        )

        conn.commit()


# ============================================================
# Person queries
# ============================================================


def find_persons(
    name: Optional[str] = None,
    email: Optional[str] = None,
    department: Optional[str] = None,
    project: Optional[str] = None,
    location: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Disambiguate person lookups by multiple fields.
    Returns list with skills attached.
    """
    with get_db_connection() as conn:
        cur = conn.cursor()
        sql = """
            SELECT p.id, p.full_name, p.email, p.department, p.project, p.role,
                   p.location, p.timezone, p.phone, p.slack_handle, p.bio, p.active,
                   mgr.full_name AS manager_name
            FROM persons p
            LEFT JOIN persons mgr ON mgr.id = p.manager_id
            WHERE p.active = 1
        """
        params: List[Any] = []
        if email:
            sql += " AND p.email = ?"
            params.append(email)
        if name:
            sql += " AND LOWER(p.full_name) LIKE ?"
            params.append(f"%{name.lower()}%")
        if department:
            sql += " AND LOWER(p.department) LIKE ?"
            params.append(f"%{department.lower()}%")
        if project:
            sql += " AND LOWER(p.project) LIKE ?"
            params.append(f"%{project.lower()}%")
        if location:
            sql += " AND LOWER(p.location) LIKE ?"
            params.append(f"%{location.lower()}%")
        sql += f" LIMIT {int(limit)}"

        cur.execute(sql, params)
        rows = cur.fetchall()
        results = []
        for row in rows:
            r = dict(row)
            cur2 = conn.cursor()
            cur2.execute(
                "SELECT skill FROM person_skills WHERE person_id=?", (r["id"],)
            )
            r["skills"] = [s["skill"] for s in cur2.fetchall()]
            results.append(r)
        return results


def get_person_by_id(person_id: str) -> Optional[Dict[str, Any]]:
    results = find_persons(limit=1)  # won't work; use direct query
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT p.*, mgr.full_name AS manager_name
            FROM persons p LEFT JOIN persons mgr ON mgr.id = p.manager_id
            WHERE p.id = ?
        """,
            (person_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        r = dict(row)
        cur.execute("SELECT skill FROM person_skills WHERE person_id=?", (person_id,))
        r["skills"] = [s["skill"] for s in cur.fetchall()]
        return r


def get_person_by_email(email: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT p.*, mgr.full_name AS manager_name
            FROM persons p LEFT JOIN persons mgr ON mgr.id = p.manager_id
            WHERE p.email = ?
        """,
            (email,),
        )
        row = cur.fetchone()
        if not row:
            return None
        r = dict(row)
        cur.execute("SELECT skill FROM person_skills WHERE person_id=?", (r["id"],))
        r["skills"] = [s["skill"] for s in cur.fetchall()]
        return r


# ============================================================
# Calendar / availability queries
# ============================================================


def get_busy_blocks(person_id: str, from_iso: str, to_iso: str) -> List[Dict[str, Any]]:
    """Return busy calendar blocks for a person in a given window."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT title, start_time, end_time, timezone
            FROM calendar_events
            WHERE person_id = ?
              AND is_blocked = 1
              AND end_time   > ?
              AND start_time < ?
            ORDER BY start_time
        """,
            (person_id, from_iso, to_iso),
        )
        return [dict(r) for r in cur.fetchall()]


def create_calendar_event(
    person_id: str,
    title: str,
    start_time: str,
    end_time: str,
    timezone: str,
    external_id: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
) -> int:
    """Insert a calendar event and return its row id."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO calendar_events(person_id, external_id, title, start_time, end_time, timezone, is_blocked, description, location)
            VALUES(?,?,?,?,?,?,1,?,?)
        """,
            (
                person_id,
                external_id,
                title,
                start_time,
                end_time,
                timezone,
                description,
                location,
            ),
        )
        conn.commit()
        return cur.lastrowid


# ============================================================
# Meeting CRUD
# ============================================================


def create_meeting(
    meeting_id: str,
    title: str,
    organizer_id: str,
    duration_mins: int = 60,
    timezone: str = "UTC",
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    description: Optional[str] = None,
    meeting_type: str = "internal",
) -> str:
    """Create a meeting record. Returns meeting_id."""
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO meetings(id, title, organizer_id, start_time, end_time, timezone, duration_mins, description, meeting_type)
            VALUES(?,?,?,?,?,?,?,?,?)
        """,
            (
                meeting_id,
                title,
                organizer_id,
                start_time,
                end_time,
                timezone,
                duration_mins,
                description,
                meeting_type,
            ),
        )
        conn.commit()
    return meeting_id


def add_attendees(meeting_id: str, attendees: List[Dict[str, str]]) -> None:
    """Add attendees: [{person_id, role, rsvp}]"""
    with get_db_connection() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO meeting_attendees(meeting_id, person_id, role, rsvp) VALUES(?,?,?,?)",
            [
                (
                    meeting_id,
                    a["person_id"],
                    a.get("role", "attendee"),
                    a.get("rsvp", "pending"),
                )
                for a in attendees
            ],
        )
        conn.commit()


def save_agenda(meeting_id: str, agenda_items: List[Dict[str, Any]]) -> None:
    """Save agenda items [{topic, duration_mins, presenter_id, order, notes}]"""
    with get_db_connection() as conn:
        conn.executemany(
            "INSERT INTO meeting_agendas(meeting_id,topic,duration_mins,presenter_id,agenda_order,notes) VALUES(?,?,?,?,?,?)",
            [
                (
                    meeting_id,
                    a["topic"],
                    a.get("duration_mins", 10),
                    a.get("presenter_id"),
                    a.get("order", 0),
                    a.get("notes"),
                )
                for a in agenda_items
            ],
        )
        conn.commit()


def save_action_items(meeting_id: str, items: List[Dict[str, Any]]) -> None:
    """Save action items [{assignee_id, description, due_date, priority}]"""
    with get_db_connection() as conn:
        conn.executemany(
            "INSERT INTO meeting_action_items(meeting_id,assignee_id,description,due_date,priority) VALUES(?,?,?,?,?)",
            [
                (
                    meeting_id,
                    i.get("assignee_id"),
                    i["description"],
                    i.get("due_date"),
                    i.get("priority", "medium"),
                )
                for i in items
            ],
        )
        conn.commit()


def get_meeting_full(meeting_id: str) -> Optional[Dict[str, Any]]:
    """Return meeting with attendees, agenda, and action items via JOINs."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM meetings WHERE id=?", (meeting_id,))
        mtg = cur.fetchone()
        if not mtg:
            return None
        result = dict(mtg)

        cur.execute(
            """
            SELECT ma.role, ma.rsvp, p.id AS person_id, p.full_name, p.email, p.department, p.role AS job_role
            FROM meeting_attendees ma JOIN persons p ON p.id = ma.person_id
            WHERE ma.meeting_id = ?
        """,
            (meeting_id,),
        )
        result["attendees"] = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT ag.topic, ag.duration_mins, ag.agenda_order, ag.notes, p.full_name AS presenter_name
            FROM meeting_agendas ag
            LEFT JOIN persons p ON p.id = ag.presenter_id
            WHERE ag.meeting_id = ? ORDER BY ag.agenda_order
        """,
            (meeting_id,),
        )
        result["agenda"] = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT ai.description, ai.due_date, ai.priority, ai.status, p.full_name AS assignee_name
            FROM meeting_action_items ai
            LEFT JOIN persons p ON p.id = ai.assignee_id
            WHERE ai.meeting_id = ?
        """,
            (meeting_id,),
        )
        result["action_items"] = [dict(r) for r in cur.fetchall()]
        return result


def log_communication(
    sender_id: str,
    recipient_id: str,
    channel: str,
    content: str,
    subject: Optional[str] = None,
    sentiment_score: Optional[float] = None,
    sentiment_label: Optional[str] = None,
    meeting_id: Optional[str] = None,
) -> None:
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO communications(sender_id, recipient_id, channel, subject, content,
                sentiment_score, sentiment_label, meeting_id)
            VALUES(?,?,?,?,?,?,?,?)
        """,
            (
                sender_id,
                recipient_id,
                channel,
                subject,
                content,
                sentiment_score,
                sentiment_label,
                meeting_id,
            ),
        )
        conn.commit()
