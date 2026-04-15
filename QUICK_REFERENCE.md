# Quick Reference - Vendor & Communication Agent Upgrades

## 🎯 New Capabilities at a Glance

### Vendor Management

| Feature | Module | Usage | Benefit |
|---------|--------|-------|---------|
| **Historical Performance Scoring** | `performance_aggregator.py` | Automatically enhances fit scores | +3-15 points for vendors with good history |
| **PII Sanitization in LLM** | `evaluate.py` (updated) | Automatic masking before LLM call | Project names, clients hidden from external LLMs |
| **Natural Language Queries** | `query_orchestrator.py` | `"Find cloud vendors under $2k"` | Flexible client requirements parsing |
| **Risk Scoring** | `performance_aggregator.py` | Composite risk assessment | Identifies risky vendors automatically |
| **Trend Analysis** | `performance_aggregator.py` | `trending_up`, `stable`, `trending_down` | Vendors improving/declining tracked |
| **Distributed Tracing** | `tracing.py` + `vendor_matcher.py` | Request correlation across steps | Debug and monitor complex flows |

### Communication Agent

| Feature | Module | Usage | Benefit |
|---------|--------|-------|---------|
| **Flexible Intent Detection** | `query_handler.py` | Handles 8 intent types | Route user queries to right tools |
| **Parameter Extraction** | `query_handler.py` | Auto-detect attendees, time, timezone | Reduced clarification requests |
| **Confidence Scoring** | `query_handler.py` | Confidence % for detected intent | Know when to ask for clarification |
| **LLM or Rule-Based** | `query_handler.py` | Fallback parsing modes | Works even if LLM fails |

---

## 📋 Integration Checklist (30 minutes)

```bash
# 1. Wire metrics into agent execute() methods
# File: agents/vendor_management/agent.py
# Add: metrics.record_histogram(), metrics.increment_counter()
# Copy from INTEGRATION_GUIDE.md § Vendor Management Integration

# 2. Wire communication query handler
# File: agents/communication/agent.py
# Add: handler = get_query_handler()
#      parsed_intent = handler.parse_query(query)
#      route_by_intent(parsed_intent)
# Copy from INTEGRATION_GUIDE.md § Communication Agent Integration

# 3. Add middleware for tracing
# File: backend/api/middleware.py
# Add: RequestTracingMiddleware with X-Correlation-ID

# 4. Add metrics endpoint
# File: backend/api/routes/metrics.py
# Add: @router.get("/summary")
```

---

## 🚀 Usage Examples

### Example 1: Vendor Matching with NL Query

```python
from agents.vendor_management.query_orchestrator import get_vendor_query_orchestrator
from agents.vendor_management.tools.vendor_matcher import VendorMatcherTool

# Parse user's natural language query
orchestrator = get_vendor_query_orchestrator()
query = "Find reliable cloud vendors under $1.5k/month in US"
parsed_req = orchestrator.parse_vendor_query(query)

# Automatically gets:
# - service_tag: cloud_hosting
# - budget_monthly: 1500
# - country: US
# - min_on_time_rate: 0.95 (higher due to "reliable")

# Execute matching with historical performance
matcher = VendorMatcherTool()
result = matcher.execute(parsed_req.to_matcher_input())

# Result includes:
# - fit_score: 78 (enhanced from 75 base due to good history)
# - selection_reason: "Top choice — strong quality (88/100), reliable delivery..."
# - Traced and logged with PII sanitization ✓
```

### Example 2: Communication Query Parsing

```python
from agents.communication.query_handler import get_query_handler

handler = get_query_handler()

# Query 1: Schedule meeting
query1 = "Schedule meeting with john@company.com tomorrow 2pm EST"
intent1 = handler.parse_query(query1)
# intent: SCHEDULE, confidence: 0.92
# attendees: ["john@company.com"]
# datetime: "2024-01-16T14:00:00"
# timezone: "EST"

# Query 2: Ambiguous query
query2 = "Can you do something with the meeting?"
intent2 = handler.parse_query(query2)
# intent: UNKNOWN, confidence: 0.3
# requires_clarification: True
# clarification_request: "Could you specify... (schedule/summarize/brief?)"
```

### Example 3: Vendor Evaluation with Sanitized LLM

