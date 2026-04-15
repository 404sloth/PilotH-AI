"""
Test Suite: Advanced Intent Parser, System Prompts, PII Sanitization, and Tool Validation

Tests:
  ✓ Advanced intent parser with LLM and keyword fallback
  ✓ PII sanitization in all contexts
  ✓ System prompts for agents
  ✓ Tool validation and error handling
  ✓ End-to-end agent workflows
"""

import pytest

from config.settings import Settings
from observability.pii_sanitizer import PIISanitizer
from orchestrator.advanced_intent_parser import TOOL_REGISTRY, AdvancedIntentParser
from orchestrator.system_prompts import (
    AgentType,
    get_evaluation_prompt,
    get_prompt,
    get_system_prompt,
)
from tools.validation import (
    ToolValidationError,
)

# ── Test Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def settings():
    return Settings()


@pytest.fixture
def intent_parser(settings):
    return AdvancedIntentParser(settings)


# ── PII Sanitization Tests ────────────────────────────────────────────────


class TestPIISanitization:
    """Test PII masking in various data structures."""

    def test_email_masking(self):
        """Email addresses should be masked."""
        email = "john.doe@company.com"
        masked = PIISanitizer.sanitize_email(email)

        assert "@" in masked
        assert "john.doe@company.com" not in masked
        assert masked == "j***e@c***y.com"

    def test_phone_masking(self):
        """Phone numbers should be masked."""
        phone = "(555) 123-4567"
        masked = PIISanitizer.sanitize_phone(phone)

        assert "555" not in masked
        assert "123" not in masked
        assert "4567" in masked  # Last 4 always shown

    def test_ssn_masking(self):
        """SSN should be masked."""
        ssn = "123-45-6789"
        masked = PIISanitizer.sanitize_ssn(ssn)

        assert masked == "***-**-6789"

    def test_credit_card_masking(self):
        """Credit cards should be masked."""
        cc = "1234-5678-9012-3456"
        masked = PIISanitizer.sanitize_credit_card(cc)

        assert "1234" not in masked
        assert "3456" in masked  # Last 4 digits

    def test_api_key_masking(self):
        """API keys in strings should be redacted."""
        text = 'api_key: "sk-1234567890abcdefghij"'
        masked = PIISanitizer.sanitize_string(text)

        assert "[REDACTED]" in masked
        assert "sk-1234567890" not in masked

    def test_dict_sanitization_recursive(self):
        """Dict with nested PII should be sanitized."""
        data = {
            "user": {
                "email": "john@example.com",
                "phone": "(555) 123-4567",
                "name": "John Doe",
            },
            "api_key": "sk-1234567890",
            "safe_field": "public_data",
        }

        sanitized = PIISanitizer.sanitize_dict(data)

        assert sanitized["user"]["email"] != "john@example.com"
        assert sanitized["user"]["phone"] != "(555) 123-4567"
        assert "[REDACTED]" in str(sanitized["api_key"])
        assert sanitized["safe_field"] == "public_data"

    def test_list_sanitization(self):
        """Lists with PII should be sanitized."""
        data = [
            "contact: john@example.com",
            "safe: public information",
        ]

        sanitized = PIISanitizer.sanitize_list(data)

        assert sanitized[0] != data[0]
        assert sanitized[1] == data[1]


# ── Intent Parser Tests ────────────────────────────────────────────────────


class TestAdvancedIntentParser:
    """Test LLM-based and keyword-based intent parsing."""

    def test_vendor_management_keywords(self, intent_parser):
        """Vendor management keywords should be recognized."""
        messages = [
            "find the best vendor for cloud hosting",
            "assess this vendor: CloudPro",
            "check SLA compliance for vendor 123",
            "track milestones for project ABC",
        ]

        for msg in messages:
            result = intent_parser._keyword_parse(msg)
            assert result["agent"] == "vendor_management"
            assert result["action"] != ""
            assert result["confidence"] > 0

    def test_communication_keywords(self, intent_parser):
        """Communication keywords should be recognized."""
        messages = [
            "schedule a meeting with John and Jane",
            "summarize this meeting transcript",
            "brief me before the meeting",
            "what is the agenda for tomorrow",
        ]

        for msg in messages:
            result = intent_parser._keyword_parse(msg)
            assert result["agent"] == "meetings_communication"
            assert result["action"] != ""

    def test_confidence_scoring(self, intent_parser):
        """Confidence should be higher for clear matches."""
        clear_msg = "find best vendor for cloud hosting"
        unclear_msg = "help"

        clear_result = intent_parser._keyword_parse(clear_msg)
        unclear_result = intent_parser._keyword_parse(unclear_msg)

        assert clear_result["confidence"] > unclear_result["confidence"]

    def test_tool_registry_valid(self):
        """Tool registry should contain valid agents and actions."""
        for agent_info in TOOL_REGISTRY.items():
            assert "agent_name" in agent_info
            assert "actions" in agent_info

            for action_info in agent_info["actions"].items():
                assert "description" in action_info
                assert "triggers" in action_info
                assert len(action_info["triggers"]) > 0


