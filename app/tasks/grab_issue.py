"""
Celery task: grab_issue
-----------------------
Submits a matched release to the configured downloader client and updates
the Issue status to "Snatched" on success.

Called by search_wanted via .delay() when a match is found and GRAB_ON_MATCH
is enabled.
"""
import asyncio
from typing import Optional

from sqlmodel import select

from app.core.logger import logger
from app.core.sync_db import get_sync_session
from app.downloaders.factory import get_downloader
from app.models.issue import Issue
from app.worker import celery_app


@celery_app.task(
    name="tasks.grab_issue",
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5-minute retry backoff
)
def grab_issue(self, issue_id: str, result: dict) -> dict:
    """
    Submit a release to the configured downloader and update issue status.

    Args:
        issue_id:  The Issue.issue_id to update on success.
        result:    Dict with keys: title, download_url, provider_name, type.

    Returns:
        {"issue_id": str, "status": "Snatched" | "Failed"}
    """
    title: str = result.get("title", "Unknown")
    download_url: str = result.get("download_url", "")
    provider_name: str = result.get("provider_name", "Unknown")

    logger.info(
        f"[Grab] Processing grab for issue {issue_id}: '{title}' from {provider_name}"
    )

    # Resolve the configured downloader
    downloader = get_downloader()
    if downloader is None:
        logger.warning(
            f"[Grab] No downloader configured (DOWNLOADER_TYPE=none). "
            f"Skipping grab for issue {issue_id}."
        )
        return {"issue_id": issue_id, "status": "Skipped"}

    # Submit the download
    try:
        job_id: Optional[str] = asyncio.run(
            downloader.add_download(
                url_or_filepath=download_url,
                title=title,
            )
        )
    except Exception as exc:
        logger.error(f"[Grab] Downloader raised exception for issue {issue_id}: {exc}")
        job_id = None

    if not job_id:
        logger.error(
            f"[Grab] Download submission failed for issue {issue_id} — "
            f"will leave status as Wanted for next search cycle."
        )
        return {"issue_id": issue_id, "status": "Failed"}

    # Update the Issue status to Snatched
    with get_sync_session() as session:
        issue: Optional[Issue] = session.exec(
            select(Issue).where(Issue.issue_id == issue_id)
        ).first()

        if issue is None:
            logger.warning(f"[Grab] Issue {issue_id} not found in DB after grab.")
            return {"issue_id": issue_id, "status": "Failed"}

        issue.status = "Snatched"
        session.add(issue)

    logger.info(
        f"[Grab] Issue {issue_id} status updated to Snatched. "
        f"Downloader job ID: {job_id}"
    )
    return {"issue_id": issue_id, "status": "Snatched"}
