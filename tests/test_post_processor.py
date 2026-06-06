import os
import shutil
import zipfile
import pytest
import pytest_asyncio
from sqlmodel import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import engine, init_db
from app.models.comic import Comic
from app.models.issue import Issue
from app.core.config import settings
from app.services.post_processor import PostProcessorService

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
def temp_dirs(tmp_path):
    # Setup temp paths in test workspace
    download_dir = tmp_path / "downloads"
    destination_dir = tmp_path / "comics"
    
    os.makedirs(download_dir, exist_ok=True)
    os.makedirs(destination_dir, exist_ok=True)
    
    # Store settings originals
    orig_dest = settings.DESTINATION_DIR
    orig_move = settings.MOVE_FILES
    orig_rename = settings.RENAME_FILES
    orig_meta = settings.ENABLE_META
    
    # Apply temp paths to settings
    settings.DESTINATION_DIR = str(destination_dir)
    settings.MOVE_FILES = True
    settings.RENAME_FILES = True
    settings.ENABLE_META = False # Disable during unit test to skip missing ComicTagger binary
    
    yield download_dir, destination_dir
    
    # Restore settings
    settings.DESTINATION_DIR = orig_dest
    settings.MOVE_FILES = orig_move
    settings.RENAME_FILES = orig_rename
    settings.ENABLE_META = orig_meta

@pytest.mark.asyncio
async def test_post_process_file_success(db_session, temp_dirs):
    download_dir, destination_dir = temp_dirs

    # 1. Insert seed data
    comic = Comic(
        comic_id="12345",
        comic_name="The Amazing Spider-Man",
        comic_year=2018,
        publisher="Marvel",
        status="Active",
        location=str(destination_dir / "Marvel" / "The Amazing Spider-Man (2018)")
    )
    issue = Issue(
        issue_id="67890",
        comic_id="12345",
        issue_number="1",
        issue_name="Back to Basics",
        release_date="2018-07-11",
        status="Snatched"
    )
    db_session.add(comic)
    db_session.add(issue)
    await db_session.commit()

    # 2. Create dummy CBZ file
    cbz_filename = "The.Amazing.Spider-Man.001.2018.cbz"
    cbz_path = os.path.join(download_dir, cbz_filename)
    
    with zipfile.ZipFile(cbz_path, 'w') as zipf:
        zipf.writestr("page1.jpg", b"dummy image content")

    # 3. Instantiate PostProcessor and process
    pp_service = PostProcessorService(db_session)
    results = await pp_service.scan_and_process(str(download_dir))

    # 4. Verify results
    assert len(results) == 1
    assert results[0]["status"] == "success"
    
    # Re-fetch from DB to verify status changes
    stmt = select(Issue).where(Issue.issue_id == "67890")
    res = await db_session.execute(stmt)
    updated_issue = res.scalars().first()
    assert updated_issue.status == "Downloaded"
    
    # Verify file was moved to the correct destination structure
    expected_moved_path = os.path.join(
        str(destination_dir),
        "Marvel",
        "The Amazing Spider-Man (2018)",
        "The Amazing Spider-Man 1 (2018).cbz"
    )
    assert os.path.exists(expected_moved_path)
    assert not os.path.exists(cbz_path) # Since MOVE_FILES is True
