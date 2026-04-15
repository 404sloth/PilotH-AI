#!/usr/bin/env python3
"""
Orchestrator Integration Tests.

Tests orchestrator components:
  - Intent parsing and detection
  - Task decomposition
  - Agent routing
  - HITL integration
  - Feedback loops

Run: python3 tests/integration/test_orchestrator.py
"""

import sys
import time
from datetime import datetime
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
    print(f"  {BLUE}ORCHESTRATOR TEST SUMMARY{RESET}")
    print(f"{BLUE}{'=' * 70}{RESET}")
    print(f"  Total:  {total}")
    print(f"  {GREEN}Passed: {passed}{RESET}")
    print(f"  {RED}Failed: {failed}{RESET}")
    print(f"{BLUE}{'=' * 70}{RESET}\n")

    return failed == 0


# ────────────────────────────────────────────────────────────────────────────
# PHASE 1: Initialization
# ────────────────────────────────────────────────────────────────────────────

section("PHASE 1: Initialization")

try:
    from config.settings import Settings
    from integrations.data_warehouse.sqlite_client import init_db
    from llm.model_factory import get_llm

    init_db(seed=True)
    settings = Settings()
    llm = get_llm()

    check("Database initialized", True)
    check("Settings loaded", settings is not None)
    check("LLM ready", llm is not None, f"Provider: {type(llm).__name__}")

except Exception as e:
    check("Initialization failed", False, str(e))
    sys.exit(1)

# ────────────────────────────────────────────────────────────────────────────
# PHASE 2: Intent Parser
# ────────────────────────────────────────────────────────────────────────────

section("PHASE 2: Intent Parser")

try:
    from orchestrator.intent_parser import IntentParser

    parser = IntentParser(llm)

    # Test vendor-related queries
    vendor_queries = [
        "Find me the best cloud vendors",
        "I need database solutions",
        "Show me backup and DR vendors",
    ]

    for query in vendor_queries:
        intent = parser.parse(query)
        check(
            f"Parse intent: {query[:30]}...",
            intent.agent_name == "vendor_management",
            f"Intent: {intent.agent_name}",
        )

    # Test communication-related queries
    comm_queries = [
        "Schedule a meeting for tomorrow",
        "Summarize the quarterly review meeting",
        "Send a briefing to the team",
    ]

    for query in comm_queries:
        intent = parser.parse(query)
        check(
            f"Parse intent: {query[:30]}...",
            intent.agent_name in ["communication", "meetings_communication"],
            f"Intent: {intent.agent_name}",
        )

except Exception as e:
    check("Intent parser tests", False, str(e))

# ────────────────────────────────────────────────────────────────────────────
# PHASE 3: Task Decomposer
# ────────────────────────────────────────────────────────────────────────────

section("PHASE 3: Task Decomposer")

try:
    from orchestrator.task_decomposer import TaskDecomposer

    decomposer = TaskDecomposer(llm)

    # Complex query that might decompose into subtasks
    complex_query = "Find cloud vendors and schedule a meeting with top 3 candidates"

    tasks = decomposer.decompose(complex_query)

    check(
        "Decompose complex query",
        len(tasks) > 0,
        f"Tasks: {len(tasks)}",
    )

    # Simpler query (no decomposition needed)
    simple_query = "Find cloud hosting vendors"
    simple_tasks = decomposer.decompose(simple_query)

    check(
        "Handle simple query",
        len(simple_tasks) >= 1,
        f"Tasks: {len(simple_tasks)}",
    )

except Exception as e:
    check("Task decomposer tests", False, str(e))

# ────────────────────────────────────────────────────────────────────────────
# PHASE 4: Agent Router
# ────────────────────────────────────────────────────────────────────────────

section("PHASE 4: Agent Router")

try:
    from backend.services.agent_registry import AgentRegistry
    from orchestrator.agent_router import AgentRouter

    registry = AgentRegistry(settings)
    router = AgentRouter(registry)

    # Test routing to vendor agent
    vendor_intent_name = "vendor_management"
    vendor_agent = router.route(vendor_intent_name)

    check(
        "Route to vendor agent",
        vendor_agent is not None and vendor_agent.name == "vendor_management",
        f"Agent: {vendor_agent.name if vendor_agent else 'None'}",
    )

    # Test routing to communication agent
    comm_intent_name = "communication"
    comm_agent = router.route(comm_intent_name)

    check(
        "Route to communication agent",
        comm_agent is not None
        and comm_agent.name in ["communication", "meetings_communication"],
        f"Agent: {comm_agent.name if comm_agent else 'None'}",
    )

except Exception as e:
    check("Agent router tests", False, str(e))

