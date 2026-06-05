import os
import re
from typing import Optional, List, Dict, Any
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.logger import logger
from app.models.comic import Comic
from app.models.issue import Issue
from app.services.cv_api import ComicVineClient, CVVolume, CVIssue
from app.services.covers import cache_cover, save_local_cover, save_local_folder_thumbnail

def make_filesafe(name: str) -> str:
    """
    Remove characters not allowed in Windows and Linux filenames: < > : " / \\ | ? *
    """
    safe = re.sub(r'[<>:"/\\|?*]', '', name)
    # Replace multiple spaces with a single space
    safe = re.sub(r'\s+', ' ', safe)
    return safe.strip()

def resolve_publisher_and_imprint(raw_publisher: Optional[str]) -> tuple[str, Optional[str]]:
    """
    Resolve imprints to their primary publisher and return (publisher, imprint).
    Based on Mylar legacy publisher and imprint mappings.
    """
    if not raw_publisher:
        return "Unknown", None

    publisher = raw_publisher.strip()
    imprint = None

    # Standard legacy imprint mapping
    imprint_mapping = {
        "Homage Comics": ("DC Comics", "Homage"),
        "Max Comics": ("Marvel", "MAX"),
        "Mailbu": ("Malibu Comics", "Malibu Comics"),
        "Milestone": ("DC Comics", "Milestone Comics"),
        "Skybound": ("Image", "Skybound Entertainment"),
        "Top Cow": ("Image", "Top Cow Productions"),
        "Vertigo": ("DC Comics", "Vertigo"),
        "Wildstorm": ("DC Comics", "WildStorm"),
        "Icon Comics": ("Marvel", "Icon Comics")
    }

    if publisher in imprint_mapping:
        parent, imp = imprint_mapping[publisher]
        return parent, imp

    return publisher, imprint

def determine_book_type(volume: CVVolume, issues: List[CVIssue]) -> str:
    """
    Determine the book type (One-Shot, TPB, HC, GN, Print, Digital)
    based on description, deck, and issue count.
    """
    desc = (volume.description or "").lower()
    deck = (volume.deck or "").lower()
    count = volume.count_of_issues or len(issues)

    # If count is 1 and it's not ongoing, it's likely a One-Shot
    if count == 1:
        return "One-Shot"

    # Analyze description/deck keywords
    text_to_check = f"{desc} {deck}"
    if "graphic novel" in text_to_check:
        return "GN"
    if "hardcover" in text_to_check:
        return "HC"
    if "trade paperback" in text_to_check or "tpb" in text_to_check:
        return "TPB"
    if "digital edition" in text_to_check or "digital comic" in text_to_check:
        return "Digital"
    if "one-shot" in text_to_check or "one shot" in text_to_check:
        return "One-Shot"

    return "Print"

async def add_comic_to_db(
    session: AsyncSession,
    comic_id: str,
    fixed_type: Optional[str] = None
) -> Optional[Comic]:
    """
    Fetches volume details and issue list from ComicVine, creates destination directory,
    inserts/updates the Comic and Issue models, and downloads cover art.
    """
    cv_client = ComicVineClient()
    logger.info(f"[Importer] Initiating import for Comic ID: {comic_id}")

    try:
        volume = await cv_client.get_volume(comic_id)
    except Exception as e:
        logger.error(f"[Importer] Failed to fetch volume {comic_id}: {e}")
        return None

    if not volume:
        logger.warning(f"[Importer] Volume {comic_id} not found on ComicVine")
        return None

    # 1. Resolve Publisher & Imprint
    raw_pub = volume.publisher.name if volume.publisher else None
    publisher, imprint = resolve_publisher_and_imprint(raw_pub)

    # 2. Parse Comic Year
    comic_year = None
    if volume.start_year and volume.start_year.isdigit():
        comic_year = int(volume.start_year)

    # 3. Determine Directory Structure
    publisher_safe = make_filesafe(publisher)
    name_safe = make_filesafe(volume.name)
    year_suffix = f" ({comic_year})" if comic_year else ""
    dest_dir = os.path.join(settings.DESTINATION_DIR, publisher_safe, f"{name_safe}{year_suffix}")

    # Create directory if enabled
    if settings.CREATE_FOLDERS:
        try:
            os.makedirs(dest_dir, exist_ok=True)
            logger.info(f"[Importer] Validated destination directory: {dest_dir}")
        except Exception as e:
            logger.error(f"[Importer] Failed to create destination directory {dest_dir}: {e}")

    # 4. Cover download and caching
    image_url = None
    if volume.image:
        image_url = volume.image.super_url or volume.image.original_url
        # Trigger cover caching and storage asynchronously/concurrently
        try:
            cache_path = await cache_cover(str(volume.id), image_url)
            await save_local_cover(str(volume.id), dest_dir, cache_path=cache_path, image_url=image_url)
            if volume.image.icon_url:
                await save_local_folder_thumbnail(str(volume.id), dest_dir, volume.image.icon_url)
        except Exception as e:
            logger.error(f"[Importer] Cover download failed for {volume.name}: {e}")

    # 5. Fetch all issues under this volume
    all_cv_issues: List[CVIssue] = []
    offset = 0
    while True:
        try:
            logger.info(f"[Importer] Fetching issues for volume {volume.id} (offset: {offset})")
            issues_resp = await cv_client.get_issues(str(volume.id), offset=offset)
            if not issues_resp.results:
                break
            all_cv_issues.extend(issues_resp.results)
            if len(all_cv_issues) >= issues_resp.number_of_total_results:
                break
            offset += 100
        except Exception as e:
            logger.error(f"[Importer] Failed to fetch issues at offset {offset}: {e}")
            break

    # Determine book type
    book_type = fixed_type or determine_book_type(volume, all_cv_issues)

    # 6. Check if Comic already exists
    stmt = select(Comic).where(Comic.comic_id == str(volume.id))
    result = await session.execute(stmt)
    comic = result.scalars().first()

    if not comic:
        comic = Comic(
            comic_id=str(volume.id),
            comic_name=volume.name,
            comic_year=comic_year,
            publisher=publisher,
            status="Active",
            location=dest_dir
        )
        session.add(comic)
        logger.info(f"[Importer] Added new Comic: {volume.name} ({comic_year})")
    else:
        comic.comic_name = volume.name
        comic.comic_year = comic_year
        comic.publisher = publisher
        comic.location = dest_dir
        logger.info(f"[Importer] Updated existing Comic: {volume.name} ({comic_year})")

    # Save changes to assign IDs/trackers before issue loops
    await session.flush()

    # 7. Sync Issues
    for cv_issue in all_cv_issues:
        issue_stmt = select(Issue).where(Issue.issue_id == str(cv_issue.id))
        issue_res = await session.execute(issue_stmt)
        issue = issue_res.scalars().first()

        release_date = cv_issue.cover_date or cv_issue.store_date

        if not issue:
            issue = Issue(
                issue_id=str(cv_issue.id),
                comic_id=str(volume.id),
                issue_number=cv_issue.issue_number,
                issue_name=cv_issue.name,
                release_date=release_date,
                status="Skipped"
            )
            session.add(issue)
        else:
            issue.issue_number = cv_issue.issue_number
            issue.issue_name = cv_issue.name
            issue.release_date = release_date

    try:
        await session.commit()
        await session.refresh(comic)
        logger.info(f"[Importer] Successfully synchronized database tables for volume {volume.name}")
        return comic
    except Exception as e:
        logger.error(f"[Importer] Database transaction failed: {e}")
        await session.rollback()
        raise
