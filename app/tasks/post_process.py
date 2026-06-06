import asyncio
from typing import Optional, List, Dict, Any
from app.worker import celery_app, run_async
from app.core.config import settings
from app.core.logger import logger
from app.core.db import async_session
from app.services.post_processor import PostProcessorService

@celery_app.task(name="tasks.post_process_folder")
def post_process_folder(folder_path: str, nzb_name: Optional[str] = None, status: Optional[str] = "success") -> List[Dict[str, Any]]:
    """
    Celery task to run the post-processor on a given download directory.
    This runs asynchronously in the Celery worker pool.
    """
    settings.check_and_reload()
    logger.info(f"[Tasks] Triggering post-processing for folder: {folder_path} (status: {status})")
    
    async def _run():
        async with async_session() as session:
            pp_service = PostProcessorService(session)
            return await pp_service.scan_and_process(folder_path, nzb_name, status)
            
    try:
        return run_async(_run())
    except Exception as exc:
        logger.error(f"[Tasks] Post-processing task failed: {exc}", exc_info=True)
        return [{"file": folder_path, "status": "failed", "detail": str(exc)}]
