from abc import ABC, abstractmethod


class BaseNotifier(ABC):
    """
    Abstract base class for notification backends.

    All implementations must support the async notify() method.
    notify_type maps to Apprise NotifyType values:
        "info", "success", "warning", "failure"
    """

    @abstractmethod
    async def notify(
        self,
        title: str,
        body: str,
        notify_type: str = "info",
    ) -> bool:
        """
        Send a notification with the given title and body.

        Returns True if all configured services accepted the message,
        False if any service failed or an exception occurred.
        """