# ── System Prompts Tests ───────────────────────────────────────────────────


class TestSystemPrompts:
    """Test system prompt generation."""

    def test_vendor_system_prompt(self):
        """Vendor system prompt should contain key guidance."""
        prompt = get_system_prompt(AgentType.VENDOR_MANAGEMENT)

        assert "procurement" in prompt.lower() or "vendor" in prompt.lower()
        assert "quality" in prompt.lower()
        assert "sla" in prompt.lower()
        assert "risk" in prompt.lower()

    def test_communication_system_prompt(self):
        """Communication system prompt should contain meeting guidance."""
        prompt = get_system_prompt(AgentType.COMMUNICATION)

        assert "meeting" in prompt.lower()
        assert "scheduling" in prompt.lower() or "schedule" in prompt.lower()
        assert "timezone" in prompt.lower()
        assert "action items" in prompt.lower()

    def test_evaluation_prompt_generation(self):
        """Evaluation prompt should be properly formatted."""
        vendor_data = {
            "vendor": {"name": "TestVendor", "quality_score": 85},
            "sla": {"overall_compliance": 95},
        }

        prompt = get_evaluation_prompt(vendor_data, "TestVendor")

        assert "TestVendor" in prompt
        assert "evaluation" in prompt.lower()
        assert "{" in prompt  # Should contain JSON template
        assert "}" in prompt

    def test_meeting_summary_prompt_generation(self):
        """Meeting summary prompt should be properly formatted."""
        transcript = "John: Let's deploy next week. Jane: Agreed."

        prompt = get_prompt(
            "meeting_summary",
            transcript=transcript,
            meeting_title="Planning Session",
        )

        assert "Planning Session" in prompt
        assert "summary" in prompt.lower()
        assert "{" in prompt  # Should contain JSON template


# ── Tool Validation Tests ──────────────────────────────────────────────────


class TestToolValidation:
    """Test tool input/output validation and error handling."""

    def test_validation_error_creation(self):
        """ToolValidationError should be properly created."""
        error = ToolValidationError(
            "Test message",
            "test_tool",
            {"field": "test"},
        )

        assert error.message == "Test message"
        assert error.tool_name == "test_tool"
        assert error.error_code == "VALIDATION_ERROR"
        assert not error.is_retryable

    def test_validation_error_with_details(self):
        """ToolValidationError should preserve details."""
        details = {"field": "email", "reason": "invalid format"}
        error = ToolValidationError(
            "Validation failed",
            "email_tool",
            details,
        )

        assert error.details == details


# ── Integration Tests ──────────────────────────────────────────────────────


class TestIntegration:
    """End-to-end integration tests."""

    def test_intent_parsing_with_sanitization(self, intent_parser):
        """Intent parser should handle PII in messages."""
        message = "Find best vendor for john.doe@company.com"

        result = intent_parser.parse(message)

        assert result["agent"] in TOOL_REGISTRY
        assert "action" in result
        # Original message not modified
        assert "john.doe@company.com" not in result.get("reasoning", "")

    def test_full_vendor_workflow(self):
        """Vendor management workflow should work end-to-end."""
        from agents.vendor_management.agent import VendorManagementAgent

        config = Settings()
        agent = VendorManagementAgent(config)

        # Agent should be properly initialized
        assert agent.name == "vendor_management"
        assert agent.input_schema is not None
        assert agent.output_schema is not None

    def test_full_communication_workflow(self):
        """Communication workflow should work end-to-end."""
        from agents.communication.agent import MeetingCommunicationAgent

        config = Settings()
        agent = MeetingCommunicationAgent(config)

        # Agent should be properly initialized
        assert agent.name == "meetings_communication"
        assert agent.input_schema is not None
        assert agent.output_schema is not None


# ── Regression Tests ───────────────────────────────────────────────────────


class TestRegression:
    """Tests for known issues and edge cases."""

    def test_multiple_emails_in_message(self, intent_parser):
        """Parser should handle multiple emails in message."""
        message = "Brief john@example.com and jane@example.com for the meeting"
        result = intent_parser.parse(message)

        assert result["agent"] == "meetings_communication"
        assert result["action"] == "brief"

    def test_ambiguous_keywords(self, intent_parser):
        """Parser should handle ambiguous keywords."""
        message = "schedule vs requirements"  # 'schedule' could match meeting agent
        result = intent_parser.parse(message)

        # Should pick best match, not crash
        assert result["agent"] in TOOL_REGISTRY

    def test_empty_message_handling(self, intent_parser):
        """Parser should handle empty messages gracefully."""
        result = intent_parser.parse("")

        # Should fall back to default, not crash
        assert result["agent"] == "vendor_management"
        assert result["confidence"] < 0.5


# ── Run Tests ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
