"""
Celery task: grab_issue
-----------------------
Submits a matched release to the configured downloader client, updates
the Issue status to "Snatched" on success, and fires push notifications
for both success and failure events.

Called by search_wanted via .delay() when a match is found and GRAB_ON_MATCH
is enabled.
"""
import asyncio
from typing import Optional

from sqlmodel import select

from app.core.config import settings
from app.core.logger import logger
from app.core.sync_db import get_sync_session
from app.downloaders.factory import get_downloader
from app.models.issue import Issue
from app.notifications.factory import get_notifier
from app.worker import celery_app


def _send_notification(title: str, body: str, notify_type: str) -> None:
    """Helper to fire a notification from within a sync Celery task."""
    notifier = get_notifier()
    if notifier is None:
        return
    try:
        asyncio.run(notifier.notify(title=title, body=body, notify_type=notify_type))
    except Exception as exc:
        logger.error(f"[Grab] Notification failed: {exc}")


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
        {"issue_id": str, "status": "Snatched" | "Failed" | "Skipped"}
    """
    settings.check_and_reload()
    title: str = result.get("title", "Unknown")
    download_url: str = result.get("download_url", "")
    provider_name: str = result.get("provider_name", "Unknown")

    logger.info(
        f"[Grab] Processing grab for issue {issue_id}: '{title}' from {provider_name}"
    )

    job_id = None
    if result.get("type") == "ddl":
        from app.services.ddl import DDLService
        ddl_service = DDLService()
        try:
            direct_link = asyncio.run(ddl_service.resolve_download_link(download_url))
        except Exception as e:
            logger.error(f"[Grab] Failed resolving download link for DDL: {e}")
            direct_link = None
            
        if direct_link:
            if settings.JD2_ENABLE and settings.JD2_URL:
                from app.services.ddl import JDownloader2
                jd2 = JDownloader2(settings.JD2_URL)
                package_name = f"{title} - {issue_id}"
                logger.info(f"[Grab] Sending DDL link to JDownloader2 package {package_name}")
                try:
                    jd_res = asyncio.run(jd2.submit({direct_link: "DEFAULT"}, package_name))
                    if jd_res.get("status"):
                        job_id = jd_res["jobid"]
                    else:
                        logger.error(f"[Grab] JDownloader2 submission failed: {jd_res.get('error')}")
                except Exception as e:
                    logger.error(f"[Grab] JDownloader2 error: {e}")
            else:
                import os
                temp_dir = os.path.join("cache", "ddl", issue_id)
                clean_url = direct_link.split("?")[0].rstrip("/")
                filename = os.path.basename(clean_url)
                if not filename or not filename.endswith((".cbz", ".cbr", ".pdf", ".cb7")):
                    filename = f"{title}.cbz"
                
                dest_filepath = os.path.join(temp_dir, filename)
                logger.info(f"[Grab] Downloading direct link to {dest_filepath}")
                try:
                    download_ok = asyncio.run(ddl_service.download_file(direct_link, dest_filepath))
                    if download_ok:
                        from app.tasks.post_process import post_process_folder
                        post_process_folder.delay(temp_dir)
                        job_id = f"ddl-{issue_id}"
                except Exception as e:
                    logger.error(f"[Grab] Direct DDL download failed: {e}")
        else:
            logger.error(f"[Grab] Could not resolve any direct links from post page {download_url}")
    else:
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
            job_id = asyncio.run(
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
            f"[Grab] Download submission failed for issue {issue_id}."
        )
        if settings.FAILED_DOWNLOAD_HANDLING:
            from app.models.failed_release import FailedRelease
            import datetime
            try:
                with get_sync_session() as session:
                    # Normalize / fallback for download_url
                    target_url = download_url or f"failed-submission-{issue_id}"
                    stmt = select(FailedRelease).where(FailedRelease.release_id == target_url)
                    existing = session.exec(stmt).first()
                    if not existing:
                        # Fetch the issue to retrieve comic_id
                        issue_obj = session.exec(select(Issue).where(Issue.issue_id == issue_id)).first()
                        comic_id = issue_obj.comic_id if issue_obj else ""
                        
                        failed_rel = FailedRelease(
                            release_id=target_url,
                            title=title,
                            provider=provider_name,
                            comic_id=comic_id,
                            issue_id=issue_id,
                            date_failed=datetime.datetime.utcnow().isoformat()
                        )
                        session.add(failed_rel)

                        if issue_obj:
                            if settings.FAILED_AUTO:
                                issue_obj.status = "Wanted"
                            else:
                                issue_obj.status = "Failed"
                            session.add(issue_obj)
            except Exception as e:
                logger.error(f"[Grab] Failed to blacklist failed release: {e}")

            if settings.FAILED_AUTO:
                from app.tasks.search_wanted import search_wanted
                logger.info(f"[Grab] FAILED_AUTO is enabled. Dispatching search_wanted delay.")
                search_wanted.delay()

        if settings.NOTIFY_ON_FAILURE:
            _send_notification(
                title="Grab Failed ❌",
                body=f"Could not download: '{title}'\nProvider: {provider_name}",
                notify_type="failure",
            )
        return {"issue_id": issue_id, "status": "Failed"}

    # Fetch the issue for display context, then update its status
    issue_number: str = ""
    with get_sync_session() as session:
        issue: Optional[Issue] = session.exec(
            select(Issue).where(Issue.issue_id == issue_id)
        ).first()

        if issue is None:
            logger.warning(f"[Grab] Issue {issue_id} not found in DB after grab.")
            return {"issue_id": issue_id, "status": "Failed"}

        issue_number = issue.issue_number
        issue.status = "Snatched"
        session.add(issue)

    logger.info(
        f"[Grab] Issue {issue_id} status updated to Snatched. "
        f"Downloader job ID: {job_id}"
    )

    if settings.NOTIFY_ON_SNATCH:
        _send_notification(
            title="Snatched ✅",
            body=f"Issue #{issue_number} — '{title}'\nProvider: {provider_name}",
            notify_type="success",
        )

    return {"issue_id": issue_id, "status": "Snatched"}
