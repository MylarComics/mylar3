import asyncio
from typing import Optional, Dict, Any
from app.worker import celery_app
from app.core.config import settings
from app.core.logger import logger
from app.core.db import async_session
from app.services.weekly_pull import WeeklyPullService

@celery_app.task(name="tasks.sync_weekly_pull_list")
def sync_weekly_pull_list(week: Optional[int] = None, year: Optional[int] = None) -> Dict[str, Any]:
    """
    Celery task to download and synchronize the weekly releases.
    Can be run on-demand or as a periodic task.
    """
    settings.check_and_reload()
    logger.info(f"[Tasks] Triggering sync of weekly pull list for week={week}, year={year}")
    
    async def _run():
        async with async_session() as session:
            service = WeeklyPullService(session)
            try:
                return await service.fetch_and_sync(week, year)
            finally:
                await service.close()
                
    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error(f"[Tasks] Weekly pull sync task failed: {exc}", exc_info=True)
        return {"status": "failure", "detail": str(exc)}
