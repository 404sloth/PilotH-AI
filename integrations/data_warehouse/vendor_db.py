"""
Vendor Data Access Layer (DAL) — the ONLY place in the codebase that executes SQL.

All tools, nodes, and agents import functions from this module.
Never write SQL anywhere else.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .sqlite_client import get_db_connection

logger = logging.getLogger(__name__)


# ============================================================
# Vendor lookup
# ============================================================


def search_vendors(
    vendor_name: Optional[str] = None,
    vendor_id: Optional[str] = None,
    service_tag: Optional[str] = None,
    country: Optional[str] = None,
    industry: Optional[str] = None,
    category: Optional[str] = None,
    tier: Optional[str] = None,
    contract_status: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Flexible vendor search with JOIN across service_categories, industries, and vendor_performance.

    Returns a list of vendor records (not sensitive PII fields).
    Filters applied if arguments provided (all optional).
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Rebuild with service_tag handled in JOIN
        query, params = _build_vendor_query(
            vendor_id, vendor_name, service_tag, country, industry, category, tier, contract_status
        )

        query += f" LIMIT {int(limit)}"

        cur.execute(query, params)
        rows = cur.fetchall()

        results = []
        for row in rows:
            r = dict(row)
            # Hydrate services
            cur2 = conn.cursor()
            cur2.execute(
                "SELECT service_tag FROM vendor_services WHERE vendor_id = ?",
                (r["vendor_id"],),
            )
            r["services"] = [s["service_tag"] for s in cur2.fetchall()]
            results.append(r)

        return results


def _build_vendor_query(
    vendor_id: Optional[str],
    vendor_name: Optional[str],
    service_tag: Optional[str],
    country: Optional[str],
    industry: Optional[str] = None,
    category: Optional[str] = None,
    tier: Optional[str] = None,
    contract_status: Optional[str] = None,
) -> tuple[str, list]:
    """Internal helper to assemble the vendor search query safely."""
    base = """
        SELECT
            v.id                        AS vendor_id,
            v.name,
            v.tier,
            v.country,
            v.contract_status,
            v.website,
            sc.name                     AS category,
            ind.name                    AS industry,
            vp.avg_delivery_days,
            vp.on_time_rate,
            vp.quality_score,
            vp.communication_score,
            vp.innovation_score,
            vp.cost_competitiveness,
            vp.defect_rate,
            vp.total_projects_completed,
            vp.avg_client_rating
        FROM vendors v
        LEFT JOIN service_categories sc  ON sc.id = v.category_id
        LEFT JOIN industries ind         ON ind.id = v.industry_id
        LEFT JOIN vendor_performance vp ON vp.vendor_id = v.id
    """
    joins: List[str] = []
    filters: List[str] = []
    params: List[Any] = []

    if service_tag:
        joins.append(
            "JOIN vendor_services vs2 ON vs2.vendor_id = v.id AND vs2.service_tag = ?"
        )
        params.append(service_tag)

    if vendor_id:
        filters.append("v.id = ?")
        params.append(vendor_id)

    if vendor_name:
        filters.append("LOWER(v.name) LIKE ?")
        params.append(f"%{vendor_name.lower()}%")

    if country:
        # Fuzzy country match: allow full names or common abbreviations
        country_map = {
            "united states": "US", "usa": "US", "us": "US",
            "united kingdom": "GB", "uk": "GB", "gb": "GB",
            "germany": "DE", "deutschland": "DE", "de": "DE",
            "india": "IN", "in": "IN",
            "france": "FR", "fr": "FR",
            "canada": "CA", "ca": "CA",
        }
        mapped = country_map.get(country.lower(), country.upper())
        filters.append("v.country = ?")
        params.append(mapped)

    if industry:
        filters.append("LOWER(ind.name) LIKE ?")
        params.append(f"%{industry.lower()}%")

    if category:
        filters.append("LOWER(sc.name) LIKE ?")
        params.append(f"%{category.lower()}%")

    if tier:
        filters.append("v.tier = ?")
        params.append(tier.lower())

    if contract_status:
        filters.append("v.contract_status = ?")
        params.append(contract_status.lower())

    sql = base + " ".join(joins)
    if filters:
        sql += " WHERE " + " AND ".join(filters)

    logger.debug(f"Vendor Search SQL: {sql} | Params: {params}")
    return sql, params


def get_vendor_by_id(vendor_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single vendor record with full details."""
    results = search_vendors(vendor_id=vendor_id, limit=1)
    return results[0] if results else None


# ============================================================
# Vendor matching / best-fit selection
# ============================================================


