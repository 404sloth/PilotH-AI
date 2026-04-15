# Integration Guide - Vendor & Communication Agent Upgrades

This guide shows how to integrate the new components into the existing agent infrastructure.

---

## Table of Contents

1. [Vendor Management Integration](#vendor-management-integration)
2. [Communication Agent Integration](#communication-agent-integration)
3. [Observability Wiring](#observability-wiring)
4. [Testing & Validation](#testing--validation)

---

## Vendor Management Integration

### Step 1: Update Execute Method to Record Metrics

**File**: `agents/vendor_management/agent.py`

```python
from observability.metrics import get_metrics, MetricsTracker
from observability.tracing import get_tracer
import time

class VendorManagementAgent(BaseAgent):
    def execute(self, input_data: VendorManagementInput) -> VendorManagementOutput:
        """Execute vendor management workflow with metrics & tracing."""
        tracer = get_tracer("vendor_management")
        metrics = get_metrics()
        start_time = time.time()

        with tracer.trace_operation(
            "vendor_management_execute",
            attributes={
                "action": input_data.action,
                "vendor_id": input_data.vendor_id,
            }
        ) as span:
            try:
                # Existing validation and setup
                state = {
                    "action": input_data.action,
                    "vendor_id": input_data.vendor_id,
                    "vendor_name": input_data.vendor_name,
                    "service_required": input_data.service_required,
                    "budget_monthly": input_data.budget_monthly,
                    "min_quality_score": input_data.min_quality_score,
                    "min_on_time_rate": input_data.min_on_time_rate,
                    "required_tier": input_data.required_tier,
                    "country": input_data.country,
                    "client_project_id": input_data.client_project_id,
                    "top_n": input_data.top_n,
                }

                # Get and invoke subgraph
                graph = self.get_subgraph()
                config = {"configurable": {"thread_id": input_data.session_id}}
                result = graph.invoke(state, config)

                duration_ms = (time.time() - start_time) * 1000

                # Record metrics
                metrics.record_histogram(
                    "vendor_management.duration_ms",
                    duration_ms,
                    attributes={"action": input_data.action},
                )
                metrics.increment_counter(
                    "vendor_management.success",
                    attributes={"action": input_data.action},
                )

                span.add_event(
                    "execution_complete",
                    {"duration_ms": duration_ms},
                )

                # Build output
                output = VendorManagementOutput(
                    action_performed=input_data.action,
                    status="success",
                    result=result.get("selected_vendors", []),
                    summary=result.get("summary", ""),
                )

                return output

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                
                # Record failure metrics
                metrics.increment_counter(
                    "vendor_management.failure",
                    attributes={"action": input_data.action},
                )
                
                span.add_event(
                    "execution_failed",
                    {"error": str(e), "duration_ms": duration_ms},
                )
                
                raise
```

### Step 2: Use Query Orchestrator in Agent

**File**: `agents/vendor_management/agent.py`

```python
from agents.vendor_management.query_orchestrator import get_vendor_query_orchestrator

class VendorManagementAgent(BaseAgent):
    def execute(self, input_data: VendorManagementInput) -> VendorManagementOutput:
        # If input_data.raw_query is provided, parse it
        if hasattr(input_data, 'raw_query') and input_data.raw_query:
            orchestrator = get_vendor_query_orchestrator()
            parsed_req = orchestrator.parse_vendor_query(input_data.raw_query)
            
            if parsed_req.requires_clarification:
                return VendorManagementOutput(
                    action_performed="query_parse",
                    status="clarification_needed",
                    result={},
                    summary=orchestrator.generate_clarification_request(parsed_req),
                )
            
            # Update state with parsed requirements
            state.update(parsed_req.to_matcher_input())
        
        # Rest of execute method...
```

### Step 3: Wire Vendor Evaluation with Sanitization

**File**: `agents/vendor_management/graph.py`

```python
# Already done in evaluate.py, but ensure graph uses updated node:

from agents.vendor_management.nodes.evaluate import evaluate_node

def build_vendor_graph():
    """Build the vendor management graph with updated nodes."""
    graph = StateGraph(VendorState)
    
    # Existing nodes...
    graph.add_node("fetch_vendor", fetch_vendor_node)
    
    # Updated evaluate node (already includes sanitization, logging, metrics, tracing)
    graph.add_node("evaluate", evaluate_node)
    
    graph.add_node("risk_detect", risk_detect_node)
    graph.add_node("summarize", summarize_node)
    
    # Routing...
    graph.add_conditional_edges(
        "fetch_vendor",
        route_after_fetch,
        {
            "FIND_BEST": "summarize",
            "EVALUATE": "evaluate",
        }
    )
    
    return graph.compile()
```

---

## Communication Agent Integration

### Step 1: Update Communication Agent to Use Query Handler

**File**: `agents/communication/agent.py`

```python
from agents.communication.query_handler import (
    get_query_handler,
    QueryIntentType,
)
from observability.metrics import get_metrics
from observability.tracing import get_tracer
import time

class MeetingCommunicationAgent(BaseAgent):
    def execute(self, input_data: MeetingRequestInput) -> MeetingAgentOutput:
        """Execute meeting communication workflow with query routing."""
        tracer = get_tracer("communication")
        metrics = get_metrics()
        start_time = time.time()

        with tracer.trace_operation(
            "communication_execute",
            attributes={
                "action": input_data.action,
            }
        ) as span:
            try:
                # Parse intent if natural language query provided
                handler = get_query_handler()
                parsed_intent = handler.parse_query(input_data.query)
                
                if parsed_intent.requires_clarification:
                    return MeetingAgentOutput(
                        action_performed="query_parse",
                        status="clarification_needed",
                        summary=handler.handle_requires_clarification(parsed_intent),
                    )
                
                # Route to appropriate tools based on intent
                result = self._route_by_intent(parsed_intent)
                
                duration_ms = (time.time() - start_time) * 1000
                
                # Record metrics
                metrics.record_histogram(
                    "communication.duration_ms",
                    duration_ms,
                    attributes={"intent": parsed_intent.intent.value},
                )
                metrics.increment_counter(
                    "communication.success",
                    attributes={"intent": parsed_intent.intent.value},
                )
                
                return MeetingAgentOutput(
                    action_performed=parsed_intent.intent.value,
                    status="success",
                    summary=result,
                )
                
            except Exception as e:
                metrics.increment_counter(
                    "communication.failure",
                )
                raise
    
    def _route_by_intent(self, parsed_intent) -> str:
        """Route execution based on detected intent."""
        intent = parsed_intent.intent
        params = parsed_intent.parameters
        
        if intent == QueryIntentType.SCHEDULE:
            return self._handle_schedule(params)
        elif intent == QueryIntentType.SUMMARIZE:
            return self._handle_summarize(params)
        elif intent == QueryIntentType.BRIEF:
            return self._handle_briefing(params)
        elif intent == QueryIntentType.AGENDA:
            return self._handle_agenda(params)
        elif intent == QueryIntentType.NOTIFY:
            return self._handle_notify(params)
        elif intent == QueryIntentType.RESOLVE_CONFLICT:
            return self._handle_conflict_resolution(params)
        elif intent == QueryIntentType.TRACK_ACTIONS:
            return self._handle_action_tracking(params)
        else:
            return "Could not determine action from query."
    
    def _handle_schedule(self, params: Dict) -> str:
        """Handle meeting scheduling intent."""
        # Use GoogleCalendarCreateTool with params
        pass
    
    # ... other intent handlers
```

---

## Observability Wiring

### Step 1: Initialize Tracing in Main App

**File**: `backend/api/main.py`

```python
from observability.tracing import init_langsmith_tracing, get_tracer
from observability.logger import get_logger
from observability.metrics import get_metrics

@app.on_event("startup")
async def startup_tracing():
    """Initialize tracing system."""
    # Initialize LangSmith if configured
    langsmith_ok = init_langsmith_tracing()
    
    if langsmith_ok:
        logger.info("✓ LangSmith tracing initialized")
    else:
        logger.info("ℹ LangSmith not configured, using local tracing")
    
    # Get tracer instance to verify it works
    tracer = get_tracer()
    logger.info(f"✓ Distributed tracer ready: {tracer.service_name}")
```

### Step 2: Middleware for Request Tracing

**File**: `backend/api/middleware.py`

```python
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from observability.logger import get_logger

logger = get_logger("api.middleware")

class RequestTracingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        """Add correlation ID and trace all requests."""
        # Generate or extract correlation ID
        correlation_id = request.headers.get(
            "X-Correlation-ID",
            str(uuid.uuid4())
        )
        
        # Add to response headers
        request.state.correlation_id = correlation_id
        
        # Log request
        logger.info(
            f"{request.method} {request.url.path}",
            agent="api",
            action="request_received",
            data={
                "method": request.method,
                "path": request.url.path,
                "correlation_id": correlation_id,
            },
        )
        
        # Process request
        response = await call_next(request)
        
        # Log response
        logger.info(
            f"{request.method} {request.url.path} - {response.status_code}",
            agent="api",
            action="request_complete",
            data={
                "status_code": response.status_code,
                "correlation_id": correlation_id,
            },
        )
        
        response.headers["X-Correlation-ID"] = correlation_id
        return response

# Register middleware in main.py
app.add_middleware(RequestTracingMiddleware)
```

### Step 3: Metrics Endpoint

**File**: `backend/api/routes/metrics.py`

```python
from fastapi import APIRouter
from observability.metrics import get_metrics

router = APIRouter(prefix="/metrics", tags=["observability"])

@router.get("/summary")
async def get_metrics_summary():
    """Get metrics summary."""
    metrics = get_metrics()
    return metrics.get_metrics_report()

@router.get("/vendors")
async def get_vendor_metrics():
    """Get vendor-specific metrics."""
    metrics = get_metrics()
    report = metrics.get_metrics_report()
    
    return {
        "vendor_matching": {
            "total_matches": report.get("vendor_matching.success", 0),
            "avg_candidates": report.get("vendor_matching.candidates", 0),
        },
        "vendor_evaluation": {
            "total_evaluations": report.get("vendor_evaluation.success", 0),
            "avg_duration_ms": report.get("vendor_evaluation.duration_ms", 0),
        },
    }
```

### Step 4: Tracing Endpoint

**File**: `backend/api/routes/tracing.py`

```python
from fastapi import APIRouter
from observability.tracing import export_all_traces, get_trace_summary

router = APIRouter(prefix="/traces", tags=["observability"])

@router.get("/summary")
async def get_trace_summary_endpoint():
    """Get current trace summary."""
    return get_trace_summary()

@router.get("/export")
async def export_traces():
    """Export all recorded traces."""
    return {"traces": export_all_traces()}
```

---

## Testing & Validation

### Test 1: Vendor Matching with Historical Performance

```python
# test_vendor_matching_enhanced.py

from agents.vendor_management.tools.vendor_matcher import VendorMatcherTool
from agents.vendor_management.query_orchestrator import get_vendor_query_orchestrator

def test_vendor_matching_with_performance():
    """Test vendor matching with historical performance integration."""
    orchestrator = get_vendor_query_orchestrator()
    
    # Parse natural language query
    query = "Find cloud hosting vendors under $2k/month with >95% uptime"
    parsed_req = orchestrator.parse_vendor_query(query)
    
    assert parsed_req.service_tag == "cloud_hosting"
    assert parsed_req.budget_monthly == 2000
    assert parsed_req.min_on_time_rate == 0.95
    assert parsed_req.confidence > 0.8
    
    # Execute vendor matching
    matcher = VendorMatcherTool()
    result = matcher.execute(parsed_req.to_matcher_input())
    
    # Verify results include enhanced scoring
    assert len(result.ranked_vendors) > 0
    assert all(hasattr(v, 'fit_score') for v in result.ranked_vendors)
    assert all(hasattr(v, 'selection_reason') for v in result.ranked_vendors)
    
    print(f"✓ Top vendor: {result.ranked_vendors[0].name}")
    print(f"  Fit score: {result.ranked_vendors[0].fit_score}")
    print(f"  Reason: {result.ranked_vendors[0].selection_reason}")
```

### Test 2: Communication Query Parsing

```python
# test_communication_queries.py

from agents.communication.query_handler import get_query_handler, QueryIntentType

def test_communication_query_parsing():
    """Test communication query intent detection."""
    handler = get_query_handler()
    
    test_cases = [
        (
            "Schedule a meeting with john@company.com tomorrow at 2pm EST",
            QueryIntentType.SCHEDULE,
        ),
        (
            "Summarize the Q1 planning meeting",
            QueryIntentType.SUMMARIZE,
        ),
        (
            "Generate an agenda for the standup meeting",
            QueryIntentType.AGENDA,
        ),
    ]
    
    for query, expected_intent in test_cases:
        parsed = handler.parse_query(query)
        assert parsed.intent == expected_intent
        assert parsed.confidence > 0.6
        print(f"✓ Query '{query}'")
        print(f"  Intent: {parsed.intent.value}")
        print(f"  Confidence: {parsed.confidence:.2%}")
```

### Test 3: PII Sanitization in Logs

```python
# test_pii_sanitization.py

from observability.logger import get_logger
from common.pii_sanitizer import sanitize_data
import json

def test_pii_sanitization():
    """Test that PII is masked in logs."""
    logger = get_logger("test")
    
    sensitive_data = {
        "vendor_name": "TechCorp Inc",
        "recent_clients": ["NASA", "Tesla", "Google"],
        "contact_email": "vendor@techcorp.com",
        "phone": "555-123-4567",
    }
    
    # Sanitize before logging
    sanitized = sanitize_data(sensitive_data)
    
    logger.info(
        "Vendor information",
        agent="vendor_management",
        data=sanitized,  # Already masked
    )
    
    # Verify PII is masked
    assert "[CLIENT_NAME]" in str(sanitized.get("recent_clients"))
    assert "[EMAIL]" in str(sanitized.get("contact_email"))
    assert "[PHONE]" in str(sanitized.get("phone"))
    
    print("✓ PII properly masked in logs")
```

### Test 4: Metrics Recording

```python
# test_metrics_recording.py

from observability.metrics import get_metrics, MetricsTracker

def test_metrics_recording():
    """Test metrics collection."""
    metrics = get_metrics()
    
    # Record various metrics
    with MetricsTracker("vendor_matching", agent_name="vendor_management") as tracker:
        metrics.record_histogram("vendor_matching.candidates", 5)
        metrics.record_histogram("vendor_matching.duration_ms", 1250)
        metrics.increment_counter("vendor_matching.success")
    
    # Get report
    report = metrics.get_metrics_report()
    
    assert report.get("vendor_matching.success", 0) > 0
    assert report.get("vendor_matching.candidates", 0) > 0
    
    print("✓ Metrics recorded successfully")
    print(json.dumps(report, indent=2))
```

---

## Deployment Checklist

- [ ] Update `agents/vendor_management/agent.py` with metrics wiring
- [ ] Update `agents/communication/agent.py` with query handler
- [ ] Add tracing middleware to `backend/api/main.py`
- [ ] Add metrics endpoint to `backend/api/routes/`
- [ ] Add tracing endpoint to `backend/api/routes/`
- [ ] Run all integration tests
- [ ] Test end-to-end vendor matching flow
- [ ] Test end-to-end communication flow
- [ ] Monitor logs and metrics
- [ ] Deploy to staging
- [ ] Monitor production metrics for 24 hours
- [ ] Deploy to production

---

## Troubleshooting

### Issue: PII not being masked in LLM calls

**Solution**: Ensure `sanitize_data()` is called on vendor context before LLM invocation.

```python
# Correct:
sanitized = sanitize_data(vendor_context)
llm.invoke(prompt_with_sanitized)

# Wrong:
llm.invoke(prompt_with_vendor_context)  # ❌ Sends unmasked PII
```

### Issue: Metrics not appearing in reports

**Solution**: Ensure metrics are being recorded in the right place.

```python
metrics = get_metrics()  # Get global instance
# Not: metrics = MetricsCollector()  # New instance won't be global!
```

### Issue: Traces not correlating across requests

**Solution**: Ensure correlation IDs are propagated through headers.

```python
# Client should send:
headers = {"X-Correlation-ID": "req-abc-123"}

# Server extracts and uses:
correlation_id = request.headers.get("X-Correlation-ID")
```

---

**Last Updated**: 2024  
**Status**: Integration Ready
