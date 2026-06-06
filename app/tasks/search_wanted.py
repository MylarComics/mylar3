"""
Celery task: search_wanted
--------------------------
Periodic task that scans all Wanted issues in the database, queries all
configured indexers for matching releases, and optionally triggers a grab.

Scheduled by Celery Beat via the beat_schedule in app/worker.py.
"""
import asyncio
from typing import List

from sqlmodel import select

from app.core.config import settings
from app.core.logger import logger
from app.core.sync_db import get_sync_session
from app.models.comic import Comic
from app.models.issue import Issue
from app.services.search import search_issue, SearchResultItem
from app.worker import celery_app

# Import at module level so tests can patch app.tasks.search_wanted.grab_issue
from app.tasks.grab_issue import grab_issue


@celery_app.task(
    name="tasks.search_wanted",
    bind=True,
    max_retries=0,  # Beat will re-fire on schedule; no manual retries needed
)
def search_wanted(self) -> dict:
    """
    Orchestrator task. Finds all Wanted issues, searches each one across
    all configured indexers, and dispatches grab_issue for the best match.

    Returns a summary dict for result tracking:
        {"scanned": int, "matched": int, "grabbed": int}
    """
    settings.check_and_reload()
    logger.info("[Search Runner] Starting wanted-issue search loop.")
    scanned = 0
    matched = 0
    grabbed = 0

    with get_sync_session() as session:
        # Fetch all Wanted issues whose parent comic is Active
        wanted_issues: List[Issue] = session.exec(
            select(Issue).where(Issue.status == "Wanted")
        ).all()

        if not wanted_issues:
            logger.info("[Search Runner] No Wanted issues found — nothing to search.")
            return {"scanned": 0, "matched": 0, "grabbed": 0}

        logger.info(f"[Search Runner] Found {len(wanted_issues)} Wanted issue(s) to search.")

        for issue in wanted_issues:
            # Fetch the parent comic
            comic: Comic | None = session.exec(
                select(Comic).where(Comic.comic_id == issue.comic_id)
            ).first()

            if comic is None:
                logger.warning(
                    f"[Search Runner] Issue {issue.issue_id} has no matching comic — skipping."
                )
                continue

            if comic.status != "Active":
                logger.info(
                    f"[Search Runner] Comic '{comic.comic_name}' is {comic.status} — skipping issue {issue.issue_number}."
                )
                continue

            scanned += 1
            logger.info(
                f"[Search Runner] Searching for '{comic.comic_name}' #{issue.issue_number} "
                f"(issue_id={issue.issue_id})"
            )

            # Run the async search in the sync Celery context
            try:
                results: List[SearchResultItem] = asyncio.run(
                    search_issue(comic, issue)
                )
            except Exception as exc:
                logger.error(
                    f"[Search Runner] Search failed for issue {issue.issue_id}: {exc}"
                )
                continue

            if not results:
                logger.info(
                    f"[Search Runner] No results found for '{comic.comic_name}' #{issue.issue_number}."
                )
                continue

            matched += 1
            best = results[0]
            logger.info(
                f"[Search Runner] Match found for '{comic.comic_name}' #{issue.issue_number}: "
                f"'{best.title}' via {best.provider_name}"
            )

            if settings.GRAB_ON_MATCH:
                # Dispatch grab_issue as an async Celery task
                grab_issue.delay(
                    issue_id=issue.issue_id,
                    result={
                        "title": best.title,
                        "download_url": best.download_url,
                        "provider_name": best.provider_name,
                        "type": best.type,
                    },
                )
                grabbed += 1
                logger.info(
                    f"[Search Runner] Grab dispatched for issue {issue.issue_id}."
                )

    logger.info(
        f"[Search Runner] Loop complete — "
        f"scanned={scanned}, matched={matched}, grabbed={grabbed}."
    )
    return {"scanned": scanned, "matched": matched, "grabbed": grabbed}
