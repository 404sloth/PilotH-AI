"""
Vendor Performance Aggregator.

Computes historical performance metrics for vendors based on past projects,
including:
  - Quality trends (moving average)
  - On-time delivery rate
  - Cost efficiency
  - Client satisfaction scores
  - Risk metrics
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from observability.logger import get_logger
from observability.pii_sanitizer import sanitize_data

logger = get_logger("vendor.performance")


@dataclass
class PerformanceMetric:
    """A single performance metric."""
    metric_name: str
    value: float
    period: str  # daily, weekly, monthly, yearly, all_time
    timestamp: float
    confidence: float = 1.0  # 0-1, higher = more reliable
    

@dataclass
class VendorPerformanceProfile:
    """Complete performance profile for a vendor."""
    vendor_id: str
    vendor_name: str
    total_projects: int = 0
    avg_quality_score: float = 0.0
    on_time_delivery_rate: float = 0.0
    avg_cost_variance: float = 0.0  # % over/under budget
    avg_client_rating: float = 0.0
    sla_compliance_rate: float = 0.0
    risk_score: float = 0.0  # 0-100, higher = riskier
    
    # Trend metrics
    quality_trend: str = "stable"  # trending_up, trending_down, stable
    reliability_trend: str = "stable"
    satisfaction_trend: str = "stable"
    
    # Historical data
    recent_scores: List[float] = field(default_factory=list)
    recent_ratings: List[float] = field(default_factory=list)
    delayed_milestone_count: int = 0
    sla_breach_count: int = 0
    
    # Confidence indicators
    last_updated: float = 0.0
    data_points_count: int = 0
    confidence_score: float = 0.5
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "vendor_id": self.vendor_id,
            "vendor_name": self.vendor_name,
            "total_projects": self.total_projects,
            "avg_quality_score": round(self.avg_quality_score, 2),
            "on_time_delivery_rate": round(self.on_time_delivery_rate, 3),
            "avg_cost_variance": round(self.avg_cost_variance, 2),
            "avg_client_rating": round(self.avg_client_rating, 2),
            "sla_compliance_rate": round(self.sla_compliance_rate, 3),
            "risk_score": round(self.risk_score, 2),
            "quality_trend": self.quality_trend,
            "reliability_trend": self.reliability_trend,
            "satisfaction_trend": self.satisfaction_trend,
            "delayed_milestone_count": self.delayed_milestone_count,
            "sla_breach_count": self.sla_breach_count,
            "data_points_count": self.data_points_count,
            "confidence_score": round(self.confidence_score, 2),
        }


class VendorPerformanceAggregator:
    """Aggregates and computes vendor performance metrics."""

    def __init__(self):
        """Initialize aggregator."""
        self.cache = {}  # vendor_id -> VendorPerformanceProfile

    def compute_vendor_profile(
        self,
        vendor_id: str,
        vendor_name: str,
        db_connection=None,
    ) -> VendorPerformanceProfile:
        """
        Compute complete performance profile for a vendor.
        
        Args:
            vendor_id: The vendor identifier
            vendor_name: The vendor name
            db_connection: Optional database connection to fetch data
                
        Returns:
            VendorPerformanceProfile with aggregated metrics
        """
        
        # Check cache first
        if vendor_id in self.cache:
            cached = self.cache[vendor_id]
            # Refresh if older than 1 hour
            age_seconds = datetime.now().timestamp() - cached.last_updated
            if age_seconds < 3600:
                logger.debug(
                    f"Using cached profile for vendor {vendor_name}",
                    agent="vendor_performance",
                )
                return cached

        profile = VendorPerformanceProfile(
            vendor_id=vendor_id,
            vendor_name=vendor_name,
        )

        if db_connection:
            try:
                # Fetch project history
                projects = self._fetch_project_history(vendor_id, db_connection)
                profile = self._aggregate_project_metrics(profile, projects)
                
                # Compute trends
                profile = self._compute_trends(profile, projects)
                
                # Calculate risk score
                profile.risk_score = self._calculate_risk_score(profile)
                
                profile.last_updated = datetime.now().timestamp()
                self.cache[vendor_id] = profile
                
                logger.info(
                    f"Computed performance profile for vendor {vendor_name}",
                    agent="vendor_performance",
                    data={
                        "vendor_id": vendor_id,
                        "total_projects": profile.total_projects,
                        "avg_quality": profile.avg_quality_score,
                        "on_time_rate": profile.on_time_delivery_rate,
                    },
                )
                
            except Exception as e:
                logger.warning(
                    f"Failed to compute vendor profile: {e}",
                    agent="vendor_performance",
                    error=str(e),
                )

        return profile

    def _fetch_project_history(
        self,
        vendor_id: str,
        db_connection,
    ) -> List[Dict[str, Any]]:
        """Fetch project history for vendor from database."""
        try:
            cursor = db_connection.cursor()
            
            # Query projects with vendor involvement
            query = """
            SELECT 
                p.project_id,
                p.project_name,
                p.start_date,
                p.end_date,
                p.budget,
                p.actual_cost,
                p.quality_score,
                p.client_satisfaction,
                p.on_time,
                COUNT(DISTINCT m.milestone_id) as milestone_count,
                SUM(CASE WHEN m.status = 'delayed' THEN 1 ELSE 0 END) as delayed_count
            FROM projects p
            LEFT JOIN milestones m ON p.project_id = m.project_id
            LEFT JOIN project_vendors pv ON p.project_id = pv.project_id
            WHERE pv.vendor_id = ?
            GROUP BY p.project_id
            ORDER BY p.end_date DESC
            LIMIT 100
            """
            
            cursor.execute(query, (vendor_id,))
            columns = [col[0] for col in cursor.description]
            
            projects = []
            for row in cursor.fetchall():
                projects.append(dict(zip(columns, row)))
                
            return projects
            
        except Exception as e:
            logger.warning(
                f"Failed to fetch project history: {e}",
                agent="vendor_performance",
            )
            return []

    def _aggregate_project_metrics(
        self,
        profile: VendorPerformanceProfile,
        projects: List[Dict[str, Any]],
    ) -> VendorPerformanceProfile:
        """Aggregate metrics from all projects."""
        if not projects:
            return profile

        profile.total_projects = len(projects)
        
        # Collect scores and ratings
        quality_scores = []
        client_ratings = []
        cost_variances = []
        on_time_count = 0

        for project in projects:
            if project.get("quality_score"):
                quality_scores.append(project["quality_score"])
            
            if project.get("client_satisfaction"):
                client_ratings.append(project["client_satisfaction"])
            
            if project.get("on_time"):
                on_time_count += 1
            
            # Compute cost variance %
            budget = project.get("budget")
            actual = project.get("actual_cost")
            if budget and actual:
                variance = ((actual - budget) / budget) * 100
                cost_variances.append(variance)
            
            # Track delayed milestones
            delayed = project.get("delayed_count", 0)
            profile.delayed_milestone_count += delayed

        # Compute averages
        if quality_scores:
            profile.avg_quality_score = sum(quality_scores) / len(quality_scores)
            profile.recent_scores = quality_scores[-10:]  # Last 10

        if client_ratings:
            profile.avg_client_rating = sum(client_ratings) / len(client_ratings)
            profile.recent_ratings = client_ratings[-10:]  # Last 10

        if cost_variances:
            profile.avg_cost_variance = sum(cost_variances) / len(cost_variances)

        if profile.total_projects > 0:
            profile.on_time_delivery_rate = on_time_count / profile.total_projects

        # Data quality metrics
        profile.data_points_count = (
            len(quality_scores) + len(client_ratings) + len(cost_variances)
        )
        profile.confidence_score = min(1.0, profile.data_points_count / 30)

        return profile

    def _compute_trends(
        self,
        profile: VendorPerformanceProfile,
        projects: List[Dict[str, Any]],
    ) -> VendorPerformanceProfile:
        """Compute trend direction from recent data."""
        
        if len(projects) < 2:
            return profile

        # Sort by end date (most recent first)
        sorted_projects = sorted(
            projects,
            key=lambda p: p.get("end_date") or "",
            reverse=True
        )

        # Recent (last half) vs older (first half)
        mid = len(sorted_projects) // 2
        recent = sorted_projects[:mid]
        older = sorted_projects[mid:]

        # Quality trend
        recent_quality = [
            p.get("quality_score") for p in recent if p.get("quality_score")
        ]
        older_quality = [
            p.get("quality_score") for p in older if p.get("quality_score")
        ]

        if recent_quality and older_quality:
            recent_avg = sum(recent_quality) / len(recent_quality)
            older_avg = sum(older_quality) / len(older_quality)
            
            if recent_avg > older_avg + 5:
                profile.quality_trend = "trending_up"
            elif recent_avg < older_avg - 5:
                profile.quality_trend = "trending_down"
            else:
                profile.quality_trend = "stable"

        # Reliability trend (on-time rate)
        recent_ontime = sum(1 for p in recent if p.get("on_time"))
        older_ontime = sum(1 for p in older if p.get("on_time"))
        
        recent_rate = recent_ontime / len(recent) if recent else 0
        older_rate = older_ontime / len(older) if older else 0

        if recent_rate > older_rate + 0.1:
            profile.reliability_trend = "trending_up"
        elif recent_rate < older_rate - 0.1:
            profile.reliability_trend = "trending_down"
        else:
            profile.reliability_trend = "stable"

        # Satisfaction trend
        recent_ratings = [
            p.get("client_satisfaction") for p in recent
            if p.get("client_satisfaction")
        ]
        older_ratings = [
            p.get("client_satisfaction") for p in older
            if p.get("client_satisfaction")
        ]

        if recent_ratings and older_ratings:
            recent_avg = sum(recent_ratings) / len(recent_ratings)
            older_avg = sum(older_ratings) / len(older_ratings)
            
            if recent_avg > older_avg + 0.5:
                profile.satisfaction_trend = "trending_up"
            elif recent_avg < older_avg - 0.5:
                profile.satisfaction_trend = "trending_down"
            else:
                profile.satisfaction_trend = "stable"

        return profile

    def _calculate_risk_score(
        self,
        profile: VendorPerformanceProfile
    ) -> float:
        """
        Calculate composite risk score (0-100).
        Higher = riskier.
        """
        risk_factors = []

        # Quality risk (lower quality = higher risk)
        quality_risk = max(0, 100 - profile.avg_quality_score)
        risk_factors.append(("quality", quality_risk, 0.25))

        # Reliability risk (lower on-time rate = higher risk)
        reliability_risk = max(0, 100 - (profile.on_time_delivery_rate * 100))
        risk_factors.append(("reliability", reliability_risk, 0.25))

        # SLA compliance risk
        sla_risk = max(0, 100 - (profile.sla_compliance_rate * 100))
        risk_factors.append(("sla", sla_risk, 0.20))

        # Cost risk (high variance = higher risk)
        cost_risk = min(100, abs(profile.avg_cost_variance) / 2)
        risk_factors.append(("cost", cost_risk, 0.15))

        # Client satisfaction risk
        satisfaction_risk = max(0, 100 - (profile.avg_client_rating * 20))
        risk_factors.append(("satisfaction", satisfaction_risk, 0.15))

        # Compute weighted average
        total_risk = sum(risk * weight for _, risk, weight in risk_factors)

        logger.debug(
            f"Computed risk score",
            agent="vendor_performance",
            data={
                "vendor_id": profile.vendor_id,
                "risk_score": total_risk,
                "risk_factors": [
                    {"factor": name, "risk": round(risk, 1), "weight": weight}
                    for name, risk, weight in risk_factors
                ],
            },
        )

        return total_risk

    def compute_fit_score_enhancement(
        self,
        base_fit_score: float,
        vendor_id: str,
        vendor_name: str,
        db_connection=None,
        max_adjustment: float = 15.0,
    ) -> tuple:
        """
        Enhance base fit score with historical performance.
        
        Args:
            base_fit_score: The original vendor matcher fit score (0-100)
            vendor_id: The vendor identifier
            vendor_name: The vendor name
            db_connection: Database connection for history lookup
            max_adjustment: Max points to adjust score up/down
            
        Returns:
            (adjusted_fit_score, explanation, confidence)
        """
        
        profile = self.compute_vendor_profile(
            vendor_id, vendor_name, db_connection
        )

        # Start with base score
        adjusted_score = base_fit_score
        adjustments = []

        # Positive adjustments for good history
        if profile.avg_quality_score >= 85:
            bonus = min(5, (profile.avg_quality_score - 85) * 0.2)
            adjusted_score += bonus
            adjustments.append(f"+{bonus:.1f} for high quality history")

        if profile.on_time_delivery_rate >= 0.95:
            bonus = min(5, (profile.on_time_delivery_rate - 0.95) * 20)
            adjusted_score += bonus
            adjustments.append(f"+{bonus:.1f} for excellent on-time rate")

        if profile.avg_client_rating >= 4.5:
            bonus = min(5, (profile.avg_client_rating - 4.0) * 2)
            adjusted_score += bonus
            adjustments.append(f"+{bonus:.1f} for high client satisfaction")

        # Negative adjustments for poor history
        if profile.risk_score > 60:
            penalty = min(10, (profile.risk_score - 60) * 0.2)
            adjusted_score -= penalty
            adjustments.append(f"-{penalty:.1f} for elevated risk factors")

        if profile.quality_trend == "trending_down":
            penalty = min(5, abs(profile.recent_scores[0] - profile.recent_scores[-1]) * 0.1)
            adjusted_score -= penalty
            adjustments.append(f"-{penalty:.1f} for declining performance")

        # Clamp to 0-100
        adjusted_score = max(0, min(100, adjusted_score))

        explanation = "Adjustment factors: " + "; ".join(adjustments) if adjustments else "No historical adjustments"

        return adjusted_score, explanation, profile.confidence_score


# Global aggregator instance
_aggregator: Optional[VendorPerformanceAggregator] = None


def get_aggregator() -> VendorPerformanceAggregator:
    """Get or create the global aggregator."""
    global _aggregator
    if _aggregator is None:
        _aggregator = VendorPerformanceAggregator()
    return _aggregator