```python
# In vendor_management/nodes/evaluate.py (already implemented)

# Before LLM call:
vendor_context = {
    "name": "VendorX Corp",
    "recent_projects": ["Government AI Initiative", "Tesla Supply Chain"],  # SENSITIVE
    "clients": ["US DoD", "Tesla", "Goldman Sachs"],  # SENSITIVE
}

# After sanitization:
sanitized_context = sanitize_data(vendor_context)
# {
#   "name": "VendorX Corp",
#   "recent_projects": ["[PROJECT_NAME]", "[PROJECT_NAME]"],
#   "clients": ["[CLIENT_NAME]", "[CLIENT_NAME]", "[CLIENT_NAME]"],
# }

# LLM never sees actual project/client names ✓
```

### Example 4: Metrics & Tracing

```python
from observability.metrics import get_metrics, MetricsTracker
from observability.tracing import get_tracer

tracer = get_tracer("vendor_management")
metrics = get_metrics()

with tracer.trace_operation("vendor_matching", attributes={"service": "cloud"}):
    # This automatically:
    # - Creates span with unique ID
    # - Correlates with parent span (if any)
    # - Exports to LangSmith (if configured)
    # - Records duration and status
    
    result = vendor_matcher.execute(input)
    
    # Record business metrics
    with MetricsTracker("vendor_matching") as tracker:
        metrics.record_histogram("vendor_matching.candidates", len(result.ranked_vendors))

# View metrics:
report = metrics.get_metrics_report()
# {
#   "vendor_matching.candidates": 5,
#   "vendor_matching.duration_ms": 1250,
#   "vendor_matching.success": 1,
# }
```

---

## 🔍 Key Files Reference

### Vendor Management

| File | Purpose | Key Class/Function |
|------|---------|-------------------|
| `performance_aggregator.py` | Historical vendor metrics | `VendorPerformanceAggregator`, `compute_fit_score_enhancement()` |
| `query_orchestrator.py` | Parse NL requirements | `VendorQueryOrchestrator`, `parse_vendor_query()` |
| `vendor_matcher.py` (updated) | Enhanced ranking | Uses hist. perf in fit score |
| `evaluate.py` (updated) | Vendor evaluation | PII sanitization before LLM |

### Communication

| File | Purpose | Key Class/Function |
|------|---------|-------------------|
| `query_handler.py` | Intent detection | `CommunicationQueryHandler`, `parse_query()` |

### Observability

| File | Purpose | Key Class/Function |
|------|---------|-------------------|
| `logger.py` | Structured logging | `StructuredLogger`, `get_logger()` |
| `metrics.py` | Metrics collection | `MetricsCollector`, `get_metrics()` |
| `tracing.py` | Request tracing | `DistributedTracer`, `get_tracer()` |

---

## 📊 Metrics Available

### Vendor Management Metrics

```python
# Vendor Matching
metrics.record_histogram("vendor_matching.duration_ms", duration)
metrics.record_histogram("vendor_matching.candidates", count)
metrics.increment_counter("vendor_matching.success")

# Vendor Evaluation
metrics.record_histogram("vendor_evaluation.duration_ms", duration)
metrics.increment_counter("vendor_evaluation.success")

# LLM Calls
metrics.record_histogram("llm_call.duration_ms", duration)
metrics.increment_counter("llm_call.success")
metrics.increment_counter("llm_call.failure")
```

### Communication Metrics

```python
# Query Parsing
metrics.record_histogram("communication_query.parse_confidence", confidence)
metrics.increment_counter("communication_query.parsed")
```

### View All Metrics

```python
from observability.metrics import get_metrics

metrics = get_metrics()
report = metrics.get_metrics_report()
print(report)
# Returns dict of all recorded metrics
```

---

## 🔐 Security Features

### Automatic PII Masking

The system automatically masks:
- Email addresses → `[EMAIL]`
- Phone numbers → `[PHONE]`
- Project names → `[PROJECT_NAME]`
- Client names → `[CLIENT_NAME]`
- Credit cards → `[CREDIT_CARD]`
- API keys → `[API_KEY]`
- SSNs → `[SSN]`

### Where Masking Happens

1. **Vendor Context before LLM** ✓ (in `evaluate.py`)
2. **Selection Reasons in logs** ✓ (in `vendor_matcher.py`)
3. **All structured logging** ✓ (auto in `logger.py`)

### Never Masked (for functionality)

