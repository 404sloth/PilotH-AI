#!/usr/bin/env python3
"""
Test script to verify the API endpoint changes work correctly.
Tests the import fixes and agent_hint functionality.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

def test_imports():
    """Test that all imports work correctly."""
    try:
        from backend.api.dependencies import get_settings
        from orchestrator.controller import OrchestratorController
        from orchestrator.advanced_intent_parser import AdvancedIntentParser
        print("✓ All imports successful")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False

def test_agent_hint_logic():
    """Test that agent_hint is properly handled."""
    try:
        from backend.api.dependencies import get_settings
        from orchestrator.advanced_intent_parser import AdvancedIntentParser

        settings = get_settings()
        parser = AdvancedIntentParser(settings)

        # Test with agent_hint
        result = parser.parse(
            message="find the best vendor",
            agent_hint="vendor_management"
        )

        print(f"✓ Agent hint test: agent={result.get('agent')}, action={result.get('action')}")
        assert result.get('agent') == 'vendor_management', f"Expected vendor_management, got {result.get('agent')}"
        return True
    except Exception as e:
        print(f"✗ Agent hint test failed: {e}")
        return False

def test_controller_with_hint():
    """Test that controller accepts agent_hint parameter."""
    try:
        from backend.api.dependencies import get_settings
        from orchestrator.controller import OrchestratorController

        settings = get_settings()
        controller = OrchestratorController(settings)

        # Check that handle method accepts agent_hint
        import inspect
        sig = inspect.signature(controller.handle)
        params = list(sig.parameters.keys())

        assert 'agent_hint' in params, f"agent_hint parameter not found in handle method. Params: {params}"
        print("✓ Controller handle method accepts agent_hint parameter")
        return True
    except Exception as e:
        print(f"✗ Controller test failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing API endpoint fixes...")

    tests = [
        test_imports,
        test_agent_hint_logic,
        test_controller_with_hint,
    ]

    passed = 0
    for test in tests:
        if test():
            passed += 1
        print()

    print(f"Results: {passed}/{len(tests)} tests passed")

    if passed == len(tests):
        print("🎉 All tests passed! API endpoint changes are working correctly.")
        sys.exit(0)
    else:
        print("❌ Some tests failed.")
        sys.exit(1)