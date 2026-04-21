import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.vendor_management.tools.lifecycle_tools import (
    compute_project_health,
    evaluate_vendor_responses,
    generate_mock_vendor_responses,
    generate_rfp_from_meeting,
    generate_sow_from_meeting,
    select_vendor_helper,
    simulate_daily_status,
)
from integrations.data_warehouse.sqlite_client import get_db_connection

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def setup_test_data():
    """Setup a mock project and meeting for the lifecycle test."""
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Ensure we have a dummy vendor for projects table constraint if needed
        cur.execute("SELECT id FROM vendors LIMIT 1")
        vendor_row = cur.fetchone()
        v_id = vendor_row[0] if vendor_row else "V-001"

        # 1. Create a Project
        project_id = "PRJ-TEST-99"
        cur.execute(
            "INSERT OR IGNORE INTO projects(id, name, vendor_id, status) VALUES(?,?,?,?)",
            (project_id, "Enterprise Cloud Migration", v_id, "active"),
        )

        # 2. Create a Meeting with a Transcript
        meeting_id = "MTG-TEST-99"
        transcript = """
        Anil: We need a vendor to handle our multi-cloud migration from AWS to GCP.
        Priya: The budget is around $200k. We need high availability and zero downtime.
        James: Technical requirements include Kubernetes orchestration and Terraform for IaC.
        Anil: Timeline is 6 months starting June.
        Priya: Evaluation should be 40% cost, 60% expertise.
        """
        # Note: organizer_id P-001 exists from seed
        cur.execute(
            """
            INSERT OR IGNORE INTO meetings(id, title, organizer_id, project_id, transcript, status) 
            VALUES(?,?,?,?,?,?)
        """,
            (
                meeting_id,
                "Migration Kickoff",
                "P-001",
                project_id,
                transcript,
                "completed",
            ),
        )

        conn.commit()
    return project_id, meeting_id


def run_lifecycle_test():
    logger.info("=== STARTING PROJECT LIFECYCLE TOOL TEST ===")

    prj_id, mtg_id = setup_test_data()
    logger.info(f"Test Data Ready: Project={prj_id}, Meeting={mtg_id}")

    # 1. Generate RFP
    logger.info("\n--- Step 1: RFP Generation ---")
    rfp_msg = generate_rfp_from_meeting.invoke({"meeting_id": mtg_id})
    logger.info(rfp_msg)

    if "Error" in rfp_msg:
        return

    rfp_id = rfp_msg.split("'")[1]  # Extract ID from success message

    # 2. Generate Vendor Responses
    logger.info("\n--- Step 2: Vendor Response Generation ---")
    resp_msg = generate_mock_vendor_responses.invoke({"rfp_id": rfp_id})
    logger.info(resp_msg)

    # 3. Evaluate Responses
    logger.info("\n--- Step 3: Response Evaluation ---")
    eval_msg = evaluate_vendor_responses.invoke({"rfp_id": rfp_id})
    logger.info(eval_msg)

    # 4. Select Vendor (Mocking selection of first in list from evaluations)
    # For test purpose, we'll just pick a known vendor
    logger.info("\n--- Step 4: Vendor Selection ---")
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM vendors LIMIT 1")
        best_vendor = cur.fetchone()[0]

    select_msg = select_vendor_helper.invoke(
        {"project_id": prj_id, "vendor_id": best_vendor}
    )
    logger.info(select_msg)

    # 5. Generate SOW from Negotiation Meeting
    logger.info("\n--- Step 5: SOW Generation from Negotiation ---")
    # Simulate a negotiation meeting
    with get_db_connection() as conn:
        neg_mtg_id = "MTG-NEG-99"
        neg_transcript = """
        Vendor Representative: We can agree to the 6-month timeline.
        Anil: We expect 5 major milestones: 
        1. Infrastructure Set-up (10 days)
        2. Data Migration Phase 1 (30 days)
        3. Security Audit (45 days)
        4. Application Cut-over (60 days)
        5. Final Handover (90 days)
        Vendor: Payment will be 20% on start, 80% on final handover.
        """
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO meetings(id, title, organizer_id, project_id, transcript, status) 
            VALUES(?,?,?,?,?,?)
        """,
            (
                neg_mtg_id,
                "SOW Negotiation",
                "P-001",
                prj_id,
                neg_transcript,
                "completed",
            ),
        )
        conn.commit()

    sow_msg = generate_sow_from_meeting.invoke({"meeting_id": neg_mtg_id})
    logger.info(sow_msg)

    # 6. Simulate Status Updates
    logger.info("\n--- Step 6: Status Simulation ---")
    sim_msg = simulate_daily_status.invoke({"project_id": prj_id})
    logger.info(sim_msg)

    # 7. Compute Health
    logger.info("\n--- Step 7: Compute Project Health ---")
    health_report = compute_project_health.invoke({"project_id": prj_id})
    logger.info(health_report)

    logger.info("\n=== TEST COMPLETE ===")


if __name__ == "__main__":
    run_lifecycle_test()
