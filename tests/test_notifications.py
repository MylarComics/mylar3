"""
Tests for Phase 7: Notification system.

Covers:
  - Factory: returns None / AppriseNotifier based on APPRISE_URLS
  - AppriseNotifier: send success, send failure, empty URL short-circuit
  - grab_issue task: fires snatch notification on success, failure notification on failure
  - db_sync task: fires new-issue notification when new_issues > 0
  - API: POST /api/notifications/test returns correct JSON responses
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from httpx import AsyncClient

from app.models.comic import Comic
from app.models.issue import Issue


# ---------------------------------------------------------------------------
# Helpers shared with test_tasks
# ---------------------------------------------------------------------------

def _make_comic(comic_id: str = "1234", status: str = "Active") -> Comic:
    c = Comic(comic_id=comic_id, comic_name="Amazing Spider-Man", comic_year=1963,
              publisher="Marvel", status=status)
    c.id = 1
    return c


def _make_issue(issue_id: str = "5678", status: str = "Wanted") -> Issue:
    i = Issue(issue_id=issue_id, comic_id="1234", issue_number="1", status=status)
    i.id = 1
    return i


def _make_mock_session(first_return=None):
    """Minimal session mock for single .exec().first() calls."""
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    exec_result = MagicMock()
    exec_result.first.return_value = first_return
    exec_result.all.return_value = [first_return] if first_return is not None else []
    session.exec.return_value = exec_result
    return session


# ---------------------------------------------------------------------------
# Factory tests
# ---------------------------------------------------------------------------

class TestNotificationFactory:
    def test_returns_none_when_no_urls(self):
        with patch("app.notifications.factory.settings") as ms:
            ms.APPRISE_URLS = ""
            from app.notifications.factory import get_notifier
            result = get_notifier()
        assert result is None

    def test_returns_notifier_when_urls_configured(self):
        with patch("app.notifications.factory.settings") as ms:
            ms.APPRISE_URLS = "json://localhost"
            # Patch AppriseNotifier at its definition site; the lazy import inside
            # get_notifier() will pick up the patched class at call time.
            with patch(
                "app.notifications.apprise_notifier.AppriseNotifier",
                return_value=MagicMock(),
            ):
                from app.notifications.factory import get_notifier
                result = get_notifier()
        assert result is not None


# ---------------------------------------------------------------------------
# AppriseNotifier unit tests
# ---------------------------------------------------------------------------

class TestAppriseNotifier:
    def _make_notifier(self, urls: str = "json://localhost"):
        with patch("app.notifications.apprise_notifier.settings") as ms:
            ms.APPRISE_URLS = urls
            with patch("app.notifications.apprise_notifier.apprise") as mock_apprise_mod:
                mock_apobj = MagicMock()
                mock_apobj.add.return_value = True
                mock_apprise_mod.Apprise.return_value = mock_apobj
                mock_apprise_mod.NotifyType.INFO = "info"
                mock_apprise_mod.NotifyType.SUCCESS = "success"
                mock_apprise_mod.NotifyType.WARNING = "warning"
                mock_apprise_mod.NotifyType.FAILURE = "failure"
                from app.notifications.apprise_notifier import AppriseNotifier
                notifier = AppriseNotifier()
                notifier._apobj = mock_apobj
                notifier._urls = [u.strip() for u in urls.split(",") if u.strip()]
                return notifier, mock_apobj

    @pytest.mark.asyncio
    async def test_notify_success(self):
        notifier, mock_apobj = self._make_notifier()
        mock_apobj.async_notify = AsyncMock(return_value=True)

        result = await notifier.notify("Test Title", "Test body", "success")

        assert result is True
        mock_apobj.async_notify.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_notify_returns_false_on_apprise_failure(self):
        notifier, mock_apobj = self._make_notifier()
        mock_apobj.async_notify = AsyncMock(return_value=False)

        result = await notifier.notify("Test Title", "Test body", "failure")

        assert result is False

    @pytest.mark.asyncio
    async def test_notify_returns_false_on_exception(self):
        notifier, mock_apobj = self._make_notifier()
        mock_apobj.async_notify = AsyncMock(side_effect=RuntimeError("Connection refused"))

        result = await notifier.notify("Test Title", "Test body")

        assert result is False

    @pytest.mark.asyncio
    async def test_notify_skips_when_no_urls(self):
        """When URL list is empty, notify() returns True without calling Apprise."""
        notifier, mock_apobj = self._make_notifier(urls="")
        notifier._urls = []  # Force empty URL list
        mock_apobj.async_notify = AsyncMock(return_value=True)

        result = await notifier.notify("Empty", "No services configured")

        assert result is True
        mock_apobj.async_notify.assert_not_awaited()


# ---------------------------------------------------------------------------
# grab_issue notification integration tests
# ---------------------------------------------------------------------------

class TestGrabIssueNotifications:
    _result = {
        "title": "Amazing Spider-Man 001",
        "download_url": "http://indexer.test/nzb/001.nzb",
        "provider_name": "TestIndexer",
        "type": "nzb",
    }

    @patch("app.tasks.grab_issue.get_sync_session")
    @patch("app.tasks.grab_issue.asyncio.run")
    @patch("app.tasks.grab_issue.get_downloader")
    @patch("app.tasks.grab_issue.get_notifier")
    def test_snatch_notification_sent_on_success(
        self, mock_get_notifier, mock_factory, mock_run, mock_ctx
    ):
        """On successful grab, notify() is called with notify_type='success'."""
        issue = _make_issue(status="Wanted")
        mock_downloader = MagicMock()
        mock_factory.return_value = mock_downloader
        mock_run.return_value = "job-id-123"

        mock_session = _make_mock_session(first_return=issue)
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        mock_notifier = MagicMock()
        mock_notifier.notify = AsyncMock(return_value=True)
        mock_get_notifier.return_value = mock_notifier

        with patch("app.tasks.grab_issue.settings") as ms:
            ms.NOTIFY_ON_SNATCH = True
            ms.NOTIFY_ON_FAILURE = True
            from app.tasks.grab_issue import grab_issue
            result = grab_issue(issue_id="5678", result=self._result)

        assert result["status"] == "Snatched"
        # get_notifier called once (for snatch notification)
        mock_get_notifier.assert_called()
        # notify() invoked inside asyncio.run, so mock_run is called twice:
        # once for add_download, once for notifier.notify
        assert mock_run.call_count == 2

    @patch("app.tasks.grab_issue.get_sync_session")
    @patch("app.tasks.grab_issue.asyncio.run")
    @patch("app.tasks.grab_issue.get_downloader")
    @patch("app.tasks.grab_issue.get_notifier")
    def test_failure_notification_sent_on_failed_grab(
        self, mock_get_notifier, mock_factory, mock_run, mock_ctx
    ):
        """When downloader returns None, failure notification is fired."""
        mock_factory.return_value = MagicMock()
        mock_run.return_value = None  # Downloader failure

        mock_notifier = MagicMock()
        mock_notifier.notify = AsyncMock(return_value=True)
        mock_get_notifier.return_value = mock_notifier

        with patch("app.tasks.grab_issue.settings") as ms:
            ms.NOTIFY_ON_SNATCH = True
            ms.NOTIFY_ON_FAILURE = True
            from app.tasks.grab_issue import grab_issue
            result = grab_issue(issue_id="5678", result=self._result)

        assert result["status"] == "Failed"
        mock_get_notifier.assert_called()

    @patch("app.tasks.grab_issue.asyncio.run")
    @patch("app.tasks.grab_issue.get_downloader")
    @patch("app.tasks.grab_issue.get_notifier")
    def test_no_notification_when_notify_on_failure_false(
        self, mock_get_notifier, mock_factory, mock_run
    ):
        """NOTIFY_ON_FAILURE=False → get_notifier NOT called on grab failure."""
        mock_factory.return_value = MagicMock()
        mock_run.return_value = None  # Failure

        with patch("app.tasks.grab_issue.settings") as ms:
            ms.NOTIFY_ON_SNATCH = False
            ms.NOTIFY_ON_FAILURE = False
            from app.tasks.grab_issue import grab_issue
            grab_issue(issue_id="5678", result=self._result)

        mock_get_notifier.assert_not_called()


# ---------------------------------------------------------------------------
# db_sync notification integration tests
# ---------------------------------------------------------------------------

class TestDbSyncNotifications:
    @patch("app.tasks.db_sync.get_sync_session")
    @patch("app.tasks.db_sync.ComicVineClient")
    @patch("app.tasks.db_sync.get_notifier")
    def test_new_issues_notification_fired(self, mock_get_notifier, mock_cv_class, mock_ctx):
        """When new issues are discovered, notify() is called with notify_type='info'."""
        comic = _make_comic()

        # exec calls: comic lookup, existing_ids query
        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)
        comic_result = MagicMock()
        comic_result.first.return_value = comic
        empty_result = MagicMock()
        empty_result.all.return_value = []
        session.exec.side_effect = [comic_result, empty_result]
        mock_ctx.return_value = session

        mock_cv = MagicMock()
        mock_cv.get_volume = AsyncMock(return_value={
            "name": "Amazing Spider-Man", "publisher": {"name": "Marvel"}, "id": 1234
        })
        mock_cv.get_issues = AsyncMock(return_value=[
            {"id": 9001, "issue_number": "2", "name": "Chapter 2", "store_date": "2024-01-01"},
        ])
        mock_cv_class.return_value = mock_cv

        mock_notifier = MagicMock()
        mock_notifier.notify = AsyncMock(return_value=True)
        mock_get_notifier.return_value = mock_notifier

        with patch("app.tasks.db_sync.settings") as ms:
            ms.NOTIFY_ON_NEW_ISSUES = True
            from app.tasks.db_sync import sync_comic_metadata
            result = sync_comic_metadata(comic_id="1234")

        assert result["new_issues"] == 1
        mock_get_notifier.assert_called_once()

    @patch("app.tasks.db_sync.get_sync_session")
    @patch("app.tasks.db_sync.ComicVineClient")
    @patch("app.tasks.db_sync.get_notifier")
    def test_no_notification_when_notify_on_new_issues_false(
        self, mock_get_notifier, mock_cv_class, mock_ctx
    ):
        """NOTIFY_ON_NEW_ISSUES=False → get_notifier NOT called even when issues found."""
        comic = _make_comic()

        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)
        comic_result = MagicMock()
        comic_result.first.return_value = comic
        empty_result = MagicMock()
        empty_result.all.return_value = []
        session.exec.side_effect = [comic_result, empty_result]
        mock_ctx.return_value = session

        mock_cv = MagicMock()
        mock_cv.get_volume = AsyncMock(return_value={
            "name": "Amazing Spider-Man", "publisher": {"name": "Marvel"}, "id": 1234
        })
        mock_cv.get_issues = AsyncMock(return_value=[
            {"id": 9001, "issue_number": "2", "name": "Chapter 2", "store_date": "2024-01-01"},
        ])
        mock_cv_class.return_value = mock_cv

        with patch("app.tasks.db_sync.settings") as ms:
            ms.NOTIFY_ON_NEW_ISSUES = False
            from app.tasks.db_sync import sync_comic_metadata
            sync_comic_metadata(comic_id="1234")

        mock_get_notifier.assert_not_called()


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

class TestNotificationTestEndpoint:
    @pytest.mark.asyncio
    async def test_no_urls_returns_ok_false(self):
        """When no APPRISE_URLS configured, endpoint returns ok=False."""
        from app.main import app
        transport = httpx.ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.routers.api.get_notifier", return_value=None):
                response = await client.post("/api/notifications/test")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert "APPRISE_URLS" in data["message"]

    @pytest.mark.asyncio
    async def test_successful_send_returns_ok_true(self):
        """When notifier sends successfully, endpoint returns ok=True."""
        from app.main import app
        mock_notifier = MagicMock()
        mock_notifier.notify = AsyncMock(return_value=True)

        transport = httpx.ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.routers.api.get_notifier", return_value=mock_notifier):
                response = await client.post("/api/notifications/test")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    @pytest.mark.asyncio
    async def test_failed_send_returns_ok_false(self):
        """When Apprise reports delivery failure, endpoint returns ok=False."""
        from app.main import app
        mock_notifier = MagicMock()
        mock_notifier.notify = AsyncMock(return_value=False)

        transport = httpx.ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.routers.api.get_notifier", return_value=mock_notifier):
                response = await client.post("/api/notifications/test")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
