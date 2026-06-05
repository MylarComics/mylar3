import pytest
from unittest.mock import AsyncMock, patch
from app.models.comic import Comic
from app.models.issue import Issue
from app.services.search import (
    parse_providers_string,
    generate_search_queries,
    parse_xml_results,
    is_title_match,
    search_issue,
    check_indexer,
    IndexerConfig
)

# Sample XML response matching Newznab spec
MOCK_NEWZNAB_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/">
  <channel>
    <title>Mock Indexer Results</title>
    <item>
      <title>The Amazing Spider-Man 001 (2020) (Digital) (Zone-Empire)</title>
      <link>http://localhost/get/101</link>
      <enclosure url="http://localhost/get/101" length="45000000" type="application/x-nzb" />
      <newznab:attr name="size" value="45000000" />
      <pubDate>Wed, 05 Jun 2026 12:00:00 +0000</pubDate>
    </item>
    <item>
      <title>The Amazing Spider-Man 002 (2020) (Digital) (Zone-Empire)</title>
      <link>http://localhost/get/102</link>
      <enclosure url="http://localhost/get/102" length="50000000" type="application/x-nzb" />
      <pubDate>Thu, 06 Jun 2026 12:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Wrong Comic Series 001 (2020)</title>
      <link>http://localhost/get/103</link>
      <enclosure url="http://localhost/get/103" length="30000000" type="application/x-nzb" />
      <pubDate>Fri, 07 Jun 2026 12:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>
"""

MOCK_CAPS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<caps>
  <server version="1.0" title="Mock Indexer" />
</caps>
"""

def test_parse_providers_string():
    # Test valid formats
    config_str = "Geek|https://api.nzbgeek.info|myapikey123,Finder|https://nzbfinder.ws|anotherkey"
    providers = parse_providers_string(config_str, "newznab")
    
    assert len(providers) == 2
    assert providers[0].name == "Geek"
    assert providers[0].url == "https://api.nzbgeek.info"
    assert providers[0].apikey == "myapikey123"
    assert providers[0].type == "newznab"
    
    assert providers[1].name == "Finder"
    assert providers[1].url == "https://nzbfinder.ws"
    assert providers[1].apikey == "anotherkey"
    assert providers[1].type == "newznab"

    # Test empty string returns empty list
    assert parse_providers_string("", "newznab") == []

def test_generate_search_queries():
    # Test queries generated for single digit numeric issue
    queries = generate_search_queries("Spider-Man", "1")
    assert "Spider-Man 1" in queries
    assert "Spider-Man 01" in queries
    assert "Spider-Man 001" in queries
    assert len(queries) == 3

    # Test query generated for issue with suffix
    queries_suffix = generate_search_queries("Action Comics", "1000A")
    assert "Action Comics 1000A" in queries_suffix
    assert "Action Comics 1000A" in queries_suffix
    assert len(queries_suffix) == 1

def test_parse_xml_results():
    provider = IndexerConfig(name="Mock", url="http://mock", apikey="key", type="newznab")
    results = parse_xml_results(MOCK_NEWZNAB_XML, provider)
    
    assert len(results) == 3
    assert results[0].title == "The Amazing Spider-Man 001 (2020) (Digital) (Zone-Empire)"
    assert results[0].download_url == "http://localhost/get/101"
    assert results[0].size == 45000000
    assert results[0].provider_name == "Mock"
    assert results[0].type == "nzb"

    # Verify fallback size on enclosure without newznab attr
    assert results[1].title == "The Amazing Spider-Man 002 (2020) (Digital) (Zone-Empire)"
    assert results[1].size == 50000000

def test_is_title_match():
    comic = Comic(comic_id="1", comic_name="The Amazing Spider-Man", comic_year=2020, publisher="Marvel")
    issue1 = Issue(issue_id="1", comic_id="1", issue_number="1", status="Wanted")
    issue2 = Issue(issue_id="2", comic_id="1", issue_number="2", status="Wanted")

    # Match valid title for issue 1
    parsed_title_1 = {
        "series_name": "The Amazing Spider-Man",
        "issue_number": "001",
        "issue_year": "2020"
    }
    assert is_title_match(parsed_title_1, comic, issue1) is True

    # Match valid title for issue 2
    parsed_title_2 = {
        "series_name": "The Amazing Spider-Man",
        "issue_number": "2",
        "issue_year": "2020"
    }
    assert is_title_match(parsed_title_2, comic, issue2) is True

    # Fail mismatched year
    parsed_title_wrong_year = {
        "series_name": "The Amazing Spider-Man",
        "issue_number": "1",
        "issue_year": "2018"
    }
    assert is_title_match(parsed_title_wrong_year, comic, issue1) is False

    # Fail mismatched series
    parsed_title_wrong_series = {
        "series_name": "Wrong Spider-Man",
        "issue_number": "1",
        "issue_year": "2020"
    }
    assert is_title_match(parsed_title_wrong_series, comic, issue1) is False

@pytest.mark.asyncio
@patch("app.services.search.get_all_indexers")
@patch("httpx.AsyncClient.get")
async def test_search_issue(mock_get, mock_get_indexers):
    # Setup mock indexer config
    provider = IndexerConfig(name="MockGeek", url="http://localhost", apikey="key", type="newznab")
    mock_get_indexers.return_value = [provider]

    # Mock indexer network response
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.content = MOCK_NEWZNAB_XML
    mock_get.return_value = mock_response

    comic = Comic(comic_id="1", comic_name="The Amazing Spider-Man", comic_year=2020, publisher="Marvel")
    issue = Issue(issue_id="1", comic_id="1", issue_number="1", status="Wanted")

    # Run search
    matches = await search_issue(comic, issue)
    
    # Assert that only matched release for Issue 1 was returned (mismatched series & issue 2 are filtered out)
    assert len(matches) == 1
    assert matches[0].title == "The Amazing Spider-Man 001 (2020) (Digital) (Zone-Empire)"
    assert matches[0].size == 45000000

@pytest.mark.asyncio
@patch("httpx.AsyncClient.get")
async def test_check_indexer(mock_get):
    # Success mock
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.content = MOCK_CAPS_XML
    mock_get.return_value = mock_response

    assert await check_indexer("http://localhost", "key") is True

    # Failure mock
    mock_response_fail = AsyncMock()
    mock_response_fail.status_code = 403
    mock_get.return_value = mock_response_fail

    assert await check_indexer("http://localhost", "key") is False
