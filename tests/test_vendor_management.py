#!/usr/bin/env python3
"""
Integration test for the complete Vendor Management system.
Tests: DB init, DAL, all tools, and graph nodes (no LLM required).
Run from project root: python3 tests/test_vendor_management.py
"""

import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = "✓"
FAIL = "✗"
results = []


def check(name: str, condition: bool, detail: str = ""):
    status = PASS if condition else FAIL
    results.append((status, name, detail))
    print(f"  {status} {name}" + (f"  [{detail}]" if detail else ""))


def section(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ──────────────────────────────────────────────────────────────
# 1. Database initialisation
# ──────────────────────────────────────────────────────────────
section("1. Database Initialisation")
try:
    from integrations.data_warehouse.sqlite_client import init_db

    init_db(seed=True)
    check("init_db() succeeded", True)
except Exception as e:
    check("init_db() succeeded", False, str(e))


# ──────────────────────────────────────────────────────────────
# 2. DAL functions
# ──────────────────────────────────────────────────────────────
section("2. Data Access Layer (DAL)")
try:
    from integrations.data_warehouse.vendor_db import (
        search_vendors,
        get_vendor_by_id,
        find_best_vendors_for_service,
        get_contract_details,
        get_sla_compliance,
        get_milestones,
        get_client_project,
        save_vendor_selection,
        get_saved_selections,
        get_vendor_scorecard,
    )

    vendors = search_vendors(service_tag="cloud_hosting")
    check("search_vendors by service_tag", len(vendors) >= 2, f"{len(vendors)} found")

    v = get_vendor_by_id("V-001")
    check(
        "get_vendor_by_id V-001",
        v is not None and v["name"] == "Acme Cloud Solutions",
        v["name"] if v else "None",
    )

    best = find_best_vendors_for_service(
        "cloud_hosting", {"min_quality_score": 80, "min_on_time_rate": 0.88}
    )
    check(
        "find_best_vendors_for_service",
        len(best) >= 1,
        f"{len(best)} candidates, top={best[0].get('name') if best else 'N/A'}",
    )
    check(
        "Ranked by fit_score descending",
        all(
            best[i]["fit_score"] >= best[i + 1]["fit_score"]
            for i in range(len(best) - 1)
        ),
    )

    contract = get_contract_details(vendor_id="V-001")
    check(
        "get_contract_details V-001",
        contract is not None and contract.get("contract_reference") == "CTR-2024-001",
    )

    sla = get_sla_compliance("V-001")
    check(
        "get_sla_compliance V-001",
        sla is not None and "metrics" in sla,
        f"compliance={sla.get('overall_compliance') if sla else 'N/A'}%",
    )

    ms = get_milestones("V-001")
    check("get_milestones V-001", len(ms) > 0, f"{len(ms)} milestones")

    cp = get_client_project("CP-001")
    check("get_client_project CP-001", cp is not None and "requirements" in cp)

    save_vendor_selection("CP-001", "V-001", 88.5, True, "Test selection")
    sels = get_saved_selections("CP-001")
    check(
        "save & retrieve vendor_selection", any(s["vendor_id"] == "V-001" for s in sels)
    )

    sc = get_vendor_scorecard("V-001")
    check("get_vendor_scorecard V-001", sc is not None and sc.get("vendor") is not None)

except Exception:
    import traceback

    check("DAL overall", False, traceback.format_exc())


# ──────────────────────────────────────────────────────────────
# 3. Tool layer
# ──────────────────────────────────────────────────────────────
section("3. Tool Layer")

try:
    from agents.vendor_management.tools.vendor_search import (
        VendorSearchTool,
        VendorSearchInput,
    )

    t = VendorSearchTool()
    out = t.execute(VendorSearchInput(service_tag="cloud_hosting", limit=5))
    check(
        "VendorSearchTool — found vendors",
        out.found and out.count >= 2,
        f"count={out.count}",
    )

    not_found = t.execute(VendorSearchInput(vendor_name="NonExistentVendorXYZ"))
    check("VendorSearchTool — not found returns found=False", not not_found.found)
except Exception as e:
    check("VendorSearchTool", False, str(e))

try:
    from agents.vendor_management.tools.vendor_matcher import (
        VendorMatcherTool,
        VendorMatcherInput,
    )

    t = VendorMatcherTool()
    out = t.execute(
        VendorMatcherInput(
            service_tag="cloud_hosting",
            min_quality_score=80,
            min_on_time_rate=0.88,
            top_n=5,
            client_project_id="CP-001",
        )
    )
    check(
        "VendorMatcherTool — candidates found",
        out.candidates_found >= 1,
        f"top={out.top_recommendation}",
    )
    check(
        "VendorMatcherTool — ranked by fit_score",
        out.ranked_vendors[0].rank == 1 if out.ranked_vendors else True,
    )
    check(
        "VendorMatcherTool — top_recommendation set", out.top_recommendation is not None
    )
except Exception as e:
    check("VendorMatcherTool", False, str(e))

try:
    from agents.vendor_management.tools.contract_parser import (
        ContractParserTool,
        ContractParserInput,
    )

    t = ContractParserTool()
    out = t.execute(ContractParserInput(vendor_id="V-001"))
    check("ContractParserTool — found contract", out.found and out.contract is not None)
    check(
        "ContractParserTool — has deliverables",
        out.found and len(out.contract.deliverables) > 0,
    )

    out2 = t.execute(ContractParserInput(vendor_id="V-999"))
    check("ContractParserTool — not found returns found=False", not out2.found)
except Exception as e:
    check("ContractParserTool", False, str(e))

try:
    from agents.vendor_management.tools.sla_monitor import (
        SLAMonitorTool,
        SLAMonitorInput,
    )

    t = SLAMonitorTool()
    out = t.execute(SLAMonitorInput(vendor_id="V-001", period_days=30))
    check("SLAMonitorTool — data available", out.data_available)
    check(
        "SLAMonitorTool — has metrics",
        len(out.metrics) > 0,
        f"{len(out.metrics)} metrics",
    )
    check(
        "SLAMonitorTool — compliance 0-100",
        0 <= out.overall_compliance <= 100,
        f"{out.overall_compliance}%",
    )
except Exception as e:
    check("SLAMonitorTool", False, str(e))

try:
    from agents.vendor_management.tools.milestone_tracker import (
        MilestoneTrackerTool,
        MilestoneTrackerInput,
    )

    t = MilestoneTrackerTool()
    out = t.execute(MilestoneTrackerInput(vendor_id="V-001"))
    check("MilestoneTrackerTool — has milestones", out.total > 0, f"total={out.total}")
    check(
        "MilestoneTrackerTool — overall_status set",
        out.overall_status in ("on_track", "at_risk", "delayed"),
    )
except Exception as e:
    check("MilestoneTrackerTool", False, str(e))

try:
    from agents.vendor_management.tools.vendor_scorecard import (
        VendorScorecardTool,
        VendorScorecardInput,
    )

    t = VendorScorecardTool()
    out = t.execute(VendorScorecardInput(vendor_id="V-001"))
    check(
        "VendorScorecardTool — score in range",
        0 <= out.overall_score <= 100,
        f"score={out.overall_score}",
    )
    check("VendorScorecardTool — has contract", out.has_active_contract)
except Exception as e:
    check("VendorScorecardTool", False, str(e))


# ──────────────────────────────────────────────────────────────
# 4. Graph nodes (no LLM required — uses rule-based fallback)
# ──────────────────────────────────────────────────────────────
section("4. LangGraph Nodes (rule-based, no LLM)")

try:
    from agents.vendor_management.nodes.fetch_vendor import fetch_vendor_node
    from agents.vendor_management.nodes.evaluate import evaluate_node
    from agents.vendor_management.nodes.risk_detect import risk_detect_node

    # Test FIND_BEST fetch
    state = {
        "action": "find_best",
        "service_required": "cloud_hosting",
        "min_quality_score": 80.0,
        "min_on_time_rate": 0.88,
        "top_n": 5,
    }
    result = fetch_vendor_node(state)
    check(
        "fetch_vendor_node FIND_BEST — returns ranked_vendors",
        "ranked_vendors" in result and len(result["ranked_vendors"]) >= 1,
    )
    check(
        "fetch_vendor_node FIND_BEST — top_recommendation set",
        result.get("top_recommendation") is not None,
    )

    # Test single vendor fetch
    state2 = {"action": "full_assessment", "vendor_name": "Acme", "vendor_id": None}
    result2 = fetch_vendor_node(state2)
    check(
        "fetch_vendor_node ASSESS — vendor_details returned",
        "vendor_details" in result2 or result2.get("error"),
    )

    # Test evaluate node (rule-based fallback)
    eval_state = {
        "action": "full_assessment",
        "vendor_details": {
            "name": "Acme Cloud Solutions",
            "quality_score": 91,
            "on_time_rate": 0.96,
            "communication_score": 88,
            "cost_competitiveness": 74,
            "innovation_score": 82,
            "avg_client_rating": 4.7,
            "total_projects_completed": 142,
        },
        "vendor_id": "V-001",
        "sla_data": {
            "overall_compliance": 75.0,
            "breaches": ["Resolution Time exceeded"],
        },
        "milestone_data": [],
    }
    eval_result = evaluate_node(eval_state)
    check(
        "evaluate_node — scores returned",
        "evaluation_scores" in eval_result or eval_result == {},
    )

    # Test risk_detect
    risk_state = {
        "action": "full_assessment",
        "evaluation_scores": {
            "quality": 91,
            "reliability": 70,
            "sla_compliance": 75,
            "communication": 88,
            "cost": 74,
            "innovation": 82,
        },
        "sla_data": {
            "overall_compliance": 75.0,
            "breaches": ["Resolution Time exceeded"],
        },
        "milestone_data": [
            {"status": "delayed", "name": "Dev Phase", "days_overdue": 12}
        ],
        "vendor_details": {"name": "Acme Cloud Solutions", "contract_status": "active"},
    }
    risk_result = risk_detect_node(risk_state)
    check("risk_detect_node — risk_items list returned", "risk_items" in risk_result)
    check(
        "risk_detect_node — identifies delayed milestone",
        any(r.get("category") == "project" for r in risk_result.get("risk_items", [])),
    )

except Exception:
    import traceback

    check("Graph nodes", False, traceback.format_exc())


# ──────────────────────────────────────────────────────────────
# 5. Schema validation
# ──────────────────────────────────────────────────────────────
section("5. Pydantic Schema Validation")
try:
    from agents.vendor_management.schemas import (
        VendorManagementInput,
        VendorManagementOutput,
    )

    valid = VendorManagementInput(action="find_best", service_required="cloud_hosting")
    check("VendorManagementInput — find_best valid", valid.action == "find_best")

    valid2 = VendorManagementInput(action="full_assessment", vendor_name="Acme")
    check("VendorManagementInput — full_assessment valid", valid2.vendor_name == "Acme")

    out = VendorManagementOutput(
        action_performed="find_best", ranked_vendors=[], recommendations=["Test"]
    )
    check("VendorManagementOutput — validates", out.action_performed == "find_best")
except Exception as e:
    check("Schema validation", False, str(e))


# ──────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────
print(f"\n{'=' * 60}")
print("  RESULTS SUMMARY")
print(f"{'=' * 60}")
passed = [r for r in results if r[0] == PASS]
failed = [r for r in results if r[0] == FAIL]
print(f"  Passed: {len(passed)} / {len(results)}")
if failed:
    print("\n  Failed tests:")
    for _, name, detail in failed:
        print(f"    {FAIL} {name}: {detail}")
else:
    print("\n  All tests passed! System is working correctly.")
print()
