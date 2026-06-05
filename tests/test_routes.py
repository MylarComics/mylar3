import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from sqlmodel import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.core.db import engine, init_db, get_session
from app.models.comic import Comic
from app.models.issue import Issue
from app.services.cv_api import CVVolume, CVPublisherRef, CVImage

@pytest_asyncio.fixture(scope="function")
async def db_session():
    # Initialize database schemas
    await init_db()
    
    # Yield an active session
    async with AsyncSession(engine) as session:
        yield session
        # Cleanup database tables after each test run
        await session.execute(delete(Issue))
        await session.execute(delete(Comic))
        await session.commit()
    # Close connection pool to prevent event loop issues
    await engine.dispose()

@pytest_asyncio.fixture(scope="function")
async def client(db_session):
    # Override get_session dependency to use our test session
    async def _get_session_override():
        yield db_session
        
    app.dependency_overrides[get_session] = _get_session_override
    
    # Use ASGITransport for async client testing
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client
        
    app.dependency_overrides.pop(get_session, None)

@pytest.mark.asyncio
async def test_read_dashboard_empty(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "Your Watchlist" in response.text
    assert "No comics in your watchlist yet." in response.text

@pytest.mark.asyncio
async def test_read_dashboard_with_data(client, db_session):
    # Insert a dummy comic
    comic = Comic(
        comic_id="10101",
        comic_name="Test Comic",
        comic_year=2021,
        publisher="Marvel",
        status="Active",
        location="comics/Marvel/Test Comic"
    )
    db_session.add(comic)
    await db_session.commit()

    response = await client.get("/")
    assert response.status_code == 200
    assert "Test Comic" in response.text
    assert "Marvel" in response.text
    assert "badge-active" in response.text
    assert "No comics in your watchlist yet." not in response.text

@pytest.mark.asyncio
async def test_read_comic_detail_not_found(client):
    response = await client.get("/comics/999999")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_read_comic_detail_found(client, db_session):
    # Insert a dummy comic and issues
    comic = Comic(
        comic_id="20202",
        comic_name="Batman",
        comic_year=2016,
        publisher="DC Comics",
        status="Active",
        location="comics/DC/Batman"
    )
    issue1 = Issue(
        issue_id="30303",
        comic_id="20202",
        issue_number="1",
        issue_name="Batman Begins",
        release_date="2016-06-01",
        status="Wanted"
    )
    issue2 = Issue(
        issue_id="30304",
        comic_id="20202",
        issue_number="2",
        issue_name="Batman Returns",
        release_date="2016-07-01",
        status="Skipped"
    )
    db_session.add(comic)
    db_session.add(issue1)
    db_session.add(issue2)
    await db_session.commit()

    response = await client.get("/comics/20202")
    assert response.status_code == 200
    assert "Batman" in response.text
    assert "Batman Begins" in response.text
    assert "badge-wanted" in response.text
    assert "badge-skipped" in response.text

@pytest.mark.asyncio
@patch("app.routers.api.ComicVineClient")
async def test_search_comicvine(mock_cv_client_class, client):
    mock_cv = AsyncMock()
    mock_cv_client_class.return_value = mock_cv
    
    mock_volume = CVVolume(
        id=5555,
        name="Amazing Fantasy",
        start_year="1962",
        publisher=CVPublisherRef(id=1, name="Marvel"),
        description="First Spidey app",
        count_of_issues=15,
        image=CVImage(icon_url="https://example.com/spidey.jpg")
    )
    mock_cv.search_volumes.return_value = [mock_volume]

    response = await client.get("/api/search-cv?q=Amazing")
    assert response.status_code == 200
    assert "Amazing Fantasy" in response.text
    assert "1962" in response.text
    assert "15 Issues" in response.text
    assert 'hx-post="/api/comics/add"' in response.text

@pytest.mark.asyncio
@patch("app.routers.api.add_comic_to_db")
async def test_add_comic_route(mock_add_comic_to_db, client, db_session):
    # Mock add_comic_to_db behavior
    mock_comic = Comic(
        comic_id="4444",
        comic_name="Iron Man",
        comic_year=2008,
        publisher="Marvel",
        status="Active",
        location="comics/Marvel/Iron Man"
    )
    mock_add_comic_to_db.return_value = mock_comic

    # Mock DB counts query
    response = await client.post("/api/comics/add", data={"comic_id": "4444"})
    assert response.status_code == 200
    assert "Iron Man" in response.text
    assert "watchlist-count" in response.text
    assert "watchlist-empty" in response.text

@pytest.mark.asyncio
async def test_toggle_comic_status(client, db_session):
    comic = Comic(
        comic_id="6666",
        comic_name="Hulk",
        comic_year=1999,
        publisher="Marvel",
        status="Active",
        location="comics/Marvel/Hulk"
    )
    db_session.add(comic)
    await db_session.commit()

    # Toggle from Active to Paused
    response = await client.post("/api/comics/6666/toggle")
    assert response.status_code == 200
    assert "Paused" in response.text
    assert "badge-paused" in response.text

    # Toggle back from Paused to Active
    response = await client.post("/api/comics/6666/toggle")
    assert response.status_code == 200
    assert "Active" in response.text
    assert "badge-active" in response.text

@pytest.mark.asyncio
async def test_delete_comic_route(client, db_session):
    comic = Comic(
        comic_id="7777",
        comic_name="Thor",
        comic_year=2011,
        publisher="Marvel",
        status="Active",
        location="comics/Marvel/Thor"
    )
    issue = Issue(
        issue_id="8888",
        comic_id="7777",
        issue_number="1",
        issue_name="Thor's Hammer",
        release_date="2011-05-01",
        status="Wanted"
    )
    db_session.add(comic)
    db_session.add(issue)
    await db_session.commit()

    # Delete the comic
    response = await client.delete("/api/comics/7777")
    assert response.status_code == 200
    assert "watchlist-count" in response.text
    assert "watchlist-empty" in response.text

    # Verify deleted from DB
    stmt_comic = select(Comic).where(Comic.comic_id == "7777")
    res_comic = await db_session.execute(stmt_comic)
    assert res_comic.scalars().first() is None

    stmt_issue = select(Issue).where(Issue.comic_id == "7777")
    res_issue = await db_session.execute(stmt_issue)
    assert len(res_issue.scalars().all()) == 0

@pytest.mark.asyncio
async def test_toggle_issue_status(client, db_session):
    issue = Issue(
        issue_id="9999",
        comic_id="1111",
        issue_number="1",
        issue_name="Issue One",
        release_date="2020-01-01",
        status="Skipped"
    )
    db_session.add(issue)
    await db_session.commit()

    # Cycle 1: Skipped -> Wanted
    response = await client.post("/api/issues/9999/toggle")
    assert response.status_code == 200
    assert "Wanted" in response.text
    assert "badge-wanted" in response.text

    # Cycle 2: Wanted -> Snatched
    response = await client.post("/api/issues/9999/toggle")
    assert response.status_code == 200
    assert "Snatched" in response.text
    assert "badge-snatched" in response.text

    # Cycle 3: Snatched -> Downloaded
    response = await client.post("/api/issues/9999/toggle")
    assert response.status_code == 200
    assert "Downloaded" in response.text
    assert "badge-downloaded" in response.text

    # Cycle 4: Downloaded -> Skipped
    response = await client.post("/api/issues/9999/toggle")
    assert response.status_code == 200
    assert "Skipped" in response.text
    assert "badge-skipped" in response.text

@pytest.mark.asyncio
@patch("app.routers.api.search_issue")
async def test_manual_search_route(mock_search_issue, client, db_session):
    comic = Comic(
        comic_id="1000",
        comic_name="Iron Fist",
        comic_year=2015,
        publisher="Marvel",
        status="Active",
        location="comics/Marvel/Iron Fist"
    )
    issue = Issue(
        issue_id="1001",
        comic_id="1000",
        issue_number="1",
        issue_name="Enter the Fist",
        release_date="2015-05-01",
        status="Wanted"
    )
    db_session.add(comic)
    db_session.add(issue)
    await db_session.commit()

    # Mock search_issue returning match results (status becomes Snatched)
    from app.services.search import SearchResultItem
    mock_search_issue.return_value = [
        SearchResultItem(
            title="Iron Fist 01 (2015) (Digital).cbz",
            download_url="https://example.com/download/ironfist01",
            size=50_000_000,
            provider_name="MockNZB",
            type="nzb"
        )
    ]

    response = await client.post("/api/issues/1001/search")
    assert response.status_code == 200
    assert "Snatched" in response.text
    assert "badge-snatched" in response.text
