from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.config import settings
from app.core.db import init_db
from app.core.logger import logger, log_memory

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup tasks
    logger.info("Starting up Mylar3 modern hybrid backend...")
    log_memory("FastAPI Startup")
    try:
        await init_db()
        logger.info("PostgreSQL database tables initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing PostgreSQL tables: {e}")
    
    yield
    
    # Shutdown tasks
    logger.info("Shutting down Mylar3 modern hybrid backend...")

app = FastAPI(
    title="Mylar3",
    description="Modern Hybrid Comic Book Grabber",
    version="0.4.0",
    lifespan=lifespan
)

@app.get("/")
async def root():
    return {
        "message": "Welcome to Mylar3 modern hybrid backend!",
        "docs_url": "/docs"
    }
