"""
Tests for Celery tasks: search_wanted, grab_issue, sync_comic_metadata.

All database interactions are mocked via get_sync_session to avoid needing
a live Postgres connection in the test environment. Celery tasks are called
directly (not via .delay()) so they run synchronously inline.
"""
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.models.comic import Comic
from app.models.issue import Issue
from app.services.search import SearchResultItem


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

def _make_comic(
    comic_id: str = "1234",
    name: str = "Amazing Spider-Man",
    year: int = 1963,
    status: str = "Active",
) -> Comic:
    c = Comic(
        comic_id=comic_id,
        comic_name=name,
        comic_year=year,
        publisher="Marvel",
        status=status,
    )
    c.id = 1
    return c


def _make_issue(
    issue_id: str = "5678",
    comic_id: str = "1234",
    issue_number: str = "1",
    status: str = "Wanted",
) -> Issue:
    i = Issue(
        issue_id=issue_id,
        comic_id=comic_id,
        issue_number=issue_number,
        status=status,
    )
    i.id = 1
    return i


def _make_search_result(title: str = "Amazing Spider-Man 001") -> SearchResultItem:
    return SearchResultItem(
        title=title,
        download_url="http://indexer.test/nzb/001.nzb",
        size=50_000_000,
        provider_name="TestIndexer",
        type="nzb",
    )


def _make_mock_session(exec_side_effects: list):
    """
    Build a mock session whose .exec() calls return objects with .all() / .first()
    driven by exec_side_effects list. Each element is either a list (→ .all())
    or a single value (→ .first()).
    """
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)

    mock_results = []
    for effect in exec_side_effects:
        r = MagicMock()
        if isinstance(effect, list):
            r.all.return_value = effect
            r.first.return_value = effect[0] if effect else None
        else:
            r.first.return_value = effect
            r.all.return_value = [effect] if effect is not None else []
        mock_results.append(r)

    session.exec.side_effect = mock_results
    return session


# ---------------------------------------------------------------------------
# search_wanted tests
# ---------------------------------------------------------------------------

