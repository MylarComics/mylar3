import pytest
import pytest_asyncio
import os
from unittest.mock import AsyncMock, patch
from sqlmodel import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import engine, init_db
from app.models.comic import Comic
from app.models.issue import Issue
from app.services.importer import add_comic_to_db, resolve_publisher_and_imprint, determine_book_type
from app.services.cv_api import CVVolume, CVIssue, CVImage, CVPublisherRef, CVVolumeRef, CVIssuesResponse

# A tiny 1x1 black JPEG image for cover downloader mocking
TINY_JPEG = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\x27" #\x2c&\'317.97$;(\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\x37\xff\xd9'

@pytest_asyncio.fixture(scope="function")
async def db_session():
    # Initialize the database schemas
    await init_db()
    
    # Yield an active session
    async with AsyncSession(engine) as session:
        yield session
        # Cleanup database tables after each test run
        await session.execute(delete(Issue))
        await session.execute(delete(Comic))
        await session.commit()

def test_resolve_publisher_and_imprint():
    # Test imprint mapping rules
    parent, imprint = resolve_publisher_and_imprint("Homage Comics")
    assert parent == "DC Comics"
    assert imprint == "Homage"

    parent2, imprint2 = resolve_publisher_and_imprint("Max Comics")
    assert parent2 == "Marvel"
    assert imprint2 == "MAX"

    # Test standard publisher fallback
    parent3, imprint3 = resolve_publisher_and_imprint("Image")
    assert parent3 == "Image"
    assert imprint3 is None

    # Test empty raw publisher fallback
    parent4, imprint4 = resolve_publisher_and_imprint(None)
    assert parent4 == "Unknown"
    assert imprint4 is None

def test_determine_book_type():
    # Test One-Shot detection (1 issue count)
    vol_one_shot = CVVolume(id=123, name="Single Shot", count_of_issues=1)
    assert determine_book_type(vol_one_shot, []) == "One-Shot"

    # Test TPB detection
    vol_tpb = CVVolume(
        id=124, 
        name="Spider-Man Volume 1", 
        count_of_issues=5, 
        description="This trade paperback collects the issues"
    )
    assert determine_book_type(vol_tpb, []) == "TPB"

    # Test regular ongoing print edition
    vol_print = CVVolume(
        id=125, 
        name="X-Men Volume 2", 
        count_of_issues=50, 
        description="Ongoing monthly series"
    )
    assert determine_book_type(vol_print, []) == "Print"


@pytest.mark.asyncio
@patch("app.services.importer.ComicVineClient")
@patch("app.services.covers.download_image")
async def test_add_comic_to_db(mock_download_image, mock_cv_client_class, db_session):
    # Setup mocks for ComicVine API client
    mock_cv_client = AsyncMock()
    mock_cv_client_class.return_value = mock_cv_client

    # Mock get_volume response
    mock_volume = CVVolume(
        id=99999,
        name="Mock Volume",
        start_year="2020",
        publisher=CVPublisherRef(id=1, name="Marvel"),
        description="Test description",
        count_of_issues=2,
        image=CVImage(super_url="https://example.com/cover.jpg", icon_url="https://example.com/icon.jpg"),
        site_detail_url="https://example.com/mock-volume"
    )
    mock_cv_client.get_volume.return_value = mock_volume

    # Mock get_issues pagination response
    mock_issues = [
        CVIssue(id=2001, issue_number="1", name="Issue One", cover_date="2020-01-01", store_date="2020-01-05"),
        CVIssue(id=2002, issue_number="2", name="Issue Two", cover_date="2020-02-01", store_date="2020-02-05")
    ]
    mock_cv_client.get_issues.return_value = CVIssuesResponse(
        error="OK",
        status_code=1,
        number_of_total_results=2,
        results=mock_issues
    )

    # Mock cover image download returning a tiny valid JPEG
    mock_download_image.return_value = TINY_JPEG

    # Execute importer logic
    comic = await add_comic_to_db(db_session, "99999")
    
    assert comic is not None
    assert comic.comic_name == "Mock Volume"
    assert comic.comic_year == 2020
    assert comic.publisher == "Marvel"
    assert comic.location is not None
    assert "Marvel" in comic.location

    # Verify that details were written to DB
    stmt_comic = select(Comic).where(Comic.comic_id == "99999")
    res_comic = await db_session.execute(stmt_comic)
    db_comic = res_comic.scalars().first()
    assert db_comic is not None
    assert db_comic.comic_name == "Mock Volume"

    # Verify that issues were linked correctly in the DB
    stmt_issues = select(Issue).where(Issue.comic_id == "99999")
    res_issues = await db_session.execute(stmt_issues)
    db_issues = res_issues.scalars().all()
    assert len(db_issues) == 2
    
    issue_numbers = {iss.issue_number for iss in db_issues}
    assert issue_numbers == {"1", "2"}
    
    issue_names = {iss.issue_name for iss in db_issues}
    assert issue_names == {"Issue One", "Issue Two"}

    # Check update logic by calling add_comic_to_db again with changed name
    mock_volume.name = "Mock Volume Updated"
    updated_comic = await add_comic_to_db(db_session, "99999")
    
    assert updated_comic is not None
    assert updated_comic.comic_name == "Mock Volume Updated"
    
    # Check that database is updated rather than adding a duplicate
    stmt_all_comics = select(Comic)
    res_all_comics = await db_session.execute(stmt_all_comics)
    all_comics = res_all_comics.scalars().all()
    assert len(all_comics) == 1
    assert all_comics[0].comic_name == "Mock Volume Updated"
