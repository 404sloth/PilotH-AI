#!/usr/bin/env python3
"""
PilotH System Initialization Script

Initializes:
  - Database schema and seeding
  - Knowledge base with sample documents
  - Agent tools registration
  - Notifications system
  - Report generation
  
Usage:
  python3 init_system.py
"""

import sys
import os
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)


def init_database():
    """Initialize the database."""
    logger.info("=" * 80)
    logger.info("STEP 1: Initializing Database")
    logger.info("=" * 80)
    
    try:
        from integrations.data_warehouse.sqlite_client import init_db
        init_db(seed=True)
        logger.info("✓ Database initialized and seeded successfully")
        return True
    except Exception as e:
        logger.error(f"✗ Database initialization failed: {e}")
        return False


def init_knowledge_base():
    """Initialize the knowledge base."""
    logger.info("\n" + "=" * 80)
    logger.info("STEP 2: Initializing Knowledge Base")
    logger.info("=" * 80)
    
    try:
        from knowledge_base.vector_store import get_vector_store
        from knowledge_base.document_loader import seed_knowledge_base
        
        vs = get_vector_store()
        logger.info("✓ Vector store initialized")
        
        # Seed with sample documents
        seed_knowledge_base()
        logger.info("✓ Knowledge base seeded with sample documents")
        
        # List collections
        collections = vs.list_collections()
        logger.info(f"✓ Available collections: {[c['name'] for c in collections]}")
        
        return True
    except Exception as e:
        logger.error(f"✗ Knowledge base initialization failed: {e}")
        logger.debug("Note: This is non-critical - system will function without ChromaDB")
        return True  # Non-critical failure