class TestSearchWanted:
    @patch("app.tasks.search_wanted.get_sync_session")
    def test_no_wanted_issues_returns_early(self, mock_ctx):
        """Empty Wanted list should return zero counts immediately."""
        mock_session = _make_mock_session([[]])  # exec → .all() → []
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        from app.tasks.search_wanted import search_wanted
        result = search_wanted()

        assert result == {"scanned": 0, "matched": 0, "grabbed": 0}

    @patch("app.tasks.search_wanted.get_sync_session")
    @patch("app.tasks.search_wanted.asyncio.run")
    @patch("app.tasks.grab_issue.grab_issue")  # patch on the owning module
    def test_found_match_dispatches_grab(self, mock_grab, mock_run, mock_ctx):
        """When search returns a result and GRAB_ON_MATCH=True, grab_issue.delay is called."""
        comic = _make_comic()
        issue = _make_issue()
        search_results = [_make_search_result()]

        mock_session = _make_mock_session([[issue], comic])
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        mock_run.return_value = search_results
        mock_grab.delay = MagicMock()

        # Patch the lazy import inside search_wanted so it receives our mock
        with patch("app.tasks.search_wanted.settings") as mock_settings, \
             patch("app.tasks.search_wanted.grab_issue", mock_grab):
            mock_settings.GRAB_ON_MATCH = True
            from app.tasks.search_wanted import search_wanted
            result = search_wanted()

        assert result["scanned"] == 1
        assert result["matched"] == 1
        assert result["grabbed"] == 1
        mock_grab.delay.assert_called_once()
        call_kwargs = mock_grab.delay.call_args
        assert call_kwargs.kwargs["issue_id"] == "5678"
        assert "download_url" in call_kwargs.kwargs["result"]

    @patch("app.tasks.search_wanted.get_sync_session")
    @patch("app.tasks.search_wanted.asyncio.run")
    def test_no_match_does_not_grab(self, mock_run, mock_ctx):
        """No search results → grab_issue.delay must NOT be called."""
        comic = _make_comic()
        issue = _make_issue()

        mock_session = _make_mock_session([[issue], comic])
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        mock_run.return_value = []  # No search results
        mock_grab = MagicMock()
        mock_grab.delay = MagicMock()

        with patch("app.tasks.search_wanted.settings") as mock_settings, \
             patch("app.tasks.search_wanted.grab_issue", mock_grab):
            mock_settings.GRAB_ON_MATCH = True
            from app.tasks.search_wanted import search_wanted
            result = search_wanted()

        assert result["matched"] == 0
        assert result["grabbed"] == 0
        mock_grab.delay.assert_not_called()

    @patch("app.tasks.search_wanted.get_sync_session")
    @patch("app.tasks.search_wanted.asyncio.run")
    def test_paused_comic_skipped(self, mock_run, mock_ctx):
        """Issues belonging to a Paused comic must be skipped entirely."""
        comic = _make_comic(status="Paused")
        issue = _make_issue()

        mock_session = _make_mock_session([[issue], comic])
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        mock_grab = MagicMock()
        mock_grab.delay = MagicMock()

        with patch("app.tasks.search_wanted.grab_issue", mock_grab):
            from app.tasks.search_wanted import search_wanted
            result = search_wanted()

        assert result["scanned"] == 0  # Paused → not counted as scanned
        mock_run.assert_not_called()
        mock_grab.delay.assert_not_called()

    @patch("app.tasks.search_wanted.get_sync_session")
    @patch("app.tasks.search_wanted.asyncio.run")
    def test_grab_on_match_false_does_not_grab(self, mock_run, mock_ctx):
        """GRAB_ON_MATCH=False → match is logged but grab is never dispatched."""
        comic = _make_comic()
        issue = _make_issue()
        search_results = [_make_search_result()]

        mock_session = _make_mock_session([[issue], comic])
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        mock_run.return_value = search_results
        mock_grab = MagicMock()
        mock_grab.delay = MagicMock()

        with patch("app.tasks.search_wanted.settings") as mock_settings, \
             patch("app.tasks.search_wanted.grab_issue", mock_grab):
            mock_settings.GRAB_ON_MATCH = False
            from app.tasks.search_wanted import search_wanted
            result = search_wanted()

        assert result["matched"] == 1
        assert result["grabbed"] == 0
        mock_grab.delay.assert_not_called()


# ---------------------------------------------------------------------------
# grab_issue tests
# ---------------------------------------------------------------------------

class TestGrabIssue:
    _result = {
        "title": "Amazing Spider-Man 001",
        "download_url": "http://indexer.test/nzb/001.nzb",
        "provider_name": "TestIndexer",
        "type": "nzb",
    }

    @patch("app.tasks.grab_issue.get_sync_session")
    @patch("app.tasks.grab_issue.asyncio.run")
    @patch("app.tasks.grab_issue.get_downloader")
    def test_grab_success_updates_status(self, mock_factory, mock_run, mock_ctx):
        """Successful grab → issue.status set to Snatched."""
        issue = _make_issue(status="Wanted")

        mock_downloader = MagicMock()
        mock_factory.return_value = mock_downloader
        mock_run.return_value = "job-id-123"  # Simulates downloader returning a job ID

        mock_session = _make_mock_session([issue])
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        from app.tasks.grab_issue import grab_issue
        result = grab_issue(issue_id="5678", result=self._result)

        assert result["status"] == "Snatched"
        assert issue.status == "Snatched"

    @patch("app.tasks.grab_issue.get_downloader")
    def test_no_downloader_returns_skipped(self, mock_factory):
        """DOWNLOADER_TYPE=none → no DB interaction, returns Skipped."""
        mock_factory.return_value = None

        from app.tasks.grab_issue import grab_issue
        result = grab_issue(issue_id="5678", result=self._result)

        assert result["status"] == "Skipped"

    @patch("app.tasks.grab_issue.get_sync_session")
    @patch("app.tasks.grab_issue.asyncio.run")
    @patch("app.tasks.grab_issue.get_downloader")
    def test_downloader_failure_returns_failed(self, mock_factory, mock_run, mock_ctx):
        """Downloader returning None → status Failed, issue NOT updated."""
        issue = _make_issue(status="Wanted")

        mock_downloader = MagicMock()
        mock_factory.return_value = mock_downloader
        mock_run.return_value = None  # Downloader failure

        # Session should NOT be called since we bail out before DB update
        mock_session = MagicMock()
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        from app.tasks.grab_issue import grab_issue
        result = grab_issue(issue_id="5678", result=self._result)

        assert result["status"] == "Failed"
        assert issue.status == "Wanted"  # Unchanged