def find_best_vendors_for_service(
    service_tag: str,
    requirements: Dict[str, Any],
    country: Optional[str] = None,
    top_n: int = 5,
) -> List[Dict[str, Any]]:
    """
    Core intelligence query: find and rank vendors capable of providing `service_tag`
    that satisfy the given `requirements` dict.

    Requirements keys (all optional):
        min_quality_score       float 0-100
        min_on_time_rate        float 0-1
        max_monthly_budget      float
        min_avg_client_rating   float 1-5
        required_tier           str  (preferred | standard | trial)

    Returns ranked list with composite `fit_score` (0-100).
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Base: vendors offering this service_tag
        query = """
            SELECT
                v.id                        AS vendor_id,
                v.name,
                v.tier,
                v.country,
                v.contract_status,
                v.website,
                sc.name                     AS category,
                vp.avg_delivery_days,
                vp.on_time_rate,
                vp.quality_score,
                vp.communication_score,
                vp.innovation_score,
                vp.cost_competitiveness,
                vp.defect_rate,
                vp.total_projects_completed,
                vp.avg_client_rating,
                vpr.amount                  AS monthly_rate,
                vpr.currency
            FROM vendors v
            JOIN vendor_services        vs  ON vs.vendor_id = v.id AND vs.service_tag = ?
            JOIN service_categories     sc  ON sc.id = v.category_id
            LEFT JOIN vendor_performance vp ON vp.vendor_id = v.id
            LEFT JOIN vendor_pricing     vpr ON vpr.vendor_id = v.id
                                             AND vpr.service_tag = ?
                                             AND vpr.rate_type IN ('monthly', 'fixed')
            WHERE v.contract_status = 'active'
        """

        params: List[Any] = [service_tag, service_tag]

        # Mandatory hard filters
        if country:
            query += " AND v.country = ?"
            params.append(country.upper())

        min_quality = float(requirements.get("min_quality_score", 0))
        if min_quality > 0:
            query += " AND vp.quality_score >= ?"
            params.append(min_quality)

        min_on_time = float(requirements.get("min_on_time_rate", 0))
        if min_on_time > 0:
            query += " AND vp.on_time_rate >= ?"
            params.append(min_on_time)

        min_rating = float(requirements.get("min_avg_client_rating", 0))
        if min_rating > 0:
            query += " AND vp.avg_client_rating >= ?"
            params.append(min_rating)

        required_tier = requirements.get("required_tier")
        if required_tier:
            query += " AND v.tier = ?"
            params.append(required_tier)

        max_budget = requirements.get("max_monthly_budget")
        if max_budget is not None:
            query += " AND (vpr.amount IS NULL OR vpr.amount <= ?)"
            params.append(float(max_budget))

        cur.execute(query, params)
        rows = cur.fetchall()

        # Score and sort
        scored = []
        for row in rows:
            r = dict(row)
            r["fit_score"] = _compute_fit_score(r, requirements)
            # Add services list
            cur2 = conn.cursor()
            cur2.execute(
                "SELECT service_tag FROM vendor_services WHERE vendor_id = ?",
                (r["vendor_id"],),
            )
            r["services"] = [s["service_tag"] for s in cur2.fetchall()]
            scored.append(r)

        scored.sort(key=lambda x: x["fit_score"], reverse=True)
        return scored[:top_n]


def _compute_fit_score(vendor: Dict[str, Any], requirements: Dict[str, Any]) -> float:
    """
    Composite weighted fit score (0-100).

    Weights are deliberately transparent so the LLM can explain them.
    """
    weights = {
        "quality": 0.25,
        "on_time": 0.20,
        "cost": 0.20,
        "rating": 0.15,
        "communication": 0.10,
        "innovation": 0.05,
        "experience": 0.05,
    }

    def pct(val, lo, hi):
        if val is None:
            return 50.0
        return max(0.0, min(100.0, (val - lo) / (hi - lo) * 100))

    quality_score = float(vendor.get("quality_score") or 0)
    on_time_score = (float(vendor.get("on_time_rate") or 0)) * 100
    cost_score = float(vendor.get("cost_competitiveness") or 50)
    rating_score = pct(vendor.get("avg_client_rating"), 1, 5)
    communication_score = float(vendor.get("communication_score") or 50)
    innovation_score = float(vendor.get("innovation_score") or 50)
    experience_score = pct(vendor.get("total_projects_completed"), 0, 300)

    composite = (
        weights["quality"] * quality_score
        + weights["on_time"] * on_time_score
        + weights["cost"] * cost_score
        + weights["rating"] * rating_score
        + weights["communication"] * communication_score
        + weights["innovation"] * innovation_score
        + weights["experience"] * experience_score
    )

    return round(composite, 2)


# ============================================================
# Contract helpers
# ============================================================


def get_contract_details(
    vendor_id: Optional[str] = None,
    contract_reference: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Retrieve a contract with deliverables and conditions via multi-table JOIN.
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        sql = """
            SELECT
                c.id, c.vendor_id, c.contract_reference,
                c.effective_date, c.expiration_date,
                c.total_value, c.currency, c.payment_terms,
                c.auto_renewal, c.termination_clause,
                c.renewal_terms, c.summary,
                v.name  AS vendor_name
            FROM contracts c
            JOIN vendors v ON v.id = c.vendor_id
            WHERE 1=1
        """
        params: List[Any] = []

        if contract_reference:
            sql += " AND c.contract_reference = ?"
            params.append(contract_reference)
        elif vendor_id:
            sql += " AND c.vendor_id = ? ORDER BY c.expiration_date DESC LIMIT 1"
            params.append(vendor_id)
        else:
            return None

        cur.execute(sql, params)
        row = cur.fetchone()
        if not row:
            return None

        cid = row["id"]
        cur.execute(
            "SELECT deliverable FROM contract_deliverables WHERE contract_id = ?",
            (cid,),
        )
        deliverables = [r["deliverable"] for r in cur.fetchall()]

        cur.execute(
            "SELECT condition FROM contract_conditions WHERE contract_id = ?", (cid,)
        )
        conditions = [r["condition"] for r in cur.fetchall()]

        result = dict(row)
        result["deliverables"] = deliverables
        result["conditions"] = conditions
        return result


# ============================================================
# SLA helpers
# ============================================================


def get_sla_compliance(
    vendor_id: str,
    period_days: int = 30,
) -> Optional[Dict[str, Any]]:
    """
    Fetch the most recent SLA record + metrics for a vendor and compute compliance.
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, period_start, period_end
            FROM sla_records
            WHERE vendor_id = ?
            ORDER BY period_end DESC
            LIMIT 1
            """,
            (vendor_id,),
        )
        record = cur.fetchone()
        if not record:
            return None

        cur.execute(
            """
            SELECT metric_name, target, actual, unit, compliant, trend
            FROM sla_metrics
            WHERE sla_record_id = ?
            """,
            (record["id"],),
        )
        metrics = [dict(r) for r in cur.fetchall()]

        if not metrics:
            return None

        compliant_count = sum(1 for m in metrics if m["compliant"])
        overall_compliance = round(compliant_count / len(metrics) * 100, 1)

        return {
            "period_start": record["period_start"],
            "period_end": record["period_end"],
            "overall_compliance": overall_compliance,
            "metrics": metrics,
        }


# ============================================================
# Milestone helpers
# ============================================================


def get_milestones(
    vendor_id: str,
    project_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve milestones for a vendor (optionally filtered by project) via JOIN.
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        sql = """
            SELECT
                m.id, m.name, m.due_date, m.status,
                m.completion_percentage, m.notes, m.days_overdue,
                p.id   AS project_id,
                p.name AS project_name
            FROM milestones m
            JOIN projects p ON p.id = m.project_id AND p.vendor_id = ?
        """
        params: List[Any] = [vendor_id]

        if project_id:
            sql += " AND p.id = ?"
            params.append(project_id)

        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


# ============================================================
# Client project helpers
# ============================================================


def get_client_project(client_project_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a client project with its requirements map."""
    with get_db_connection() as conn:
        cur = conn.cursor()

        cur.execute("SELECT * FROM client_projects WHERE id = ?", (client_project_id,))
        row = cur.fetchone()
        if not row:
            return None

        cur.execute(
            "SELECT requirement_key, requirement_value FROM client_project_requirements WHERE client_project_id = ?",
            (client_project_id,),
        )
        reqs = {r["requirement_key"]: r["requirement_value"] for r in cur.fetchall()}

        result = dict(row)
        result["requirements"] = reqs
        return result