# ────────────────────────────────────────────────────────────────────────────
# PHASE 5: Memory Manager
# ────────────────────────────────────────────────────────────────────────────

section("PHASE 5: Memory Manager")

try:
    from orchestrator.memory_manager import MemoryManager

    memory = MemoryManager()

    # Create session
    session_id = "test-session-" + datetime.now().strftime("%s")
    memory.create_session(session_id, {"user_id": "test-user"})

    check(
        "Create session",
        memory.get_session(session_id) is not None,
        f"Session: {session_id[:20]}...",
    )

    # Store context
    memory.set_context(session_id, "vendor_context", {"service": "cloud_hosting"})

    context = memory.get_context(session_id, "vendor_context")
    check(
        "Store and retrieve context",
        context is not None and context.get("service") == "cloud_hosting",
        "Context preserved",
    )

    # Update memory
    memory.update_session(session_id, {"step": 2, "status": "in_progress"})

    session = memory.get_session(session_id)
    check(
        "Update session state",
        session.get("status") == "in_progress",
        f"Status: {session.get('status')}",
    )

except Exception as e:
    check("Memory manager tests", False, str(e))

# ────────────────────────────────────────────────────────────────────────────
# PHASE 6: HITL Integration
# ────────────────────────────────────────────────────────────────────────────

section("PHASE 6: HITL (Human-in-the-Loop) Integration")

try:
    from human_loop.approval import ApprovalRequest
    from human_loop.manager import HITLManager

    hitl = HITLManager()

    # Create approval request
    approval_req = ApprovalRequest(
        request_id="test-req-001",
        agent_name="vendor_management",
        action="high_cost_vendor_selection",
        description="Select vendor costing $15,000/month",
        risk_level="high",
        data={
            "vendor_id": "V-001",
            "vendor_name": "Premium Cloud Corp",
            "monthly_cost": 15000,
            "fit_score": 92.5,
        },
    )

    # Submit for approval
    submitted = hitl.submit_for_approval(approval_req)

    check(
        "Submit approval request",
        submitted is not None and submitted.request_id == approval_req.request_id,
        f"Request ID: {submitted.request_id[:20] if submitted else 'None'}",
    )

    # Get pending approvals
    pending = hitl.get_pending_approvals()

    check(
        "Retrieve pending approvals",
        len(pending) > 0,
        f"Pending: {len(pending)}",
    )

    # Mock approval
    if pending:
        req_to_approve = pending[0]
        result = hitl.approve(req_to_approve.request_id, "Test approval")

        check(
            "Approve request",
            result is not None,
            "Approval processed",
        )

except Exception as e:
    check("HITL integration tests", False, str(e))

# ────────────────────────────────────────────────────────────────────────────
# PHASE 7: End-to-End Orchestration
# ────────────────────────────────────────────────────────────────────────────

section("PHASE 7: End-to-End Orchestration")

try:
    from orchestrator.controller import OrchestratorController

    controller = OrchestratorController(settings)

    # Test orchestration of vendor query
    vendor_query = "Find reliable cloud hosting vendors for our enterprise"

    response = controller.orchestrate(vendor_query)

    check(
        "Orchestrate vendor query",
        response is not None,
        f"Response type: {type(response).__name__}",
    )

    # Test orchestration of communication query
    comm_query = "Schedule a meeting with the vendor team for next Tuesday at 2pm"

    response = controller.orchestrate(comm_query)

    check(
        "Orchestrate communication query",
        response is not None,
        f"Response type: {type(response).__name__}",
    )

except Exception as e:
    check("End-to-end orchestration", False, str(e))

# ────────────────────────────────────────────────────────────────────────────
# PHASE 8: Feedback & Learning System
# ────────────────────────────────────────────────────────────────────────────

section("PHASE 8: Feedback & Learning System")

try:
    from human_loop.feedback import FeedbackCollector, FeedbackType

    feedback_system = FeedbackCollector()

    # Submit positive feedback
    positive_feedback = {
        "request_id": "test-req-001",
        "agent_name": "vendor_management",
        "feedback_type": FeedbackType.POSITIVE,
        "message": "Great vendor selection process",
        "rating": 5,
    }

    feedback_system.submit_feedback(positive_feedback)

    check(
        "Collect positive feedback",
        True,
        "Feedback submitted",
    )

    # Submit negative feedback
    negative_feedback = {
        "request_id": "test-req-002",
        "agent_name": "communication",
        "feedback_type": FeedbackType.NEGATIVE,
        "message": "Meeting scheduling took too long",
        "rating": 2,
    }

    feedback_system.submit_feedback(negative_feedback)

    check(
        "Collect negative feedback",
        True,
        "Feedback submitted",
    )

