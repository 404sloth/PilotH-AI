"""
Agreement Expiry Notification System

Features:
  - Monitor agreement expiry dates
  - Send notifications at configured intervals (60, 45, 30, 15, 10 days)
  - Track notification status to avoid duplicates
  - Integration with WebSocket for real-time alerts
  - Email/Slack integration ready
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class NotificationLevel(str, Enum):
    """Notification priority levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AgreementExpiryNotifier:
    """Monitor and notify about expiring agreements."""
    
    # Default notification triggers (days before expiry)
    DEFAULT_TRIGGERS = [60, 45, 30, 15, 10, 5, 1]
    
    def __init__(self):
        """Initialize notifier."""
        self.triggers = self.DEFAULT_TRIGGERS
        self._sent_notifications: Dict[str, set] = {}  # agreement_id -> set of sent_day_offsets
    
    def should_notify(
        self,
        agreement_id: str,
        expiry_date: datetime,
        current_date: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Check if an agreement should trigger a notification.
        
        Returns:
            Notification dict if triggered, None otherwise
        """
        current_date = current_date or datetime.now()
        days_remaining = (expiry_date - current_date).days
        
        # Initialize tracking for this agreement
        if agreement_id not in self._sent_notifications:
            self._sent_notifications[agreement_id] = set()
        
        # Check if we should notify based on configured triggers
        for trigger_days in self.triggers:
            if days_remaining <= trigger_days and trigger_days not in self._sent_notifications[agreement_id]:
                # Determine notification level based on urgency
                if days_remaining <= 5:
                    level = NotificationLevel.CRITICAL
                elif days_remaining <= 15:
                    level = NotificationLevel.WARNING
                else:
                    level = NotificationLevel.INFO
                
                # Mark as sent
                self._sent_notifications[agreement_id].add(trigger_days)
                
                return {
                    "agreement_id": agreement_id,
                    "days_remaining": days_remaining,
                    "trigger_days": trigger_days,
                    "level": level,
                    "message": self._generate_message(days_remaining),
                    "timestamp": current_date.isoformat(),
                }
        
        return None
    
    def _generate_message(self, days_remaining: int) -> str:
        """Generate a human-readable message based on days remaining."""
        if days_remaining <= 0:
            return "Agreement has expired!"
        elif days_remaining == 1:
            return "Agreement expires TOMORROW!"
        elif days_remaining <= 5:
            return f"Agreement expires in {days_remaining} days - IMMEDIATE ACTION REQUIRED"
        elif days_remaining <= 15:
            return f"Agreement expires in {days_remaining} days - Review and prepare renewal"
        else:
            return f"Agreement expires in {days_remaining} days"
    
    def batch_check_agreements(
        self,
        agreements: List[Dict[str, Any]],
        current_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Check multiple agreements and return all that need notifications.
        
        Expected agreement dict keys:
        - id: unique identifier
        - expiry_date: ISO format date string or datetime
        - vendor: vendor name
        - name: agreement name
        """
        notifications = []
        current_date = current_date or datetime.now()
        
        for agreement in agreements:
            # Parse expiry date
            if isinstance(agreement.get("expiry_date"), str):
                expiry_date = datetime.fromisoformat(agreement["expiry_date"])
            else:
                expiry_date = agreement.get("expiry_date")
            
            if not expiry_date:
                continue
            
            # Check if notification should be sent
            notif = self.should_notify(
                agreement_id=agreement["id"],
                expiry_date=expiry_date,
                current_date=current_date,
            )
            
            if notif:
                # Enrich with agreement details
                notif.update({
                    "vendor": agreement.get("vendor", "Unknown"),
                    "agreement_name": agreement.get("name", "Unknown"),
                    "renewal_terms": agreement.get("renewal_terms", "Unknown"),
                })
                notifications.append(notif)
        
        return notifications


class NotificationStore:
    """Persist and track sent notifications."""
    
    def __init__(self):
        """Initialize notification store."""
        self._notifications: List[Dict[str, Any]] = []
    
    def record(self, notification: Dict[str, Any]) -> None:
        """Record a sent notification."""
        notification["recorded_at"] = datetime.now().isoformat()
        notification["status"] = "sent"
        self._notifications.append(notification)
        logger.info(
            f"[EXPIRY] Recorded notification for {notification['agreement_id']}: "
            f"{notification['days_remaining']} days remaining"
        )
    
    def get_history(
        self,
        agreement_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get notification history."""
        history = self._notifications
        if agreement_id:
            history = [n for n in history if n.get("agreement_id") == agreement_id]
        return history[-limit:]
    
    def get_pending_actions(self) -> List[Dict[str, Any]]:
        """Get agreements that need immediate action."""
        return [n for n in self._notifications if n.get("level") in [NotificationLevel.CRITICAL, NotificationLevel.WARNING]]


# ── Singleton ─────────────────────────────────────────────────────────────────

_notifier: Optional[AgreementExpiryNotifier] = None
_store: Optional[NotificationStore] = None


def get_expiry_notifier() -> AgreementExpiryNotifier:
    """Get the global expiry notifier instance."""
    global _notifier
    if _notifier is None:
        _notifier = AgreementExpiryNotifier()
    return _notifier


def get_notification_store() -> NotificationStore:
    """Get the global notification store instance."""
    global _store
    if _store is None:
        _store = NotificationStore()
    return _store


def test_scenario() -> None:
    """Test the notification system with scenarios."""
    import sys
    
    notifier = get_expiry_notifier()
    store = get_notification_store()
    
    # Test data - agreements with various expiry dates
    today = datetime.now()
    test_agreements = [
        {
            "id": "agr_001",
            "name": "CloudServe - Infrastructure",
            "vendor": "CloudServe Inc.",
            "expiry_date": (today + timedelta(days=45)).isoformat(),
            "renewal_terms": "Auto-renewal 12 months"
        },
        {
            "id": "agr_002",
            "name": "TechVendor - Analytics",
            "vendor": "TechVendor Solutions",
            "expiry_date": (today + timedelta(days=8)).isoformat(),
            "renewal_terms": "Manual renewal"
        },
        {
            "id": "agr_003",
            "name": "SecureNet - Security",
            "vendor": "SecureNet Inc.",
            "expiry_date": (today + timedelta(days=2)).isoformat(),
            "renewal_terms": "Auto-renewal 12 months"
        },
        {
            "id": "agr_004",
            "name": "OldVendor - Legacy Service",
            "vendor": "OldVendor Corp",
            "expiry_date": (today - timedelta(days=5)).isoformat(),
            "renewal_terms": "Expired - needs review"
        },
    ]
    
    print("=" * 80)
    print("AGREEMENT EXPIRY NOTIFICATION TEST")
    print("=" * 80)
    print(f"Current Date: {today.strftime('%Y-%m-%d')}\n")
    
    notifications = notifier.batch_check_agreements(test_agreements, current_date=today)
    
    print(f"Found {len(notifications)} agreements requiring attention:\n")
    
    for notif in notifications:
        print(f"[{notif['level'].value.upper()}] {notif['agreement_name']}")
        print(f"  Vendor: {notif['vendor']}")
        print(f"  Days Remaining: {notif['days_remaining']}")
        print(f"  Message: {notif['message']}")
        print(f"  Renewal Terms: {notif['renewal_terms']}")
        print()
        
        # Record in store
        store.record(notif)
    
    print("=" * 80)
    print(f"Notification History ({len(store.get_history())} total):")
    print("=" * 80)
    for hist in store.get_history():
        print(f"- {hist['agreement_id']}: {hist['days_remaining']} days "
              f"({hist['level'].value}) - {hist['recorded_at']}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    )
    test_scenario()