def save_vendor_selection(
    client_project_id: str,
    vendor_id: str,
    fit_score: float,
    selected: bool,
    reason: str,
) -> None:
    """Persist a vendor selection decision for a client project."""
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO vendor_selections(client_project_id, vendor_id, fit_score, selected, selection_reason)
            VALUES(?,?,?,?,?)
            ON CONFLICT(client_project_id, vendor_id) DO UPDATE SET
                fit_score = excluded.fit_score,
                selected  = excluded.selected,
                selection_reason = excluded.selection_reason,
                selected_at = datetime('now')
            """,
            (client_project_id, vendor_id, fit_score, int(selected), reason),
        )
        conn.commit()


def get_saved_selections(client_project_id: str) -> List[Dict[str, Any]]:
    """Retrieve previously saved vendor selections for a client project."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT vs.vendor_id, v.name AS vendor_name, vs.fit_score, vs.selected,
                   vs.selection_reason, vs.selected_at
            FROM vendor_selections vs
            JOIN vendors v ON v.id = vs.vendor_id
            WHERE vs.client_project_id = ?
            ORDER BY vs.fit_score DESC
            """,
            (client_project_id,),
        )
        return [dict(r) for r in cur.fetchall()]


# ============================================================
# Analytics
# ============================================================


def get_vendor_scorecard(vendor_id: str) -> Optional[Dict[str, Any]]:
    """
    Return a full enriched scorecard for a vendor: perf + latest SLA + active milestones.
    """
    vendor = get_vendor_by_id(vendor_id)
    if not vendor:
        return None

    sla = get_sla_compliance(vendor_id)
    milestones = get_milestones(vendor_id)
    contract = get_contract_details(vendor_id=vendor_id)

    return {
        "vendor": vendor,
        "sla": sla,
        "milestones": milestones,
        "contract": contract,
    }

# ============================================================
# Project Lifecycle Helpers
# ============================================================


def get_meeting_full(meeting_id: str) -> Optional[Dict[str, Any]]:
    """Fetch meeting with project_id and transcript."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, title, project_id, transcript FROM meetings WHERE id = ?",
            (meeting_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def save_rfp(rfp_id: str, project_id: str, content: str) -> str:
    """Persist an RFP generated for a project."""
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO rfps(id, project_id, content) VALUES(?,?,?)",
            (rfp_id, project_id, content),
        )
        conn.commit()
    return rfp_id