except Exception as e:
    check("Feedback system tests", False, str(e))

# ────────────────────────────────────────────────────────────────────────────
# PHASE 9: Error Handling Paths
# ────────────────────────────────────────────────────────────────────────────

section("PHASE 9: Error Handling Paths")

try:
    from orchestrator.fallback_handler import FallbackHandler

    fallback = FallbackHandler()

    # Test fallback for unknown agent
    result = fallback.handle_routing_failure("unknown_agent", "test query")

    check(
        "Handle routing failure",
        result is not None,
        "Fallback response provided",
    )

    # Test fallback for agent timeout
    result = fallback.handle_agent_timeout("vendor_management", "test query")

    check(
        "Handle agent timeout",
        result is not None,
        "Timeout response provided",
    )

    # Test fallback for LLM failure
    result = fallback.handle_llm_failure("vendor_management", "test query")

    check(
        "Handle LLM failure",
        result is not None,
        "LLM failure response provided",
    )

except Exception as e:
    check("Error handling paths", False, str(e))

# ────────────────────────────────────────────────────────────────────────────
# PHASE 10: Observability in Orchestration
# ────────────────────────────────────────────────────────────────────────────

section("PHASE 10: Observability in Orchestration")

try:
    from observability.logger import get_logger
    from observability.metrics import get_metrics
    from observability.tracing import get_tracer

    logger = get_logger("orchestrator_test")
    metrics = get_metrics()
    tracer = get_tracer("orchestrator")

    # Test logging from orchestration
    logger.info(
        "Orchestration started",
        agent="orchestrator",
        action="orchestrate",
        data={"query": "test query"},
    )

    check(
        "Orchestration logging",
        True,
        "Event logged",
    )

    # Test metrics from orchestration
    metrics.increment_counter("orchestration.requests")
    metrics.record_histogram("orchestration.duration_ms", 1250)

    report = metrics.get_metrics_report()

    check(
        "Orchestration metrics",
        "orchestration.requests" in report,
        f"Metrics: {len(report)}",
    )

    # Test tracing
    with tracer.trace_operation("orchestration_flow") as span:
        span.add_event("route_detected", {"agent": "vendor_management"})

    trace = tracer.export_trace()

    check(
        "Orchestration tracing",
        trace.get("trace_id") is not None,
        f"Trace ID: {trace.get('trace_id')[:8]}...",
    )

except Exception as e:
    check("Observability integration", False, str(e))

# ────────────────────────────────────────────────────────────────────────────
# PHASE 11: Workflow State Transitions
# ────────────────────────────────────────────────────────────────────────────

section("PHASE 11: Workflow State Transitions")

try:
    from orchestrator.workflow_engine import WorkflowEngine

    engine = WorkflowEngine()

    # Define test workflow
    workflow = {
        "name": "vendor_selection_workflow",
        "steps": [
            {"step": 1, "agent": "vendor_management", "action": "find_best"},
            {"step": 2, "agent": "communication", "action": "schedule"},
            {"step": 3, "agent": "vendor_management", "action": "evaluate"},
        ],
    }

    # Execute workflow
    session_id = "workflow-test-" + datetime.now().strftime("%s")
    result = engine.execute_workflow(workflow, session_id, {})

    check(
        "Workflow execution",
        result is not None,
        f"Workflow: {workflow['name']}",
    )

    # Check state transitions
    state = engine.get_workflow_state(session_id)

    check(
        "Workflow state tracking",
        state is not None,
        f"State: {type(state).__name__}",
    )

except Exception as e:
    check("Workflow state transitions", False, str(e))

# ────────────────────────────────────────────────────────────────────────────
# PHASE 12: Performance & Metrics
# ────────────────────────────────────────────────────────────────────────────

section("PHASE 12: Performance & Metrics")


try:
    from orchestrator.controller import OrchestratorController

    controller = OrchestratorController(settings)

    # Measure orchestration time
    start = time.time()

    response = controller.orchestrate("Find cloud vendors")

    duration = (time.time() - start) * 1000  # Convert to ms

    check(
        "Orchestration performance",
        duration < 10000,  # Should complete in 10 seconds
        f"Duration: {duration:.0f}ms",
    )

    # Check metrics
    metrics = get_metrics()
    report = metrics.get_metrics_report()

    check(
        "Metrics collection",
        len(report) > 0,
        f"Metrics tracked: {len(report)}",
    )

except Exception as e:
    check("Performance metrics", False, str(e))

# ────────────────────────────────────────────────────────────────────────────
# FINAL REPORT
# ────────────────────────────────────────────────────────────────────────────

success = report_results()
sys.exit(0 if success else 1)
