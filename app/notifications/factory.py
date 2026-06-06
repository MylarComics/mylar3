"""
Notification factory.

Returns an AppriseNotifier instance when APPRISE_URLS is configured,
or None when no URLs are set (silently skips all notifications).
"""
from typing import Optional

from app.core.config import settings
from app.notifications.base import BaseNotifier
from app.notifications.apprise_notifier import AppriseNotifier


def get_notifier() -> Optional[BaseNotifier]:
    """
    Factory function returning a configured notifier instance.

    Returns None when APPRISE_URLS is empty, allowing callers to
    short-circuit with a simple `if notifier:` check.
    """
    if not settings.APPRISE_URLS.strip():
        return None
    return AppriseNotifier()
