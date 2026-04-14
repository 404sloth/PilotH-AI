from agents.vendor_management.tools.vendor_search import (
    VendorSearchTool,
    VendorSearchInput,
)
from agents.vendor_management.tools.contract_parser import (
    ContractParserTool,
    ContractParserInput,
)
from agents.vendor_management.tools.sla_monitor import SLAMonitorTool, SLAMonitorInput
from agents.vendor_management.tools.milestone_tracker import (
    MilestoneTrackerTool,
    MilestoneTrackerInput,
)

print("Testing Vendor Search:")
vs = VendorSearchTool()
vs_out = vs.execute(VendorSearchInput(vendor_name="Acme"))
print(vs_out.dict() if vs_out.found else "Not found")

print("\nTesting Contract Parser:")
cp = ContractParserTool()
cp_out = cp.execute(
    ContractParserInput(vendor_name="Acme", contract_reference="CTR-001")
)
print(cp_out.dict())

print("\nTesting SLA Monitor:")
sla = SLAMonitorTool()
sla_out = sla.execute(SLAMonitorInput(vendor_id="V-12345", period_days=30))
print(sla_out.dict() if sla_out.metrics else "No SLA metrics")

print("\nTesting Milestone Tracker:")
mt = MilestoneTrackerTool()
mt_out = mt.execute(MilestoneTrackerInput(vendor_id="V-12345"))
print(mt_out.dict() if mt_out.milestones else "No Milestones")
