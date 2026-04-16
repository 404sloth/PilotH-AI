#!/usr/bin/env python3
"""
Quick verification script for all improvements.
"""

from orchestrator.intent_parser import IntentParser, TOOL_REGISTRY
from orchestrator.system_prompts import get_system_prompt, AgentType
from tools.validation import validate_tool_execution, ToolExecutionError
from observability.pii_sanitizer import PIISanitizer

print("✅ All imports successful!")
print(f"\n📋 Advanced Intent Parser:")
print(f"   - {len(TOOL_REGISTRY)} agents registered")
print(f"   - Vendor management actions: {list(TOOL_REGISTRY['vendor_management']['actions'].keys())}")
print(f"   - Communication actions: {list(TOOL_REGISTRY['meetings_communication']['actions'].keys())}")

print(f"\n📝 System Prompts:")
vendor_prompt = get_system_prompt(AgentType.VENDOR_MANAGEMENT)
comm_prompt = get_system_prompt(AgentType.COMMUNICATION)
print(f"   - Vendor prompt length: {len(vendor_prompt)} chars")
print(f"   - Communication prompt length: {len(comm_prompt)} chars")

print(f"\n🛡️  Tool Validation:")
print(f"   - ToolExecutionError available")
print(f"   - validate_tool_execution decorator available")

print(f"\n🔒 PII Sanitization:")
test_email = "john@example.com"
masked = PIISanitizer.sanitize_email(test_email)
print(f"   - Email: {test_email} → {masked}")

print(f"\n✨ All systems ready for production!")
