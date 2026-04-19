import os
import sys

# Ensure project root is in path
sys.path.append(os.getcwd())

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from config.settings import Settings
    from backend.services.agent_registry import initialise_agents
    
    settings = Settings()
    # Check correct attribute name
    print(f"DEBUG: Using Primary LLM: {getattr(settings, 'llm_primary', 'MISSING')}")
    
    # Manually try to import and init to see the error clearly
    from agents.vendor_management.agent import VendorManagementAgent
    from agents.registry import ToolRegistry
    from human_loop.manager import HITLManager
    
    registry = ToolRegistry()
    hitl = HITLManager(settings.hitl_threshold)
    
    print("DEBUG: Attempting manual VendorManagementAgent init...")
    vm = VendorManagementAgent(config=settings, tool_registry=registry, hitl_manager=hitl)
    print("DEBUG: Manual init SUCCESS")
    
    agents = initialise_agents(settings)
    print(f"DEBUG: Registry initialized agents: {list(agents.keys())}")
    
except Exception:
    import traceback
    traceback.print_exc()
