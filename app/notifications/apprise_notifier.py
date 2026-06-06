"""
Apprise-based notification backend.

Parses APPRISE_URLS from settings (comma-separated list of Apprise URL
schemes) and delivers notifications asynchronously via apprise.Apprise.async_notify().

Example URLs:
    discord://webhook_id/webhook_token
    tgram://bot_token/chat_id
    slack://TokenA/TokenB/TokenC/
    mailto://user:pass@gmail.com
    ntfy://ntfy.sh/my_topic
    gotify://hostname/token

Full list: https://github.com/caronc/apprise/wiki
"""
from typing import List

import apprise

from app.core.config import settings
from app.core.logger import logger
from app.notifications.base import BaseNotifier

# Map our generic notify_type strings to Apprise NotifyType constants
_TYPE_MAP = {
    "info": apprise.NotifyType.INFO,
    "success": apprise.NotifyType.SUCCESS,
    "warning": apprise.NotifyType.WARNING,
    "failure": apprise.NotifyType.FAILURE,
}


class AppriseNotifier(BaseNotifier):
    """
    Notification backend using the Apprise library.
    Supports 70+ services via URL-scheme configuration.
    """

    def __init__(self) -> None:
        self._urls: List[str] = [
            url.strip()
            for url in settings.APPRISE_URLS.split(",")
            if url.strip()
        ]
        self._apobj: apprise.Apprise = apprise.Apprise()
        for url in self._urls:
            added = self._apobj.add(url)
            if not added:
                logger.warning(f"[Notifications] Apprise failed to load URL: {url!r}")

    async def notify(
        self,
        title: str,
        body: str,
        notify_type: str = "info",
    ) -> bool:
        """
        Send a notification to all configured Apprise services.

        Returns True on success (or when no URLs are configured — silent no-op),
        False if Apprise reports a delivery failure.
        """
        if not self._urls:
            logger.debug("[Notifications] No Apprise URLs configured — skipping notification.")
            return True

        apprise_type = _TYPE_MAP.get(notify_type, apprise.NotifyType.INFO)

        try:
            result = await self._apobj.async_notify(
                body=body,
                title=title,
                notify_type=apprise_type,
            )
            if result:
                logger.info(f"[Notifications] Sent '{title}' to {len(self._urls)} service(s).")
            else:
                logger.error(f"[Notifications] Apprise reported failure sending '{title}'.")
            return result
        except Exception as exc:
            logger.error(f"[Notifications] Exception while sending notification '{title}': {exc}")
            return False