- Vendor ID, Vendor Name (needed for identification)
- Budget amounts (needed for analysis)
- Quality scores (numeric only)

---

## ⚠️ Common Mistakes to Avoid

### ❌ Wrong: Sending unmasked context to LLM

```python
# DON'T do this:
vendor_context = {"name": "Corp", "clients": ["Alpha", "Beta"]}
llm.invoke(prompt_with_context)  # PII exposed!
```

### ✅ Right: Sanitize first

```python
# DO this:
vendor_context = {...}
sanitized = sanitize_data(vendor_context)
llm.invoke(prompt_with_sanitized)  # Safe ✓
```

### ❌ Wrong: Creating new metrics instance

```python
# DON'T do this:
metrics = MetricsCollector()  # New instance!
metrics.increment_counter("vendor_matching.success")  # Lost!
```

### ✅ Right: Use global instance

```python
# DO this:
metrics = get_metrics()  # Global instance
metrics.increment_counter("vendor_matching.success")  # Recorded ✓
```

### ❌ Wrong: Ignoring confidence in intent detection

```python
# DON'T do this:
parsed = handler.parse_query(ambiguous_query)
use_intent_result_directly()  # Might be wrong!
```

### ✅ Right: Check confidence first

```python
# DO this:
parsed = handler.parse_query(query)
if parsed.confidence < 0.6:
    ask_for_clarification()
else:
    use_intent_result()
```

---

## 🧪 Quick Tests

### Test Vendor Matching

```bash
python -c "
from agents.vendor_management.query_orchestrator import get_vendor_query_orchestrator
orch = get_vendor_query_orchestrator()
req = orch.parse_vendor_query('Find cloud vendors under \$2k')
print(f'Service: {req.service_tag}, Budget: {req.budget_monthly}')
"
```

### Test Communication Query

```bash
python -c "
from agents.communication.query_handler import get_query_handler
handler = get_query_handler()
intent = handler.parse_query('Schedule meeting tomorrow at 2pm')
print(f'Intent: {intent.intent}, Confidence: {intent.confidence:.0%}')
"
```

### Test PII Sanitization

```bash
python -c "
from common.pii_sanitizer import sanitize_data
data = {'email': 'john@company.com', 'project': 'Tesla AI'}
print(sanitize_data(data))
"
```

### Test Metrics

```bash
python -c "
from observability.metrics import get_metrics
m = get_metrics()
m.increment_counter('test.counter')
print(m.get_metrics_report())
"
```

---

## 📞 Support

**Documentation**:
- Detailed docs: See `AGENT_UPGRADES_SUMMARY.md`
- Integration guide: See `INTEGRATION_GUIDE.md`
- Architecture: See AGENT_UPGRADES_SUMMARY.md § Architecture Diagrams

**Code Examples**:
- Vendor matching: See `test_vendor_matching_enhanced.py`
- Communication: See `test_communication_queries.py`
- PII: See `test_pii_sanitization.py`
- Metrics: See `test_metrics_recording.py`

**Questions**:
- How do I...? → Search AGENT_UPGRADES_SUMMARY.md for the feature
- Where is...? → Check "Key Files Reference" table above
- Why isn't...? → Check "Common Mistakes to Avoid" section

---

## 📈 Performance Notes

| Operation | Typical Duration | Notes |
|-----------|------------------|-------|
| Vendor query parsing (LLM) | 800-1200ms | Fallback to rules if LLM fails |
| Vendor matching | 1000-2000ms | Scales with number of vendors |
| Vendor evaluation | 2000-5000ms | Includes LLM call; fallback to rules |
| Communication intent detection | 500-1000ms | Fast rule-based, slow LLM-based |
| PII sanitization | 5-50ms | Very fast, linear with data size |

---

## 🎓 Learning Path

1. **Start Here**: Read this quick reference (you are here!)
2. **Understand Architecture**: Read AGENT_UPGRADES_SUMMARY.md § Architecture Diagrams
3. **Learn Integration**: Read INTEGRATION_GUIDE.md § Step-by-step setup
4. **Deep Dive**: Read source code in:
   - `agents/vendor_management/performance_aggregator.py`
   - `agents/communication/query_handler.py`
   - `observability/tracing.py`

---

**Last Updated**: 2024  
**Version**: 1.0  
**Status**: Production Ready