def get_rfp(rfp_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve RFP details."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM rfps WHERE id = ?", (rfp_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_all_active_vendors() -> List[Dict[str, Any]]:
    """Return all vendors with active contracts."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, primary_email FROM vendors WHERE contract_status = 'active'"
        )
        return [dict(r) for r in cur.fetchall()]


def save_vendor_response(
    response_id: str, rfp_id: str, vendor_id: str, response_text: str
) -> str:
    """Save a vendor's response to an RFP."""
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO vendor_responses(id, rfp_id, vendor_id, response_text)
            VALUES(?,?,?,?)
            """,
            (response_id, rfp_id, vendor_id, response_text),
        )
        conn.commit()
    return response_id


def get_vendor_responses(rfp_id: str) -> List[Dict[str, Any]]:
    """Retrieve all responses for a given RFP."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT vr.*, v.name AS vendor_name
            FROM vendor_responses vr
            JOIN vendors v ON v.id = vr.vendor_id
            WHERE vr.rfp_id = ?
            """,
            (rfp_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def update_vendor_response_score(response_id: str, score: float) -> None:
    """Update evaluation score for a vendor response."""
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE vendor_responses SET score = ? WHERE id = ?", (score, response_id)
        )
        conn.commit()


def select_vendor_for_project(project_id: str, vendor_id: str) -> None:
    """Finalize vendor selection for a project."""
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE projects SET vendor_id = ? WHERE id = ?", (vendor_id, project_id)
        )
        conn.commit()


def save_sow(sow_id: str, project_id: str, vendor_id: str, content: str) -> str:
    """Persist a Statement of Work."""
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO sows(id, project_id, vendor_id, content) VALUES(?,?,?,?)",
            (sow_id, project_id, vendor_id, content),
        )
        conn.commit()
    return sow_id


def save_lifecycle_milestone(
    m_id: str, sow_id: str, title: str, due_date: str, status: str = "on-time"
) -> None:
    """Insert a milestone linked to an SOW."""
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO lifecycle_milestones(id, sow_id, title, due_date, status)
            VALUES(?,?,?,?,?)
            """,
            (m_id, sow_id, title, due_date, status),
        )
        conn.commit()


def get_sow_for_project(project_id: str) -> Optional[Dict[str, Any]]:
    """Fetch SOW for a project."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM sows WHERE project_id = ? LIMIT 1", (project_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_milestones_for_project(project_id: str) -> List[Dict[str, Any]]:
    """Retrieve all lifecycle milestones for a project via its SOW."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT m.* 
            FROM lifecycle_milestones m
            JOIN sows s ON s.id = m.sow_id
            WHERE s.project_id = ?
            """,
            (project_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def save_daily_status(
    milestone_id: str,
    task_desc: str,
    planned_date: str,
    actual_completion: Optional[str],
    status: str,
) -> None:
    """Record a daily task status."""
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO daily_status(milestone_id, task_description, planned_date, actual_completion, status)
            VALUES(?,?,?,?,?)
            """,
            (milestone_id, task_desc, planned_date, actual_completion, status),
        )
        conn.commit()


