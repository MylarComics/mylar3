import os
import json
import logging
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings, SETTINGS_CACHE_FILE
from app.models.settings import SystemSettings

logger = logging.getLogger("mylar")

async def initialize_settings(session: AsyncSession) -> None:
    """
    Initialize settings in the database if not present, and dump to cache file.
    """
    stmt = select(SystemSettings).where(SystemSettings.id == 1)
    result = await session.execute(stmt)
    db_settings = result.scalars().first()
    
    if not db_settings:
        logger.info("Initializing system settings database table with defaults...")
        settings_data = {}
        fields = getattr(SystemSettings, "model_fields", None) or getattr(SystemSettings, "__fields__", {})
        for key in fields.keys():
            if key == "id":
                continue
            if hasattr(settings, key):
                settings_data[key] = getattr(settings, key)
        
        db_settings = SystemSettings(id=1, **settings_data)
        session.add(db_settings)
        await session.commit()
        await session.refresh(db_settings)
        logger.info("System settings database table initialized successfully.")
    
    # Always write settings cache file on startup to make sure it matches DB
    await sync_db_to_cache(db_settings)
    settings.reload_from_cache()

async def sync_db_to_cache(db_settings: SystemSettings) -> None:
    """
    Serialize the database settings to cache/settings_cache.json.
    """
    try:
        # Convert DB model to dict using model_dump or dict
        if hasattr(db_settings, "model_dump"):
            data = db_settings.model_dump()
        else:
            data = db_settings.dict()
            
        # Remove the ID field
        data.pop("id", None)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(SETTINGS_CACHE_FILE), exist_ok=True)
        
        # Write to temp file first then rename to ensure atomic write
        temp_file = SETTINGS_CACHE_FILE + ".tmp"
        with open(temp_file, "w") as f:
            json.dump(data, f, indent=4, sort_keys=True)
        
        if os.path.exists(SETTINGS_CACHE_FILE):
            os.remove(SETTINGS_CACHE_FILE)
        os.rename(temp_file, SETTINGS_CACHE_FILE)
        
        logger.debug("System settings synchronized to disk cache.")
    except Exception as e:
        logger.error(f"Failed to synchronize database settings to disk cache: {e}")

async def save_settings(session: AsyncSession, new_data: dict) -> bool:
    """
    Save new system settings, update database, write cache, and reload in-memory settings.
    """
    try:
        # Fetch current database settings
        stmt = select(SystemSettings).where(SystemSettings.id == 1)
        result = await session.execute(stmt)
        db_settings = result.scalars().first()
        
        if not db_settings:
            await initialize_settings(session)
            stmt = select(SystemSettings).where(SystemSettings.id == 1)
            result = await session.execute(stmt)
            db_settings = result.scalars().first()
            if not db_settings:
                logger.error("Failed to retrieve system settings for update.")
                return False
        
        fields = getattr(SystemSettings, "model_fields", None) or getattr(SystemSettings, "__fields__", {})
        
        # Update attributes
        for k, v in new_data.items():
            if k in fields and k != "id":
                field = fields[k]
                expected_type = getattr(field, "annotation", None)
                if expected_type is None:
                    expected_type = getattr(field, "type_", None)
                
                if expected_type == bool:
                    if isinstance(v, str):
                        v = v.lower() in ("true", "1", "on", "yes")
                    else:
                        v = bool(v)
                elif expected_type == int:
                    try:
                        v = int(v)
                    except (ValueError, TypeError):
                        continue
                elif expected_type == float:
                    try:
                        v = float(v)
                    except (ValueError, TypeError):
                        continue
                setattr(db_settings, k, v)
        
        # For boolean toggles, if they are missing from raw form data, set them to False
        for k, field in fields.items():
            if k == "id":
                continue
            expected_type = getattr(field, "annotation", None) or getattr(field, "type_", None)
            if expected_type == bool and k not in new_data:
                # If we're updating and a boolean field is missing from form submission, set it to False
                setattr(db_settings, k, False)
        
        session.add(db_settings)
        await session.commit()
        await session.refresh(db_settings)
        
        # Sync to cache file
        await sync_db_to_cache(db_settings)
        settings.reload_from_cache()
        logger.info("System settings updated and synchronized successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to save system settings: {e}")
        return False
