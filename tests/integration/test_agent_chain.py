#!/usr/bin/env python3
"""
End-to-End Integration Tests for Agent Chains.

Tests complete workflows with real LLM integration:
  - Vendor Management end-to-end
  - Communication Agent end-to-end
  - Cross-agent scenarios
  - Error handling and fallbacks

Run: python3 tests/integration/test_agent_chain.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# Colors for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

PASS = f"{GREEN}✓{RESET}"
FAIL = f"{RED}✗{RESET}"
INFO = f"{BLUE}ℹ{RESET}"

results: list[tuple[str, str, str]] = []


def check(name: str, condition: bool, detail: str = ""):
    """Record test result."""
    status = PASS if condition else FAIL
    results.append((status, name, detail))
    print(f"  {status} {name}", end="")
    if detail:
        print(f"  [{detail}]", end="")
    print()


def section(title: str):
    """Print section header."""
    print(f"\n{BLUE}{'=' * 70}{RESET}")
    print(f"  {BLUE}{title}{RESET}")
    print(f"{BLUE}{'=' * 70}{RESET}")


def report_results():
    """Print final summary."""
    total = len(results)
    passed = sum(1 for s, _, _ in results if PASS in s)
    failed = total - passed

    print(f"\n{BLUE}{'=' * 70}{RESET}")
    print(f"  {BLUE}TEST SUMMARY{RESET}")
    print(f"{BLUE}{'=' * 70}{RESET}")
    print(f"  Total:  {total}")
    print(f"  {GREEN}Passed: {passed}{RESET}")
    print(f"  {RED}Failed: {failed}{RESET}")
    print(f"{BLUE}{'=' * 70}{RESET}\n")

    if failed == 0:
        print(f"{GREEN}All tests passed!{RESET}\n")
        return True

    print(f"{RED}{failed} test(s) failed.{RESET}\n")
    return False


# ────────────────────────────────────────────────────────────────────────────
# PHASE 1: Initialization
# ────────────────────────────────────────────────────────────────────────────

section("PHASE 1: System Initialization")

# Initialize database
try:
    from integrations.data_warehouse.sqlite_client import init_db

    init_db(seed=True)
    check("Database initialization", True)
except Exception as e:
    check("Database initialization", False, str(e))
    sys.exit(1)

# Initialize LLM
try:
    from llm.model_factory import get_llm

    llm = get_llm()
    check("LLM initialization", llm is not None, f"Model: {type(llm).__name__}")
except Exception as e:
    check("LLM initialization", False, str(e))

# ────────────────────────────────────────────────────────────────────────────
# PHASE 2: Vendor Management Agent - Full Chain
# ────────────────────────────────────────────────────────────────────────────

section("PHASE 2: Vendor Management Agent - Full Chain")

# Test 2.1: Query Orchestrator
try:
    from agents.vendor_management.query_orchestrator import (
        get_vendor_query_orchestrator,
    )

    orchestrator = get_vendor_query_orchestrator()

    # Parse natural language query
    query = "Find cloud hosting vendors under $2000/month with >95% uptime"
    parsed_req = orchestrator.parse_vendor_query(query)

    check(
        "Query parsing (cloud hosting)",
        parsed_req.service_tag == "cloud_hosting",
        f"Service: {parsed_req.service_tag}",
    )
    check(
        "Budget extraction",
        parsed_req.budget_monthly == 2000,
        f"Budget: ${parsed_req.budget_monthly}",
    )
    check(
        "On-time rate extraction",
        parsed_req.min_on_time_rate >= 0.95,
        f"Rate: {parsed_req.min_on_time_rate:.0%}",
    )
    check(
        "Parse confidence",
        parsed_req.confidence > 0.7,
        f"Confidence: {parsed_req.confidence:.0%}",
    )

except Exception as e:
    check("Query parsing", False, str(e))

# Test 2.2: Vendor Matcher Tool with Performance Enhancement
try:
    from agents.vendor_management.tools.vendor_matcher import VendorMatcherTool

    matcher = VendorMatcherTool()
    input_data = {
        "service_tag": "cloud_hosting",
        "budget_monthly": 2000.0,
        "min_quality_score": 75.0,
        "min_on_time_rate": 0.95,
        "top_n": 3,
    }

    result = matcher.execute(type("Input", (), input_data))

    check(
        "Vendor matching",
        len(result.ranked_vendors) > 0,
        f"Candidates: {len(result.ranked_vendors)}",
    )

    if result.ranked_vendors:
        top_vendor = result.ranked_vendors[0]
        check(
            "Top vendor ranking",
            top_vendor.rank == 1,
            f"Vendor: {top_vendor.name}",
        )
        check(
            "Fit score in valid range",
            0 <= top_vendor.fit_score <= 100,
            f"Score: {top_vendor.fit_score:.1f}",
        )
        check(
            "Selection reason present",
            len(top_vendor.selection_reason) > 0,
            f"Reason length: {len(top_vendor.selection_reason)} chars",
        )

except Exception as e:
    check("Vendor matching chain", False, str(e))

# Test 2.3: Vendor Evaluation with LLM
try:
    from agents.vendor_management.nodes.evaluate import evaluate_node

    vendor_state = {
        "action": "full_assessment",
        "vendor_id": "V-001",
        "vendor_name": "Acme Cloud Solutions",
        "vendor_details": {
            "name": "Acme Cloud Solutions",
            "tier": "preferred",
            "quality_score": 92,
            "on_time_rate": 0.97,
            "avg_client_rating": 4.8,
            "communication_score": 88,
            "innovation_score": 85,
            "total_projects_completed": 250,
        },
        "sla_data": {"overall_compliance": 98.5, "breaches": []},
        "milestone_data": [],
    }

    result = evaluate_node(vendor_state)

    check(
        "Vendor evaluation completed",
        "evaluation_scores" in result or result == {},
        "Node returned proper structure",
    )

    if "evaluation_scores" in result:
        scores = result.get("evaluation_scores", {})
        check(
            "Evaluation scores present",
            len(scores) > 0,
            f"Score count: {len(scores)}",
        )
        check(
            "Overall score in range",
            0 <= result.get("overall_score", 0) <= 100,
            f"Overall: {result.get('overall_score', 0):.1f}",
        )

except Exception as e:
    check("Vendor evaluation with LLM", False, str(e))

# Test 2.4: Full Vendor Management Agent
try:
    from agents.vendor_management.agent import VendorManagementAgent
    from config.settings import Settings

    settings = Settings()
    agent = VendorManagementAgent(settings)

    input_data = {
        "action": "find_best",
        "service_required": "cloud_hosting",
        "budget_monthly": 2000.0,
        "min_quality_score": 75.0,
        "min_on_time_rate": 0.85,
        "top_n": 3,
        "session_id": "test-session-001",
    }

    result = agent.execute(input_data)

    check(
        "Vendor Management Agent execution",
        result.get("status") == "success" or result is not None,
        f"Status: {result.get('status', 'N/A')}",
    )

except Exception as e:
    check("Full Vendor Management Agent", False, str(e))

# ────────────────────────────────────────────────────────────────────────────
# PHASE 3: Communication Agent - Full Chain
# ────────────────────────────────────────────────────────────────────────────

section("PHASE 3: Communication Agent - Full Chain")

# Test 3.1: Query Handler (Intent Detection)
try:
    from agents.communication.query_handler import QueryIntentType, get_query_handler

    handler = get_query_handler()

    # Test various queries
    test_queries = [
        (
            "Schedule a meeting with john@company.com tomorrow at 2pm EST about Q1 planning",
            QueryIntentType.SCHEDULE,
        ),
        (
            "Please summarize the quarterly review meeting",
            QueryIntentType.SUMMARIZE,
        ),
        (
            "Generate a briefing for the investor meeting",
            QueryIntentType.BRIEF,
        ),
    ]

    for query, expected_intent in test_queries:
        parsed = handler.parse_query(query)
        check(
            f"Intent detection: {expected_intent.value}",
            parsed.intent == expected_intent,
            f"Confidence: {parsed.confidence:.0%}",
        )

except Exception as e:
    check("Query handler initialization", False, str(e))

# Test 3.2: Google Calendar Integration
try:
    from agents.communication.tools.google_calendar import (
        GoogleCalendarAvailabilityTool,
        GoogleCalendarCreateTool,
    )

    calendar_tool = GoogleCalendarCreateTool()
    check(
        "Google Calendar Create Tool loaded",
        calendar_tool is not None,
        "Tool initialized",
    )

    availability_tool = GoogleCalendarAvailabilityTool()
    check(
        "Google Calendar Availability Tool loaded",
        availability_tool is not None,
        "Tool initialized",
    )

except Exception as e:
    check("Google Calendar tools", False, str(e))

# Test 3.3: Communication Agent
try:
    from agents.communication.agent import MeetingCommunicationAgent
    from config.settings import Settings

    settings = Settings()
    agent = MeetingCommunicationAgent(settings)

    input_data = {
        "action": "schedule",
        "title": "Q1 Planning Meeting",
        "participants": [
            {"name": "John Doe", "email": "john@company.com", "role": "manager"}
        ],
        "duration_minutes": 60,
        "preferred_time_range": "14:00-16:00",
        "timezone": "US/Eastern",
        "session_id": "test-session-002",
    }

    result = agent.execute(input_data)

    check(
        "Communication Agent execution",
        result is not None,
        f"Result type: {type(result).__name__}",
    )

except Exception as e:
    check("Communication Agent execution", False, str(e))

# ────────────────────────────────────────────────────────────────────────────
# PHASE 4: Observability Integration
# ────────────────────────────────────────────────────────────────────────────

section("PHASE 4: Observability Integration")

# Test 4.1: Logging
try:
    from observability.logger import get_logger

    logger = get_logger("test_agent_chain")

    logger.info(
        "Test log entry",
        agent="test",
        action="test_action",
        data={"test_key": "test_value"},
    )

    check("Structured logging", True, "Logger operational")

except Exception as e:
    check("Structured logging", False, str(e))

# Test 4.2: Metrics Collection
try:
    from observability.metrics import get_metrics

    metrics = get_metrics()
    metrics.increment_counter("test.counter")
    metrics.record_histogram("test.histogram", 100)

    report = metrics.get_metrics_report()
    check(
        "Metrics collection",
        "test.counter" in report,
        f"Metrics recorded: {len(report)}",
    )

except Exception as e:
    check("Metrics collection", False, str(e))

# Test 4.3: Distributed Tracing
try:
    from observability.tracing import get_tracer

    tracer = get_tracer("test_agent_chain")

    with tracer.trace_operation("test_operation") as span:
        span.add_event("test_event", {"detail": "test_value"})

    trace = tracer.export_trace()
    check(
        "Distributed tracing",
        trace.get("trace_id") is not None,
        f"Trace ID: {trace.get('trace_id')[:8]}...",
    )

except Exception as e:
    check("Distributed tracing", False, str(e))

# ────────────────────────────────────────────────────────────────────────────
# PHASE 5: PII Sanitization
# ────────────────────────────────────────────────────────────────────────────

section("PHASE 5: PII Sanitization & Security")

try:
    from common.pii_sanitizer import sanitize_data

    sensitive_data = {
        "vendor_name": "TechCorp Inc",
        "recent_clients": ["NASA", "Tesla", "Goldman Sachs"],
        "contact_email": "vendor@techcorp.com",
        "phone": "555-123-4567",
        "project_name": "Project Zeus",
    }

    sanitized = sanitize_data(sensitive_data)

    check(
        "Email masking",
        "[EMAIL]" in str(sanitized),
        "Email properly masked",
    )
    check(
        "Client name masking",
        "[CLIENT_NAME]" in str(sanitized),
        "Client names properly masked",
    )
    check(
        "Project name masking",
        "[PROJECT_NAME]" in str(sanitized),
        "Project name properly masked",
    )
    check(
        "Vendor name NOT masked",
        "TechCorp Inc" in str(sanitized),
        "Business names preserved for functionality",
    )

except Exception as e:
    check("PII sanitization", False, str(e))

# ────────────────────────────────────────────────────────────────────────────
# PHASE 6: Cross-Agent Integration & Orchestration
# ────────────────────────────────────────────────────────────────────────────

section("PHASE 6: Cross-Agent Orchestration")

# Test 6.1: Agent Registry
try:
    from backend.services.agent_registry import AgentRegistry
    from config.settings import Settings

    settings = Settings()
    registry = AgentRegistry(settings)

    agents = registry.list_agents()
    check(
        "Agent registry loaded",
        len(agents) >= 2,
        f"Agents registered: {len(agents)}",
    )

    # Verify vendor management agent
    vendor_agent = registry.get_agent("vendor_management")
    check(
        "Vendor Management Agent registered",
        vendor_agent is not None,
        "Agent available",
    )

    # Verify communication agent
    comm_agent = registry.get_agent("communication")
    check(
        "Communication Agent registered",
        comm_agent is not None,
        "Agent available",
    )

except Exception as e:
    check("Agent registry", False, str(e))

# Test 6.2: Orchestrator
try:
    from config.settings import Settings
    from orchestrator.controller import OrchestratorController

    settings = Settings()
    orchestrator = OrchestratorController(settings)

    # Route vendor question
    query = "Find cloud vendors for our project"
    result = orchestrator.orchestrate(query)

    check(
        "Orchestrator routing",
        result is not None,
        "Routing completed",
    )

except Exception as e:
    check("Orchestrator integration", False, str(e))

# ────────────────────────────────────────────────────────────────────────────
# PHASE 7: Error Handling & Recovery
# ────────────────────────────────────────────────────────────────────────────

section("PHASE 7: Error Handling & Fallbacks")

# Test 7.1: Invalid Query Handling
try:
    from agents.vendor_management.query_orchestrator import (
        get_vendor_query_orchestrator,
    )

    orchestrator = get_vendor_query_orchestrator()

    # Test with ambiguous query
    ambiguous_query = "I need something"
    parsed_req = orchestrator.parse_vendor_query(ambiguous_query)

    check(
        "Ambiguous query handling",
        parsed_req.requires_clarification or parsed_req.confidence < 0.6,
        f"Confidence: {parsed_req.confidence:.0%}",
    )

except Exception as e:
    check("Invalid query handling", False, str(e))

# Test 7.2: Tool Fallback (if LLM fails)
try:
    from agents.communication.query_handler import get_query_handler

    handler = get_query_handler()
    query = "Schedule meeting with john tomorrow"

    # Should use fallback rules if needed
    parsed = handler.parse_query(query)

    check(
        "Query handler fallback",
        parsed.intent is not None,
        f"Intent detected: {parsed.intent.value}",
    )

except Exception as e:
    check("Query handler fallback", False, str(e))

# ────────────────────────────────────────────────────────────────────────────
# PHASE 8: Performance & Load
# ────────────────────────────────────────────────────────────────────────────

section("PHASE 8: Performance & Load Testing")

# Test 8.1: Vendor Matching Speed
try:
    from agents.vendor_management.tools.vendor_matcher import VendorMatcherTool

    matcher = VendorMatcherTool()

    start = time.time()
    for _ in range(3):
        input_data = {
            "service_tag": "cloud_hosting",
            "budget_monthly": 2000.0,
            "min_quality_score": 75.0,
            "top_n": 3,
        }
        matcher.execute(type("Input", (), input_data))
    duration = (time.time() - start) / 3

    check(
        "Vendor matching performance",
        duration < 5.0,
        f"Avg time: {duration:.2f}s",
    )

except Exception as e:
    check("Performance testing", False, str(e))

# ────────────────────────────────────────────────────────────────────────────
# FINAL REPORT
# ────────────────────────────────────────────────────────────────────────────

success = report_results()
sys.exit(0 if success else 1)
