"""
Celery task: sync_comic_metadata
---------------------------------
On-demand metadata refresh task. Re-fetches series details and issue list from
ComicVine for a specific comic, updates the Comic record, and adds any newly
discovered issues to the database as "Wanted" (if the series is Active).

Can be triggered manually via the API or via the Celery Beat schedule.
"""
import asyncio
from typing import List, Optional

from sqlmodel import select

from app.core.logger import logger
from app.core.sync_db import get_sync_session
from app.models.comic import Comic
from app.models.issue import Issue
from app.services.cv_api import ComicVineClient
from app.worker import celery_app


@celery_app.task(name="tasks.sync_comic_metadata", bind=True, max_retries=2)
def sync_comic_metadata(self, comic_id: str) -> dict:
    """
    Re-sync a single comic's metadata from ComicVine.

    Args:
        comic_id: The Comic.comic_id (ComicVine volume ID) to refresh.

    Returns:
        {
            "comic_id": str,
            "updated": bool,
            "new_issues": int,
        }
    """
    logger.info(f"[DB Sync] Starting metadata sync for comic_id={comic_id}")

    with get_sync_session() as session:
        comic: Optional[Comic] = session.exec(
            select(Comic).where(Comic.comic_id == comic_id)
        ).first()

        if comic is None:
            logger.warning(f"[DB Sync] Comic {comic_id} not found in DB — aborting sync.")
            return {"comic_id": comic_id, "updated": False, "new_issues": 0}

        # Fetch fresh volume data from ComicVine
        cv_client = ComicVineClient()
        try:
            volume_data = asyncio.run(cv_client.get_volume(int(comic_id)))
        except Exception as exc:
            logger.error(f"[DB Sync] ComicVine API call failed for {comic_id}: {exc}")
            return {"comic_id": comic_id, "updated": False, "new_issues": 0}

        if volume_data is None:
            logger.warning(f"[DB Sync] ComicVine returned no data for {comic_id}.")
            return {"comic_id": comic_id, "updated": False, "new_issues": 0}

        updated = False

        # Update top-level fields if they have changed
        new_name: str = volume_data.get("name", comic.comic_name)
        new_publisher: str = (
            (volume_data.get("publisher") or {}).get("name") or comic.publisher or ""
        )

        if new_name != comic.comic_name:
            logger.info(
                f"[DB Sync] Updating comic name: '{comic.comic_name}' → '{new_name}'"
            )
            comic.comic_name = new_name
            updated = True

        if new_publisher and new_publisher != comic.publisher:
            logger.info(
                f"[DB Sync] Updating publisher: '{comic.publisher}' → '{new_publisher}'"
            )
            comic.publisher = new_publisher
            updated = True

        if updated:
            session.add(comic)

        # Sync issues — discover any new ones from CV
        new_issues_added = 0
        if comic.status == "Active":
            try:
                cv_issues: List[dict] = asyncio.run(cv_client.get_issues(int(comic_id)))
            except Exception as exc:
                logger.error(
                    f"[DB Sync] Failed to fetch issues from ComicVine for {comic_id}: {exc}"
                )
                cv_issues = []

            # Fetch existing issue IDs for this comic
            existing_ids = set(
                session.exec(
                    select(Issue.issue_id).where(Issue.comic_id == comic_id)
                ).all()
            )

            for cv_issue in cv_issues:
                cv_issue_id = str(cv_issue.get("id", ""))
                if not cv_issue_id or cv_issue_id in existing_ids:
                    continue

                new_issue = Issue(
                    issue_id=cv_issue_id,
                    comic_id=comic_id,
                    issue_number=str(cv_issue.get("issue_number", "0")),
                    issue_name=cv_issue.get("name") or None,
                    release_date=cv_issue.get("store_date") or cv_issue.get("cover_date") or None,
                    status="Wanted",
                )
                session.add(new_issue)
                new_issues_added += 1
                logger.info(
                    f"[DB Sync] New issue discovered: #{new_issue.issue_number} "
                    f"(id={cv_issue_id}) for '{comic.comic_name}' — marked Wanted."
                )

    logger.info(
        f"[DB Sync] Sync complete for comic_id={comic_id}: "
        f"updated={updated}, new_issues={new_issues_added}."
    )
    return {
        "comic_id": comic_id,
        "updated": updated,
        "new_issues": new_issues_added,
    }
