import os
import json
import pytest
import pytest_asyncio
from sqlmodel import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import settings, SETTINGS_CACHE_FILE
from app.core.db import engine, init_db, get_session
from app.models.settings import SystemSettings
from app.services.settings_service import initialize_settings, save_settings

@pytest_asyncio.fixture(scope="function")
async def db_session():
    # Initialize database schemas
    await init_db()
    
    # Yield an active session
    async with AsyncSession(engine) as session:
        yield session
        # Cleanup database tables after each test run
        await session.execute(delete(SystemSettings))
        await session.commit()
        
    # Close connection pool
    await engine.dispose()

@pytest_asyncio.fixture(scope="function")
async def client(db_session):
    async def _get_session_override():
        yield db_session
        
    app.dependency_overrides[get_session] = _get_session_override
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client
        
    app.dependency_overrides.pop(get_session, None)

@pytest.fixture(autouse=True)
def cleanup_cache_file():
    # Store original values
    orig_api_key = settings.COMICVINE_API_KEY
    orig_downloader = settings.DOWNLOADER_TYPE
    
    # Yield to the test
    yield
    
    # Restore original values
    settings.COMICVINE_API_KEY = orig_api_key
    settings.DOWNLOADER_TYPE = orig_downloader
    
    # Cleanup file on disk
    if os.path.exists(SETTINGS_CACHE_FILE):
        try:
            os.remove(SETTINGS_CACHE_FILE)
        except Exception:
            pass

@pytest.mark.asyncio
async def test_initialize_settings(db_session):
    # Ensure starting without a settings row
    await db_session.execute(delete(SystemSettings))
    await db_session.commit()
    
    # Call initialization
    await initialize_settings(db_session)
    
    # Verify row exists in DB
    stmt = select(SystemSettings).where(SystemSettings.id == 1)
    result = await db_session.execute(stmt)
    db_settings = result.scalars().first()
    assert db_settings is not None
    assert db_settings.COMICVINE_API_KEY == settings.COMICVINE_API_KEY
    
    # Verify cache file was created
    assert os.path.exists(SETTINGS_CACHE_FILE)
    with open(SETTINGS_CACHE_FILE, "r") as f:
        data = json.load(f)
    assert data["COMICVINE_API_KEY"] == settings.COMICVINE_API_KEY

@pytest.mark.asyncio
async def test_save_settings(db_session):
    await initialize_settings(db_session)
    
    # Update settings via save_settings
    update_data = {
        "COMICVINE_API_KEY": "updated_test_key",
        "DOWNLOADER_TYPE": "sabnzbd",
        "NOTIFY_ON_SNATCH": "on",  # Test string-to-bool conversion
        "SEARCH_INTERVAL_MINUTES": "45"  # Test string-to-int conversion
    }
    
    success = await save_settings(db_session, update_data)
    assert success is True
    
    # Re-fetch from DB and verify
    stmt = select(SystemSettings).where(SystemSettings.id == 1)
    result = await db_session.execute(stmt)
    db_settings = result.scalars().first()
    assert db_settings.COMICVINE_API_KEY == "updated_test_key"
    assert db_settings.DOWNLOADER_TYPE == "sabnzbd"
    assert db_settings.NOTIFY_ON_SNATCH is True
    assert db_settings.SEARCH_INTERVAL_MINUTES == 45
    
    # Verify the local settings instance updated
    assert settings.COMICVINE_API_KEY == "updated_test_key"
    assert settings.DOWNLOADER_TYPE == "sabnzbd"

@pytest.mark.asyncio
async def test_settings_check_and_reload(db_session):
    await initialize_settings(db_session)
    
    # Manually overwrite settings instance values in memory
    settings.COMICVINE_API_KEY = "memory_key"
    
    # Write a new key to the cache file directly to simulate external update
    with open(SETTINGS_CACHE_FILE, "r") as f:
        data = json.load(f)
    data["COMICVINE_API_KEY"] = "external_file_key"
    
    # Ensure cache file has updated mtime
    with open(SETTINGS_CACHE_FILE, "w") as f:
        json.dump(data, f)
        
    # Trigger check_and_reload
    settings.check_and_reload()
    
    # Verify values refreshed from cache
    assert settings.COMICVINE_API_KEY == "external_file_key"

@pytest.mark.asyncio
async def test_settings_web_and_api_routes(client, db_session):
    await initialize_settings(db_session)
    
    # Test GET settings page
    response = await client.get("/settings")
    assert response.status_code == 200
    assert "System Settings" in response.text
    assert "ComicVine API Key" in response.text
    
    # Test POST api save settings
    payload = {
        "COMICVINE_API_KEY": "api_posted_key",
        "DOWNLOADER_TYPE": "qbittorrent",
        "GRAB_ON_MATCH": "false"
    }
    response = await client.post("/api/settings", data=payload)
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["ok"] is True
    
    # Check updated settings
    assert settings.COMICVINE_API_KEY == "api_posted_key"
    assert settings.DOWNLOADER_TYPE == "qbittorrent"
    assert settings.GRAB_ON_MATCH is False
