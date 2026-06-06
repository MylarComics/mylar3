import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.comic import Comic
from app.models.issue import Issue
from app.models.failed_release import FailedRelease
from app.services.search import search_issue, IndexerConfig
from app.tasks.grab_issue import grab_issue

MOCK_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>The Amazing Spider-Man 001 (2020) (Digital)</title>
      <link>http://localhost/get/101.nzb</link>
      <enclosure url="http://localhost/get/101.nzb" length="45000000" type="application/x-nzb" />
      <pubDate>Wed, 05 Jun 2026 12:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>
"""

def _make_mock_session(exec_side_effects: list):
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

@pytest.mark.asyncio
@patch("app.services.search.get_all_indexers")
@patch("app.core.db.async_session")
@patch("httpx.AsyncClient.get")
async def test_search_issue_filters_blacklisted_release(mock_get, mock_sessionmaker, mock_get_indexers):
    # Setup mock indexer
    provider = IndexerConfig(name="MockGeek", url="http://localhost", apikey="key", type="newznab")
    mock_get_indexers.return_value = [provider]

    # Setup indexer network response
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.content = MOCK_XML
    mock_get.return_value = mock_response

    # Setup mock DB session to return a failed release matching the mocked URL
    mock_session = AsyncMock()
    mock_sessionmaker.return_value = mock_session
    mock_session.__aenter__.return_value = mock_session
    
    failed_release = FailedRelease(
        release_id="http://localhost/get/101.nzb",
        title="The Amazing Spider-Man 001 (2020) (Digital)",
        provider="MockGeek",
        comic_id="1",
        issue_id="101",
        date_failed="2026-06-05T00:00:00"
    )
    
    mock_db_res = MagicMock()
    mock_db_res.scalars.return_value.all.return_value = [failed_release]
    mock_session.execute = AsyncMock(return_value=mock_db_res)

    comic = Comic(comic_id="1", comic_name="The Amazing Spider-Man", comic_year=2020, publisher="Marvel")
    issue = Issue(issue_id="101", comic_id="1", issue_number="1", status="Wanted")

    # Run search with FAILED_DOWNLOAD_HANDLING active
    with patch("app.services.search.settings") as mock_settings:
        mock_settings.FAILED_DOWNLOAD_HANDLING = True
        mock_settings.CV_VERIFY = True
        matches = await search_issue(comic, issue)

    # The only release is blacklisted, so it should be filtered out
    assert len(matches) == 0

@patch("app.tasks.grab_issue.get_sync_session")
@patch("app.tasks.grab_issue.run_async")
@patch("app.tasks.grab_issue.get_downloader")
def test_grab_issue_submission_failure_blacklists_release(mock_downloader_factory, mock_run, mock_ctx):
    # Setup downloader to throw an exception / return no job ID
    mock_downloader_factory.return_value = MagicMock()
    mock_run.return_value = None  # Indicates failure to submit

    issue = Issue(issue_id="101", comic_id="1", issue_number="1", status="Wanted")
    mock_session = _make_mock_session([None, issue])
    mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)

    grab_result = {
        "title": "The Amazing Spider-Man 001",
        "download_url": "http://localhost/get/101.nzb",
        "provider_name": "MockGeek",
        "type": "nzb"
    }

    with patch("app.tasks.grab_issue.settings") as mock_settings:
        mock_settings.FAILED_DOWNLOAD_HANDLING = True
        mock_settings.FAILED_AUTO = False
        mock_settings.NOTIFY_ON_FAILURE = False

        res = grab_issue(issue_id="101", result=grab_result)

    assert res["status"] == "Failed"
    assert issue.status == "Failed"
    # Ensure added components include the new FailedRelease record
    mock_session.add.assert_any_call(issue)
    added_args = [call[0][0] for call in mock_session.add.call_args_list]
    failed_release_records = [x for x in added_args if isinstance(x, FailedRelease)]
    assert len(failed_release_records) == 1
    assert failed_release_records[0].release_id == "http://localhost/get/101.nzb"
    assert failed_release_records[0].issue_id == "101"

@patch("app.tasks.grab_issue.get_sync_session")
@patch("app.tasks.grab_issue.run_async")
@patch("app.tasks.grab_issue.get_downloader")
@patch("app.tasks.search_wanted.search_wanted.delay")
def test_grab_issue_submission_failure_auto_retries(mock_search_delay, mock_downloader_factory, mock_run, mock_ctx):
    mock_downloader_factory.return_value = MagicMock()
    mock_run.return_value = None

    issue = Issue(issue_id="101", comic_id="1", issue_number="1", status="Wanted")
    mock_session = _make_mock_session([None, issue])
    mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)

    grab_result = {
        "title": "The Amazing Spider-Man 001",
        "download_url": "http://localhost/get/101.nzb",
        "provider_name": "MockGeek",
        "type": "nzb"
    }

    with patch("app.tasks.grab_issue.settings") as mock_settings:
        mock_settings.FAILED_DOWNLOAD_HANDLING = True
        mock_settings.FAILED_AUTO = True
        mock_settings.NOTIFY_ON_FAILURE = False

        res = grab_issue(issue_id="101", result=grab_result)

    assert res["status"] == "Failed"
    # FAILED_AUTO = True -> status remains Wanted for immediate search retry
    assert issue.status == "Wanted"
    mock_search_delay.assert_called_once()

@pytest.mark.asyncio
@patch("app.services.post_processor.PostProcessorService.handle_failed_download")
async def test_scan_and_process_routes_failed_status(mock_handle_fail):
    mock_handle_fail.return_value = {"file": "Batman 001.nzb", "status": "failed_recorded", "detail": "Status updated"}

    from app.services.post_processor import PostProcessorService
    
    mock_session = AsyncMock()
    pp = PostProcessorService(mock_session)

    with patch("app.services.post_processor.settings") as mock_settings:
        mock_settings.FAILED_DOWNLOAD_HANDLING = True
        res = await pp.scan_and_process("downloads/Batman 001.nzb", nzb_name="Batman 001.nzb", status="failed")

    assert len(res) == 1
    assert res[0]["status"] == "failed_recorded"
    mock_handle_fail.assert_called_once_with("Batman 001.nzb", "downloads/Batman 001.nzb")
