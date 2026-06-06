import os
import json
import pytest
import httpx
from unittest.mock import AsyncMock, patch
from sqlmodel import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.comic import Comic
from app.models.issue import Issue
from app.services.ddl import DDLService, JDownloader2, parse_size_to_bytes
from app.services.search import search_issue, SearchResultItem

@pytest.mark.parametrize("text,expected", [
    ("Size: 45.2 MB", 45.2 * 1024 * 1024),
    ("1.5 GB in size", 1.5 * 1024 * 1024 * 1024),
    ("Some Text with 350 KB file", 350 * 1024),
    ("No size specified", 50 * 1024 * 1024),  # Fallback
])
def test_parse_size_to_bytes(text, expected):
    assert parse_size_to_bytes(text) == int(expected)

@pytest.mark.asyncio
async def test_ddl_search_getcomics():
    service = DDLService()
    
    # Mock HTML search page
    mock_html = """
    <html>
        <body>
            <article id="post-101">
                <h1 class="post-title"><a href="https://getcomics.info/marvel/amazing-spider-man-15-2018/">Amazing Spider-Man #15 (2018)</a></h1>
                <p>Size: 42.1 MB | Year: 2018</p>
            </article>
            <article id="post-102">
                <h2 class="post-title"><a href="https://getcomics.info/dc/batman-50-2018/">Batman #50 (2018)</a></h2>
                <p>Size: 85 MB</p>
            </article>
        </body>
    </html>
    """

    comic = Comic(comic_id="111", comic_name="Amazing Spider-Man", comic_year=2018)
    issue = Issue(issue_id="222", comic_id="111", issue_number="15")

    with patch.object(service, '_fetch_url', AsyncMock(return_value=mock_html)) as mock_fetch:
        results = await service.search_issue(comic, issue)
        
        # Verify it queries the correct search URL
        mock_fetch.assert_called_once_with("https://getcomics.info/?s=Amazing+Spider-Man+15")
        
        assert len(results) == 2
        assert results[0].title == "Amazing Spider-Man #15 (2018)"
        assert results[0].download_url == "https://getcomics.info/marvel/amazing-spider-man-15-2018/"
        assert results[0].size == int(42.1 * 1024 * 1024)
        assert results[0].provider_name == "GetComics"
        assert results[0].type == "ddl"

@pytest.mark.asyncio
async def test_ddl_flaresolverr_routing():
    service = DDLService()
    
    # Enable FlareSolverr
    settings.ENABLE_FLARESOLVERR = True
    settings.FLARESOLVERR_URL = "http://flaresolverr:8191/v1"
    
    mock_response = {
        "status": "ok",
        "solution": {
            "response": "<html>FlareSolverr HTML</html>"
        }
    }
    
    # Mock post call
    mock_req = httpx.Request("POST", "http://flaresolverr:8191/v1")
    with patch("httpx.AsyncClient.post", AsyncMock(return_value=httpx.Response(200, json=mock_response, request=mock_req))) as mock_post:
        res = await service._fetch_url("https://getcomics.info/?s=test")
        
        assert res == "<html>FlareSolverr HTML</html>"
        mock_post.assert_called_once()
        assert mock_post.call_args[0][0] == "http://flaresolverr:8191/v1"
        assert mock_post.call_args[1]["json"]["url"] == "https://getcomics.info/?s=test"
        
    # Cleanup settings
    settings.ENABLE_FLARESOLVERR = False
    settings.FLARESOLVERR_URL = ""

@pytest.mark.asyncio
async def test_ddl_resolve_download_link():
    service = DDLService()
    
    # Mock post details HTML
    mock_post_html = """
    <html>
        <body>
            <div class="aio-pulse">
                <a href="https://mega.nz/#!xyz" title="MEGA Link">MEGA</a>
                <a href="https://www.mediafire.com/file/abc" title="Mediafire Link">Mediafire</a>
                <a href="https://pixeldrain.com/u/123">Pixeldrain</a>
                <a href="https://getcomics.info/download-now-button" title="Main Server">Download Now</a>
            </div>
        </body>
    </html>
    """
    
    # Priority defaults: ["mega", "mediafire", "pixeldrain", "main"]
    # With JD2 disabled, mega gets demoted to the end, prioritizing mediafire
    with patch.object(service, '_fetch_url', AsyncMock(return_value=mock_post_html)):
        settings.JD2_ENABLE = False
        link = await service.resolve_download_link("https://getcomics.info/marvel/amazing-spider-man-15-2018/")
        assert link == "https://www.mediafire.com/file/abc" # Mediafire prioritized over Mega
        
        # Enable JD2: Mega gets prioritized
        settings.JD2_ENABLE = True
        link = await service.resolve_download_link("https://getcomics.info/marvel/amazing-spider-man-15-2018/")
        assert link == "https://mega.nz/#!xyz"
        settings.JD2_ENABLE = False

@pytest.mark.asyncio
async def test_jd2_submit():
    client = JDownloader2("http://jd2-server:8080")
    
    mock_resp = {
        "data": {
            "id": 12345
        }
    }
    
    mock_req = httpx.Request("GET", "http://jd2-server:8080/linkgrabberv2/addLinks")
    with patch("httpx.AsyncClient.get", AsyncMock(return_value=httpx.Response(200, json=mock_resp, request=mock_req))) as mock_get:
        res = await client.submit({"https://mega.nz/#!xyz": "DEFAULT"}, "Amazing Spider-Man #15")
        
        assert res["status"] is True
        assert res["jobid"] == "12345"
        mock_get.assert_called_once()
        assert "linkgrabberv2/addLinks" in mock_get.call_args[0][0]

@pytest.mark.asyncio
async def test_ddl_search_fallback():
    # Test integration of DDL fallback inside search_issue
    comic = Comic(comic_id="999", comic_name="Spider-Man", comic_year=2018)
    issue = Issue(issue_id="888", comic_id="999", issue_number="1")
    
    settings.ENABLE_DDL = True
    
    mock_ddl_item = SearchResultItem(
        title="Spider-Man #1 (2018)",
        download_url="https://getcomics.info/spiderman-1",
        size=50_000_000,
        provider_name="GetComics",
        type="ddl"
    )
    
    # Mock indexer queries to return nothing, and DDL to return mock item
    with patch("app.services.search.get_all_indexers", return_value=[]), \
         patch("app.services.ddl.DDLService.search_issue", AsyncMock(return_value=[mock_ddl_item])):
        
        results = await search_issue(comic, issue)
        
        assert len(results) == 1
        assert results[0].provider_name == "GetComics"
        assert results[0].type == "ddl"
        
    settings.ENABLE_DDL = False
