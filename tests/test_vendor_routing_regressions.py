import pytest

from config.settings import Settings
from orchestrator.controller import OrchestratorController
from orchestrator.intent_parser import IntentParser


@pytest.fixture
def settings():
    return Settings()


def test_vendor_list_request_routes_to_search(settings):
    parser = IntentParser(settings)

    result = parser.parse(
        "list all vendors for different services we have across all category",
        context={},
        agent_hint="vendor_management",
    )

    assert result["agent"] == "vendor_management"
    assert result["action"] == "search_vendors"
    assert result["params"]["top_n"] == 20


def test_best_cloud_vendor_extracts_service_and_budget(settings):
    parser = IntentParser(settings)

    result = parser.parse(
        "Find the best cloud vendor within $50,000 budget",
        context={},
        agent_hint="vendor_management",
    )

    assert result["agent"] == "vendor_management"
    assert result["action"] == "find_best"
    assert result["params"]["service_required"] == "cloud_hosting"
    assert result["params"]["budget_monthly"] == 50000


def test_controller_returns_vendor_discovery_results(settings):
    controller = OrchestratorController(settings)

    result = controller.handle(
        message="list all vendors for different services we have across all category",
        context={},
        agent_hint="vendor_management",
    )

    assert result["metadata"]["agent"] == "vendor_management"
    assert result["metadata"]["action"] == "search_vendors"
    assert result["data"]["vendors"]
    assert "Found" in result["response"]


def test_controller_returns_ranked_cloud_vendors(settings):
    controller = OrchestratorController(settings)

    result = controller.handle(
        message="Find the best cloud vendor within $50,000 budget",
        context={},
        agent_hint="vendor_management",
    )

    assert result["metadata"]["agent"] == "vendor_management"
    assert result["metadata"]["action"] == "find_best"
    assert result["data"]["ranked_vendors"]
    assert result["data"]["top_recommendation"]
    assert "No vendors found" not in result["response"]