def init_agents():
    """Initialize agents and tools."""
    logger.info("\n" + "=" * 80)
    logger.info("STEP 3: Initializing Agents and Tools")
    logger.info("=" * 80)
    
    try:
        from config.settings import Settings
        from backend.services.agent_registry import initialise_agents
        
        settings = Settings()
        agents = initialise_agents(settings)
        
        logger.info(f"✓ Initialized {len(agents)} agents:")
        for agent_name in agents:
            logger.info(f"  - {agent_name}")
        
        return True
    except Exception as e:
        logger.error(f"✗ Agent initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def init_notifications():
    """Initialize the notification system."""
    logger.info("\n" + "=" * 80)
    logger.info("STEP 4: Initializing Notifications System")
    logger.info("=" * 80)
    
    try:
        from knowledge_base.expiry_notifier import get_expiry_notifier, get_notification_store
        
        notifier = get_expiry_notifier()
        store = get_notification_store()
        
        logger.info(f"✓ Expiry notifier initialized with {len(notifier.triggers)} triggers")
        logger.info(f"✓ Triggers (days before expiry): {sorted(notifier.triggers)}")
        logger.info("✓ Notification store initialized")
        
        return True
    except Exception as e:
        logger.error(f"✗ Notification system initialization failed: {e}")
        return False


def init_reports():
    """Initialize the report generation system."""
    logger.info("\n" + "=" * 80)
    logger.info("STEP 5: Initializing Report Generation")
    logger.info("=" * 80)
    
    try:
        from knowledge_base.report_generator import ReportGenerator
        
        gen = ReportGenerator()
        
        # Generate sample reports
        logger.info("✓ Report generator initialized")
        logger.info("✓ Available report types:")
        logger.info("  - Vendor Performance Reports")
        logger.info("  - Agreement Expiry Reports")
        logger.info("  - Compliance & Risk Reports")
        logger.info("  - Financial Analysis Reports")
        
        return True
    except Exception as e:
        logger.error(f"✗ Report initialization failed: {e}")
        return False


def init_simulations():
    """Initialize the simulation system."""
    logger.info("\n" + "=" * 80)
    logger.info("STEP 6: Initializing Interactive Simulations")
    logger.info("=" * 80)
    
    try:
        from knowledge_base.simulations import get_simulator
        
        sim = get_simulator()
        scenarios = sim.list_scenarios()
        
        logger.info(f"✓ Simulator initialized with {len(scenarios)} scenarios:")
        for scenario in scenarios:
            logger.info(f"  - {scenario['scenario_id']}: {scenario['title']}")
            logger.info(f"    ({scenario['total_steps']} steps)")
        
        return True
    except Exception as e:
        logger.error(f"✗ Simulation initialization failed: {e}")
        return False


def check_api_endpoints():
    """Display available API endpoints."""
    logger.info("\n" + "=" * 80)
    logger.info("STEP 7: API Endpoints Summary")
    logger.info("=" * 80)
    
    endpoints = {
        "Health": [
            "GET  /health",
        ],
        "Agents": [
            "GET  /agents",
            "POST /agents/{agent_name}/run",
        ],
        "Human-in-the-Loop": [
            "GET  /hitl/pending",
            "GET  /hitl/{task_id}",
            "POST /hitl/decision",
            "POST /hitl/{task_id}/cancel",
        ],
        "Knowledge Base": [
            "GET  /kb",
            "GET  /kb/collections",
            "POST /kb/search",
            "POST /kb/documents",
            "DELETE /kb/documents/{collection}/{doc_id}",
        ],
        "Reports": [
            "GET  /reports/vendor/{vendor_id}/performance",
            "GET  /reports/agreements/expiry",
            "GET  /reports/vendor/{vendor_id}/compliance",
            "GET  /reports/vendor/{vendor_id}/financial",
        ],
        "Simulations": [
            "GET  /reports/simulations",
            "GET  /reports/simulations/{scenario_id}",
            "GET  /reports/simulations/{scenario_id}/step/{step_num}",
            "POST /reports/simulations/{scenario_id}/step/{step_num}/evaluate",
        ],
        "Vendors": [
            "GET  /vendors",
            "GET  /vendors/{vendor_id}/scorecard",
            "GET  /vendors/{vendor_id}/sla",
            "GET  /vendors/{vendor_id}/milestones",
        ],
    }
    
    for category, eps in endpoints.items():
        logger.info(f"\n{category}:")
        for endpoint in eps:
            logger.info(f"  {endpoint}")


def test_vendor_request():
    """Test making a vendor request."""
    logger.info("\n" + "=" * 80)
    logger.info("STEP 8: Testing Sample Request")
    logger.info("=" * 80)
    
    try:
        from backend.services.agent_registry import get_agent
        
        agent = get_agent("vendor_management")
        if not agent:
            logger.warning("⚠ Vendor management agent not available")
            return False
        
        # Test basic vendor search
        logger.info("Testing vendor management agent...")
        result = agent.execute({
            "action": "vendor_search",
            "name": "CloudServe"
        })
        
        if result.get("success"):
            logger.info(f"✓ Agent execution successful")
            logger.info(f"  Result keys: {list(result.keys())}")
        else:
            logger.warning(f"⚠ Agent returned: {result}")
        
        return True
    except Exception as e:
        logger.warning(f"⚠ Sample request test skipped: {e}")
        return True  # Non-critical


def print_summary():
    """Print initialization summary."""
    logger.info("\n" + "=" * 80)
    logger.info("INITIALIZATION COMPLETE")
    logger.info("=" * 80)
    
    logger.info("""
✓ PilotH system is ready!

Next steps:
1. Start the API server:
   make run
   
2. In another terminal, test the API:
   curl http://localhost:8000/health
   
3. Try a vendor search:
   curl -X POST http://localhost:8000/agents/vendor_management/run \\
     -H "Content-Type: application/json" \\
     -d '{"action":"find_best","service_tags":["cloud"],"budget_usd":50000}'
   
4. Check the knowledge base:
   curl http://localhost:8000/kb
   
5. View interactive simulations:
   curl http://localhost:8000/reports/simulations
   
6. Get an agreement expiry report:
   curl http://localhost:8000/reports/agreements/expiry

Documentation: See README.md for full API documentation.

Key Features Initialized:
• Multi-Agent Orchestration (Vendor Management, Communication)
• Human-in-the-Loop (HITL) Approval System
• Knowledge Base with Vector DB (ChromaDB)
• Agreement Expiry Notifications (60, 45, 30, 15, 10 day triggers)
• Comprehensive Reporting (Performance, Compliance, Financial)
• Interactive Simulations (Contract Negotiation, SLA Violations, Budget Planning)
• New Vendor Tools:
  - Agreement Expiry Tracker
  - Vendor Risk Assessment
  - Financial Analysis
  - Knowledge Base Search
    """)


def main():
    """Run all initialization steps."""
    logger.info("╔" + "=" * 78 + "╗")
    logger.info("║" + " " * 78 + "║")
    logger.info("║" + "  PILOTH SYSTEM INITIALIZATION".center(78) + "║")
    logger.info("║" + "  Enterprise Multi-Agent AI Orchestration".center(78) + "║")
    logger.info("║" + " " * 78 + "║")
    logger.info("╚" + "=" * 78 + "╝")
    
    steps = [
        ("Database", init_database),
        ("Knowledge Base", init_knowledge_base),
        ("Agents & Tools", init_agents),
        ("Notifications", init_notifications),
        ("Reports", init_reports),
        ("Simulations", init_simulations),
    ]
    
    results = []
    for name, step_fn in steps:
        try:
            success = step_fn()
            results.append((name, success))
        except Exception as e:
            logger.error(f"✗ {name} initialization failed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Check endpoints
    check_api_endpoints()
    
    # Test sample
    test_vendor_request()
    
    # Print summary
    print_summary()
    
    # Print results
    logger.info("\n" + "=" * 80)
    logger.info("INITIALIZATION RESULTS")
    logger.info("=" * 80)
    
    all_success = True
    for name, success in results:
        status = "✓" if success else "✗"
        logger.info(f"{status} {name}: {'OK' if success else 'FAILED'}")
        if not success:
            all_success = False
    
    logger.info("=" * 80)
    
    if all_success:
        logger.info("✓ All systems initialized successfully!")
        return 0
    else:
        logger.warning("⚠ Some systems failed to initialize. Check logs above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