def update_milestone_status(milestone_id: str, status: str) -> None:
    """Update milestone status based on task analysis."""
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE lifecycle_milestones SET status = ? WHERE id = ?",
            (status, milestone_id),
        )
        conn.commit()


def get_project_health_metrics(project_id: str) -> Dict[str, Any]:
    """Gather statistical data for health calculation."""
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Milestone stats
        cur.execute(
            """
            SELECT m.status, COUNT(*) as count 
            FROM lifecycle_milestones m
            JOIN sows s ON s.id = m.sow_id
            WHERE s.project_id = ?
            GROUP BY m.status
            """,
            (project_id,),
        )
        m_counts = {r["status"]: r["count"] for r in cur.fetchall()}

        # Daily status stats
        cur.execute(
            """
            SELECT ds.status, COUNT(*) as count
            FROM daily_status ds
            JOIN lifecycle_milestones m ON m.id = ds.milestone_id
            JOIN sows s ON s.id = m.sow_id
            WHERE s.project_id = ?
            GROUP BY ds.status
            """,
            (project_id,),
        )
        ds_counts = {r["status"]: r["count"] for r in cur.fetchall()}

        return {"milestones": m_counts, "tasks": ds_counts}


def get_all_projects_summary() -> List[Dict[str, Any]]:
    """Return a high-level summary of all projects for the dashboard."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, vendor_id, status, created_at FROM projects")
        projects = [dict(r) for r in cur.fetchall()]
        
        summaries = []
        for p in projects:
            health = get_project_health_metrics(p["id"])
            
            # Find next milestone
            cur.execute(
                """
                SELECT title, due_date 
                FROM lifecycle_milestones m
                JOIN sows s ON s.id = m.sow_id
                WHERE s.project_id = ? AND m.due_date >= DATE('now')
                ORDER BY m.due_date ASC LIMIT 1
                """,
                (p["id"],),
            )
            next_ms = cur.fetchone()
            
            # Compute progress
            total_m = sum(health["milestones"].values())
            completed_m = health["milestones"].get("on-time", 0) # simplified
            progress = (completed_m / total_m * 100) if total_m > 0 else 0
            
            summaries.append({
                "id": p["id"],
                "name": p["name"],
                "status": p["status"],
                "progress_percent": round(progress, 1),
                "next_milestone": dict(next_ms) if next_ms else None,
                "health_color": "green" if progress > 80 else "amber" if progress > 40 else "red"
            })
        return summaries


def get_detailed_timeline(project_id: str) -> List[Dict[str, Any]]:
    """Aggregate all lifecycle events into a chronological timeline."""
    events = []
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # 1. Meetings
        cur.execute("SELECT id, title, meeting_type, transcript, created_at as date FROM meetings WHERE project_id = ? ORDER BY date ASC", (project_id,))
        for r in cur.fetchall():
            events.append({"type": "meeting", "id": r["id"], "title": r["title"], "sub_type": r["meeting_type"], "content": r["transcript"], "date": r["date"]})
            
        # 2. RFPs
        cur.execute("SELECT id, content, created_at as date FROM rfps WHERE project_id = ? ORDER BY date ASC", (project_id,))
        for r in cur.fetchall():
            events.append({"type": "rfp", "id": r["id"], "content": r["content"], "date": r["date"]})
            
        # 3. Vendor Responses and Selection
        cur.execute(
            """
            SELECT vr.id, v.name as vendor_name, vr.score, vr.submitted_at as date
            FROM vendor_responses vr
            JOIN rfps r ON r.id = vr.rfp_id
            JOIN vendors v ON v.id = vr.vendor_id
            WHERE r.project_id = ?
            ORDER BY date ASC
            """,
            (project_id,),
        )
        for r in cur.fetchall():
            events.append({"type": "vendor_response", "id": r["id"], "vendor_name": r["vendor_name"], "score": r["score"], "date": r["date"]})
            
        # 4. SOWs
        cur.execute("SELECT id, content, created_at as date FROM sows WHERE project_id = ? ORDER BY date ASC", (project_id,))
        for r in cur.fetchall():
            # Get milestones for this SOW
            cur.execute("SELECT title, due_date, status FROM lifecycle_milestones WHERE sow_id = ?", (r["id"],))
            milestones = [dict(ms) for ms in cur.fetchall()]
            events.append({"type": "sow", "id": r["id"], "content": r["content"], "milestones": milestones, "date": r["date"]})
            
    # Sort events by date
    events.sort(key=lambda x: x["date"] or "")
    return events
