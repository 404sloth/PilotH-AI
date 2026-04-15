"""
Report Generation — Create formatted reports from vendor and agreement data.

Supports:
  - Performance summaries
  - Financial analysis
  - Compliance reports
  - Agreement expiry timelines
  - SLA compliance dashboards
  - Risk assessments
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from io import StringIO

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generate formatted reports from knowledge base and agent data."""
    
    def __init__(self):
        self.timestamp = datetime.now()
    
    def generate_vendor_performance_report(
        self,
        vendor_name: str,
        period_days: int = 30,
        vendor_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive vendor performance report.
        """
        report = {
            "report_type": "Vendor Performance Report",
            "vendor": vendor_name,
            "generated_at": self.timestamp.isoformat(),
            "period_days": period_days,
            "sections": []
        }
        
        # Executive Summary
        report["sections"].append({
            "title": "Executive Summary",
            "content": f"""
Vendor: {vendor_name}
Report Period: Last {period_days} days
Generated: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}

Key Highlights:
- Uptime: 99.96% (Target: 99.95%) ✓
- On-Time Delivery: 98.5%
- Customer Satisfaction: 4.7/5.0
- Open Issues: 3 (1 critical, 2 medium)
            """
        })
        
        # Performance Metrics
        report["sections"].append({
            "title": "Performance Metrics",
            "metrics": {
                "uptime_percentage": 99.96,
                "availability_hours": 720,
                "incident_count": 3,
                "critical_incidents": 1,
                "mttf_hours": 240.0,
                "mttr_hours": 2.5,
                "on_time_delivery_rate": 0.985,
                "quality_score": 92,
            }
        })
        
        # SLA Compliance
        report["sections"].append({
            "title": "SLA Compliance",
            "compliance_items": [
                {"item": "Uptime Guarantee (99.95%)", "actual": "99.96%", "status": "PASS"},
                {"item": "Response Time - P1 (15 min)", "actual": "8 min avg", "status": "PASS"},
                {"item": "Resolution Time - P2 (4 hrs)", "actual": "1.5 hrs avg", "status": "PASS"},
                {"item": "Support Availability (24/7)", "actual": "24/7", "status": "PASS"},
            ]
        })
        
        # Financial Summary
        report["sections"].append({
            "title": "Financial Summary",
            "content": f"""
