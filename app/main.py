import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from app.core.config import settings
from app.core.db import init_db, async_session
from app.core.logger import logger, log_memory
from app.routers import web, api, opds
from app.services.settings_service import initialize_settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup tasks
    logger.info("Starting up Mylar3 modern hybrid backend...")
    log_memory("FastAPI Startup")
    try:
        await init_db()
        logger.info("PostgreSQL database tables initialized successfully.")
        
        # Initialize settings in database and cache
        async with async_session() as session:
            await initialize_settings(session)
    except Exception as e:
        logger.error(f"Error initializing PostgreSQL tables or settings: {e}")
    
    # Ensure cache directory exists
    os.makedirs(settings.CACHE_DIR, exist_ok=True)
    
    yield
    
    # Shutdown tasks
    logger.info("Shutting down Mylar3 modern hybrid backend...")

app = FastAPI(
    title="Mylar3",
    description="Modern Hybrid Comic Book Grabber",
    version="0.4.0",
    lifespan=lifespan
)

# Mount Static and Cache folders
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/cache", StaticFiles(directory=settings.CACHE_DIR), name="cache")

# Register Routers
app.include_router(web.router)
app.include_router(api.router)
app.include_router(opds.router)

