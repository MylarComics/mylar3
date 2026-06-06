import os
import zipfile
import pytest
import pytest_asyncio
from sqlmodel import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import engine, init_db
from app.models.comic import Comic
from app.models.issue import Issue
from app.services.library_sync import LibrarySyncService

@pytest_asyncio.fixture(scope="function")
async def db_session():
    await init_db()
    async with AsyncSession(engine) as session:
        yield session
        await session.execute(delete(Issue))
        await session.execute(delete(Comic))
        await session.commit()
    await engine.dispose()

@pytest.fixture(scope="function")
def library_temp_dir(tmp_path):
    lib_dir = tmp_path / "mylibrary"
    os.makedirs(lib_dir, exist_ok=True)
    return lib_dir

@pytest.mark.asyncio
async def test_library_scan_and_sync(db_session, library_temp_dir):
    # 1. Seed watched comic/issue
    comic = Comic(
        comic_id="9999",
        comic_name="The Amazing Spider-Man",
        comic_year=2018,
        publisher="Marvel",
        status="Active",
        location=str(library_temp_dir / "Marvel" / "The Amazing Spider-Man (2018)")
    )
    issue = Issue(
        issue_id="8888",
        comic_id="9999",
        issue_number="1",
        issue_name="Back to Basics",
        release_date="2018-07-11",
        status="Wanted"
    )
    db_session.add(comic)
    db_session.add(issue)
    await db_session.commit()

    # 2. Create files on disk
    # A. Matched file
    matched_filename = "The.Amazing.Spider-Man.001.2018.cbz"
    matched_file_path = os.path.join(library_temp_dir, matched_filename)
    with zipfile.ZipFile(matched_file_path, 'w') as zipf:
        zipf.writestr("page1.jpg", b"content")

    # B. Unmatched file (Batman)
    unmatched_filename = "Batman.050.(2016).cbz"
    unmatched_file_path = os.path.join(library_temp_dir, unmatched_filename)
    with zipfile.ZipFile(unmatched_file_path, 'w') as zipf:
        zipf.writestr("page1.jpg", b"content")

    # 3. Scan & Sync
    sync_service = LibrarySyncService(db_session)
    res = await sync_service.scan_and_sync_library(str(library_temp_dir))

    # 4. Asserts
    # A. Verify return data metrics
    assert res["synced_files_count"] == 1
    assert len(res["unmatched_candidates"]) == 1
    assert res["unmatched_candidates"][0]["series_name"] == "Batman"
    assert res["unmatched_candidates"][0]["year"] == 2016
    assert res["unmatched_candidates"][0]["files_count"] == 1

    # B. Verify DB updates for matched issue
    stmt = select(Issue).where(Issue.issue_id == "8888")
    res_db = await db_session.execute(stmt)
    updated_issue = res_db.scalars().first()
    assert updated_issue.status == "Downloaded"
    assert updated_issue.location == "../../The.Amazing.Spider-Man.001.2018.cbz" # Relpath relative to comic.location