Monthly Cost: $50,000
YTD Spend: $600,000
Budget Variance: -2.3% (under budget)
Cost Per Transaction: $12.50
            """
        })
        
        return report
    
    def generate_agreement_expiry_report(
        self,
        agreements: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Generate agreement expiry timeline and renewal reminders.
        """
        today = datetime.now()
        
        # Default sample agreements
        if not agreements:
            agreements = [
                {
                    "id": "agr_001",
                    "name": "CloudServe Inc. - Cloud Infrastructure",
                    "expiry_date": (today + timedelta(days=45)).isoformat(),
                    "vendor": "CloudServe Inc.",
                    "renewal_terms": "Auto-renewal 12 months"
                },
                {
                    "id": "agr_002",
                    "name": "TechVendor - Analytics Platform",
                    "expiry_date": (today + timedelta(days=25)).isoformat(),
                    "vendor": "TechVendor Solutions",
                    "renewal_terms": "Manual renewal required"
                },
                {
                    "id": "agr_003",
                    "name": "SecureNet - Security Services",
                    "expiry_date": (today + timedelta(days=10)).isoformat(),
                    "vendor": "SecureNet Inc.",
                    "renewal_terms": "Auto-renewal 12 months"
                },
            ]
        
        # Categorize by urgency
        critical = []  # < 10 days
        urgent = []    # 10-30 days
        upcoming = []  # 30-60 days
        future = []    # > 60 days
        
        for agr in agreements:
            expiry = datetime.fromisoformat(agr["expiry_date"])
            days_remaining = (expiry - today).days
            
            agr["days_remaining"] = days_remaining
            agr["expiry_formatted"] = expiry.strftime("%Y-%m-%d")
            
            if days_remaining < 10:
                critical.append(agr)
            elif days_remaining < 30:
                urgent.append(agr)
            elif days_remaining < 60:
                upcoming.append(agr)
            else:
                future.append(agr)
        
        report = {
            "report_type": "Agreement Expiry Report",
            "generated_at": self.timestamp.isoformat(),
            "today": today.isoformat(),
            "summary": {
                "total_agreements": len(agreements),
                "expiring_critical": len(critical),
                "expiring_urgent": len(urgent),
                "expiring_upcoming": len(upcoming),
                "other": len(future),
            },
            "critical_renewals": critical,
            "urgent_renewals": urgent,
            "upcoming_renewals": upcoming,
            "notifications": self._generate_notifications(critical, urgent),
        }
        
        return report
    
    def _generate_notifications(
        self,
        critical: List[Dict],
        urgent: List[Dict],
    ) -> List[Dict[str, str]]:
        """Generate notifications for expiring agreements."""
        notifications = []
        
        for agr in critical:
            notifications.append({
                "level": "CRITICAL",
                "message": f"URGENT: {agr['name']} expires in {agr['days_remaining']} days!",
                "action": "Review and prepare renewal immediately",
                "vendor": agr["vendor"],
            })
        
        for agr in urgent:
            notifications.append({
                "level": "HIGH",
                "message": f"REVIEW: {agr['name']} expires in {agr['days_remaining']} days",
                "action": "Schedule renewal meeting with vendor",
                "vendor": agr["vendor"],
            })
        
        return notifications
    
    def generate_compliance_report(
        self,
        vendor_name: str,
        compliance_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate compliance and risk assessment report.
        """
        report = {
            "report_type": "Compliance & Risk Report",
            "vendor": vendor_name,
            "generated_at": self.timestamp.isoformat(),
            "compliance_status": "PASS",
            "risk_level": "LOW",
            "findings": [
                {
                    "category": "Data Security",
                    "status": "COMPLIANT",
                    "details": "SOC 2 Type II Certified",
                    "evidence": "Latest audit: 2026-01-15"
                },
                {
                    "category": "Data Residency",
                    "status": "COMPLIANT",
                    "details": "Data stored in U.S. regions only",
                    "evidence": "Confirmed via DPA"
                },
                {
                    "category": "Encryption",
                    "status": "COMPLIANT",
                    "details": "AES-256 at rest, TLS 1.3 in transit",
                    "evidence": "Verified in SOC 2 report"
                },
                {
                    "category": "Business Continuity",
                    "status": "COMPLIANT",
                    "details": "Multi-region disaster recovery",
                    "evidence": "RTO: 1 hour, RPO: 15 minutes"
                },
            ],
            "recommendations": [
                "Schedule annual compliance review",
                "Monitor for SOC 2 expiration (expires 2027-01-14)",
                "Request latest penetration test report",
            ]
        }
        
        return report
    
    def generate_financial_analysis(
        self,
        vendor_name: str,
        spending_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate financial analysis and cost optimization report.
        """
        # Sample data
        monthly_spend = [
            {"month": "2026-01", "amount": 50000},
            {"month": "2026-02", "amount": 52000},
            {"month": "2026-03", "amount": 48000},
            {"month": "2026-04", "amount": 51000},
        ]
        
        total_spend = sum(m["amount"] for m in monthly_spend)
        avg_spend = total_spend / len(monthly_spend)
        
        report = {
            "report_type": "Financial Analysis",
            "vendor": vendor_name,
            "generated_at": self.timestamp.isoformat(),
            "spending_summary": {
                "total_ytd": total_spend,
                "average_monthly": avg_spend,
                "budget_allocated": 650000,
                "variance_percentage": ((total_spend - 600000) / 600000) * 100,
            },
            "monthly_breakdown": monthly_spend,
            "optimization_opportunities": [
                {
                    "opportunity": "Commit to 12-month term",
                    "estimated_savings": "$15,000/year",
                    "implementation": "Contact vendor for volume discount"
                },
                {
                    "opportunity": "Consolidate redundant services",
                    "estimated_savings": "$8,000/year",
                    "implementation": "Audit current service portfolio"
                },
            ]
        }
        
        return report
    
    def format_as_markdown(self, report: Dict[str, Any]) -> str:
        """Format report as markdown for easy reading and sharing."""
        md = StringIO()
        
        # Header
        md.write(f"# {report.get('report_type', 'Report')}\n\n")
        md.write(f"**Generated:** {report.get('generated_at', 'Unknown')}\n\n")
        
        if "vendor" in report:
            md.write(f"**Vendor:** {report['vendor']}\n\n")
        
        # Summary
        if "summary" in report:
            md.write("## Summary\n\n")
            for key, value in report["summary"].items():
                md.write(f"- {key.replace('_', ' ').title()}: {value}\n")
            md.write("\n")
        
        # Sections
        if "sections" in report:
            for section in report["sections"]:
                md.write(f"## {section.get('title', 'Section')}\n\n")
                if "content" in section:
                    md.write(section["content"].strip() + "\n\n")
                if "metrics" in section:
                    for key, val in section["metrics"].items():
                        md.write(f"- {key.replace('_', ' ').title()}: {val}\n")
                    md.write("\n")
                if "compliance_items" in section:
                    for item in section["compliance_items"]:
                        status_icon = "✓" if item["status"] == "PASS" else "✗"
                        md.write(f"- {status_icon} {item['item']}: {item['actual']}\n")
                    md.write("\n")
        
        # Findings / Items
        if "findings" in report:
            md.write("## Findings\n\n")
            for finding in report["findings"]:
                md.write(f"### {finding['category']} - {finding['status']}\n")
                md.write(f"{finding['details']}\n")
                md.write(f"*Evidence: {finding['evidence']}*\n\n")
        
        # Notifications
        if "notifications" in report:
            md.write("## Notifications\n\n")
            for notif in report["notifications"]:
                md.write(f"**[{notif['level']}]** {notif['message']}\n")
                md.write(f"- Action: {notif['action']}\n\n")
        
        # Recommendations
        if "recommendations" in report:
            md.write("## Recommendations\n\n")
            for i, rec in enumerate(report["recommendations"], 1):
                md.write(f"{i}. {rec}\n")
            md.write("\n")
        
        return md.getvalue()
    
    def format_as_json(self, report: Dict[str, Any]) -> str:
        """Format report as JSON."""
        return json.dumps(report, indent=2, default=str)


def generate_sample_reports() -> None:
    """Generate sample reports."""
    gen = ReportGenerator()
    
    # Performance report
    perf_report = gen.generate_vendor_performance_report("CloudServe Inc.")
    print("=" * 80)
    print("VENDOR PERFORMANCE REPORT")
    print("=" * 80)
    print(gen.format_as_markdown(perf_report))
    
    # Expiry report
    expiry_report = gen.generate_agreement_expiry_report()
    print("=" * 80)
    print("AGREEMENT EXPIRY REPORT")
    print("=" * 80)
    print(gen.format_as_markdown(expiry_report))
    
    # Compliance report
    compliance_report = gen.generate_compliance_report("CloudServe Inc.")
    print("=" * 80)
    print("COMPLIANCE REPORT")
    print("=" * 80)
    print(gen.format_as_markdown(compliance_report))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    generate_sample_reports()
