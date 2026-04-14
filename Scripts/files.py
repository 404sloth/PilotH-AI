import os
from pathlib import Path

# Script runs inside: PilotH/scripts/
# It will go one level up and create full structure

BASE_DIR = Path(__file__).resolve().parent.parent


def create_file(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()


def create_structure():
    structure = [
        # backend
        "backend/api/__init__.py",
        "backend/api/dependencies.py",
        "backend/api/routes/__init__.py",
        "backend/api/routes/agent_routes.py",
        "backend/api/routes/human_loop_routes.py",
        "backend/api/routes/health.py",
        "backend/api/middleware.py",
        "backend/api/main.py",
        "backend/websocket/manager.py",
        "backend/services/agent_registry.py",
        "backend/services/task_queue.py",

        # orchestrator
        "orchestrator/__init__.py",
        "orchestrator/controller.py",
        "orchestrator/intent_parser.py",
        "orchestrator/task_decomposer.py",
        "orchestrator/agent_router.py",
        "orchestrator/memory_manager.py",
        "orchestrator/fallback_handler.py",
        "orchestrator/workflow_engine.py",

        # agents core
        "agents/base_agent.py",
        "agents/registry.py",

        # vendor_management
        "agents/vendor_management/__init__.py",
        "agents/vendor_management/agent.py",
        "agents/vendor_management/graph.py",
        "agents/vendor_management/nodes/__init__.py",
        "agents/vendor_management/nodes/evaluation.py",
        "agents/vendor_management/nodes/risk_detection.py",
        "agents/vendor_management/nodes/summary.py",
        "agents/vendor_management/tools/__init__.py",
        "agents/vendor_management/tools/vendor_search.py",
        "agents/vendor_management/tools/sla_monitor.py",
        "agents/vendor_management/tools/contract_parser.py",
        "agents/vendor_management/tools/milestone_tracker.py",
        "agents/vendor_management/schemas.py",

        # communication
        "agents/communication/__init__.py",
        "agents/communication/agent.py",
        "agents/communication/graph.py",
        "agents/communication/nodes/scheduling.py",
        "agents/communication/nodes/agenda_gen.py",
        "agents/communication/nodes/summarizer.py",
        "agents/communication/nodes/sentiment.py",
        "agents/communication/tools/calendar_tool.py",
        "agents/communication/tools/email_draft.py",
        "agents/communication/tools/timezone_converter.py",
        "agents/communication/tools/participant_briefing.py",
        "agents/communication/schemas.py",

        # insights
        "agents/insights/__init__.py",
        "agents/insights/agent.py",
        "agents/insights/graph.py",
        "agents/insights/nodes/kpi_analyzer.py",
        "agents/insights/nodes/predictive_model.py",
        "agents/insights/nodes/competitor_monitor.py",
        "agents/insights/nodes/scenario_modeling.py",
        "agents/insights/tools/sql_query_tool.py",
        "agents/insights/tools/dashboard_fetcher.py",
        "agents/insights/tools/forecasting.py",
        "agents/insights/tools/market_scanner.py",
        "agents/insights/schemas.py",

        # compliance
        "agents/compliance/__init__.py",
        "agents/compliance/agent.py",
        "agents/compliance/graph.py",
        "agents/compliance/nodes/regulatory_check.py",
        "agents/compliance/nodes/checklist_gen.py",
        "agents/compliance/nodes/risk_dashboard.py",
        "agents/compliance/tools/regulation_fetcher.py",
        "agents/compliance/tools/deadline_tracker.py",
        "agents/compliance/tools/impact_analyzer.py",
        "agents/compliance/schemas.py",

        # executive_support
        "agents/executive_support/__init__.py",
        "agents/executive_support/agent.py",
        "agents/executive_support/graph.py",
        "agents/executive_support/nodes/strategy_advisor.py",
        "agents/executive_support/nodes/bottleneck_detector.py",
        "agents/executive_support/nodes/roi_estimator.py",
        "agents/executive_support/nodes/chief_of_staff.py",
        "agents/executive_support/tools/department_performance.py",
        "agents/executive_support/tools/early_warning.py",
        "agents/executive_support/tools/delegation_suggester.py",
        "agents/executive_support/tools/priority_ranker.py",
        "agents/executive_support/schemas.py",

        # tools core
        "tools/base_tool.py",
        "tools/registry.py",

        "tools/api_tools/__init__.py",
        "tools/api_tools/rest_client.py",
        "tools/api_tools/graphql_client.py",
        "tools/api_tools/webhook_sender.py",

        "tools/data_tools/__init__.py",
        "tools/data_tools/sql_executor.py",
        "tools/data_tools/table_joiner.py",
        "tools/data_tools/dataframe_ops.py",
        "tools/data_tools/vector_search.py",

        "tools/communication_tools/__init__.py",
        "tools/communication_tools/email_sender.py",
        "tools/communication_tools/slack_notifier.py",
        "tools/communication_tools/meeting_scheduler.py",

        "tools/calendar_tools/__init__.py",
        "tools/calendar_tools/google_calendar.py",
        "tools/calendar_tools/availability_finder.py",

        "tools/analytics_tools/__init__.py",
        "tools/analytics_tools/forecast_model.py",
        "tools/analytics_tools/sentiment_analyzer.py",
        "tools/analytics_tools/summarizer.py",

        "tools/file_tools/__init__.py",
        "tools/file_tools/pdf_parser.py",
        "tools/file_tools/docx_generator.py",
        "tools/file_tools/csv_handler.py",

        # graphs
        "graphs/__init__.py",
        "graphs/orchestration_graph.py",
        "graphs/subgraph_loader.py",
        "graphs/conditional_edges.py",

        # schemas
        "schemas/__init__.py",
        "schemas/common.py",
        "schemas/user_request.py",
        "schemas/agent_io.py",
        "schemas/tool_io.py",
        "schemas/human_loop.py",
        "schemas/memory.py",

        # human_loop
        "human_loop/__init__.py",
        "human_loop/manager.py",
        "human_loop/approval.py",
        "human_loop/feedback.py",
        "human_loop/escalation.py",
        "human_loop/ui_components.py",

        # integrations
        "integrations/__init__.py",
        "integrations/google_calendar/__init__.py",
        "integrations/google_calendar/auth.py",
        "integrations/google_calendar/client.py",
        "integrations/google_calendar/models.py",
        "integrations/crm/salesforce.py",
        "integrations/crm/hubspot.py",
        "integrations/finance/erp_connector.py",
        "integrations/data_warehouse/bigquery_client.py",

        # llm
        "llm/__init__.py",
        "llm/base.py",
        "llm/openai_client.py",
        "llm/ollama_client.py",
        "llm/groq_client.py",
        "llm/model_factory.py",
        "llm/token_counter.py",

        # memory
        "memory/__init__.py",
        "memory/session_store.py",
        "memory/vector_store.py",
        "memory/global_context.py",
        "memory/embeddings.py",

        # observability
        "observability/__init__.py",
        "observability/logger.py",
        "observability/tracing.py",
        "observability/metrics.py",
        "observability/langsmith_config.py",

        # config
        "config/__init__.py",
        "config/settings.py",
        "config/agents.yaml",
        "config/tools.yaml",
        "config/.env.example",

        # tests
        "tests/unit/agents/",
        "tests/unit/tools/",
        "tests/unit/schemas/",
        "tests/integration/test_orchestrator.py",
        "tests/integration/test_agent_chain.py",
        "tests/fixtures/",

        # scripts
        "scripts/seed_data.py",
        "scripts/register_tools.py",
        "scripts/deploy.sh",

        # root files
        "docker-compose.yml",
        "Dockerfile",
        "requirements.txt",
        "pyproject.toml",
        "README.md",
    ]

    for item in structure:
        path = BASE_DIR / item

        if item.endswith("/"):
            path.mkdir(parents=True, exist_ok=True)
        else:
            create_file(path)


if __name__ == "__main__":
    create_structure()
    print("Project structure created successfully.")