# ---------------------------------------------------------------------------
# sync_comic_metadata tests
# ---------------------------------------------------------------------------

class TestSyncComicMetadata:
    @patch("app.tasks.db_sync.get_sync_session")
    @patch("app.tasks.db_sync.ComicVineClient")
    def test_sync_updates_publisher(self, mock_cv_class, mock_ctx):
        """When CV returns a changed publisher, Comic.publisher is updated."""
        comic = _make_comic(comic_id="1234")
        comic.publisher = "Timely Comics"  # Old publisher

        mock_session = _make_mock_session([comic, []])
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        # Mock the CV client instance's async methods
        from app.services.cv_api import CVIssuesResponse
        mock_cv = MagicMock()
        mock_cv.get_volume = AsyncMock(return_value={
            "name": "Amazing Spider-Man",
            "publisher": {"name": "Marvel"},
            "id": 1234,
        })
        mock_cv.get_issues = AsyncMock(return_value=CVIssuesResponse(
            error="OK",
            status_code=1,
            number_of_total_results=0,
            results=[]
        ))
        mock_cv_class.return_value = mock_cv

        from app.tasks.db_sync import sync_comic_metadata
        result = sync_comic_metadata(comic_id="1234")

        assert result["updated"] is True
        assert comic.publisher == "Marvel"
        assert result["new_issues"] == 0

    @patch("app.tasks.db_sync.get_sync_session")
    @patch("app.tasks.db_sync.ComicVineClient")
    def test_sync_adds_new_issues(self, mock_cv_class, mock_ctx):
        """New issues from CV (not yet in DB) are added as Wanted."""
        comic = _make_comic(comic_id="1234")

        mock_session = _make_mock_session([comic, []])
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        from app.services.cv_api import CVIssuesResponse, CVIssue
        mock_cv = MagicMock()
        mock_cv.get_volume = AsyncMock(return_value={
            "name": "Amazing Spider-Man",
            "publisher": {"name": "Marvel"},
            "id": 1234,
        })
        mock_cv.get_issues = AsyncMock(return_value=CVIssuesResponse(
            error="OK",
            status_code=1,
            number_of_total_results=2,
            results=[
                CVIssue(id=9001, issue_number="2", name="Chapter 2", store_date="2024-01-01"),
                CVIssue(id=9002, issue_number="3", name="Chapter 3", store_date="2024-02-01"),
            ]
        ))
        mock_cv_class.return_value = mock_cv

        from app.tasks.db_sync import sync_comic_metadata
        result = sync_comic_metadata(comic_id="1234")

        assert result["new_issues"] == 2
        assert mock_session.add.call_count >= 2

    @patch("app.tasks.db_sync.get_sync_session")
    def test_sync_unknown_comic_returns_early(self, mock_ctx):
        """Comic not in DB → returns immediately without calling CV API."""
        mock_session = _make_mock_session([None])
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        from app.tasks.db_sync import sync_comic_metadata
        result = sync_comic_metadata(comic_id="9999")

        assert result["updated"] is False
        assert result["new_issues"] == 0
