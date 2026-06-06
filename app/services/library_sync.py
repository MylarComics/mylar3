import os
import re
from typing import Dict, Any, List, Optional
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import logger
from app.models.comic import Comic
from app.models.issue import Issue
from app.services.parsing import parse_filename

class LibrarySyncService:
    """
    Service responsible for scanning local directories, resolving files using
    the filename parser, automatically linking matched issues to their disk locations,
    and identifying potential series candidates to import.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.extensions = (".cbz", ".cbr", ".pdf", ".cb7")

    def normalize_name(self, name: str) -> str:
        return re.sub(r'[^a-z0-9]', '', name.lower()).strip()

    async def scan_and_sync_library(self, scan_dir: str) -> Dict[str, Any]:
        """
        Scans a directory recursively and updates DB.
        Returns:
            {
                "synced_files_count": int,
                "unmatched_candidates": List[Dict[str, Any]] # {"series_name": str, "year": int, "files_count": int}
            }
        """
        if not os.path.exists(scan_dir):
            logger.error(f"[LibrarySync] Scan directory does not exist: {scan_dir}")
            return {"synced_files_count": 0, "unmatched_candidates": []}

        # Gather files
        files_to_sync = []
        for root, _, files in os.walk(scan_dir):
            for file in files:
                if file.lower().endswith(self.extensions):
                    files_to_sync.append(os.path.join(root, file))

        logger.info(f"[LibrarySync] Found {len(files_to_sync)} files in {scan_dir} to check...")

        # Get active watchlist comics
        stmt_comics = select(Comic)
        res_comics = await self.session.execute(stmt_comics)
        watchlist_comics = res_comics.scalars().all()
        
        # Build lookup map: normalized series name -> Comic object
        watchlist_map = {self.normalize_name(c.comic_name): c for c in watchlist_comics}

        synced_count = 0
        unmatched_groups: Dict[str, Dict[str, Any]] = {}

        for filepath in files_to_sync:
            filename = os.path.basename(filepath)
            parsed = parse_filename(filename)
            series_name = parsed.get("series_name")
            issue_number = parsed.get("issue_number")
            year = parsed.get("issue_year")
            if year and year.isdigit():
                year = int(year)

            if not series_name or not issue_number:
                continue

            norm_series = self.normalize_name(series_name)
            matched_comic = watchlist_map.get(norm_series)

            if matched_comic:
                # Resolve relative path for DB location storage
                rel_path = os.path.relpath(filepath, matched_comic.location or settings.DESTINATION_DIR)
                
                # Fetch all issues under this comic to match
                stmt_issues = select(Issue).where(Issue.comic_id == matched_comic.comic_id)
                res_issues = await self.session.execute(stmt_issues)
                all_issues = res_issues.scalars().all()

                matched_issue = None
                for iss in all_issues:
                    try:
                        if float(iss.issue_number) == float(issue_number):
                            matched_issue = iss
                            break
                    except ValueError:
                        if iss.issue_number.strip().lower() == str(issue_number).strip().lower():
                            matched_issue = iss
                            break

                if matched_issue:
                    matched_issue.status = "Downloaded"
                    matched_issue.location = rel_path
                    self.session.add(matched_issue)
                    synced_count += 1
                    logger.fdebug(f"[LibrarySync] Synced {filename} to issue {matched_issue.issue_id}")
                else:
                    # Dynamically add the issue to the database as Downloaded
                    new_iss = Issue(
                        issue_id=f"imported_{matched_comic.comic_id}_{issue_number}",
                        comic_id=matched_comic.comic_id,
                        issue_number=str(issue_number),
                        issue_name=f"Issue #{issue_number}",
                        release_date=str(year) if year else None,
                        status="Downloaded",
                        location=rel_path
                    )
                    self.session.add(new_iss)
                    synced_count += 1
                    logger.info(f"[LibrarySync] Dynamically added new issue: {series_name} #{issue_number}")
            else:
                # Unmatched candidate grouping
                key = f"{norm_series}_{year or ''}"
                if key not in unmatched_groups:
                    unmatched_groups[key] = {
                        "series_name": series_name,
                        "year": year,
                        "files_count": 0,
                        "sample_filepath": filepath
                    }
                unmatched_groups[key]["files_count"] += 1

        try:
            await self.session.commit()
            logger.info(f"[LibrarySync] Completed library sync. Synced {synced_count} file(s). Found {len(unmatched_groups)} unmatched series candidate(s).")
            
            candidates = sorted(
                list(unmatched_groups.values()),
                key=lambda x: x["series_name"].lower()
            )
            return {
                "synced_files_count": synced_count,
                "unmatched_candidates": candidates
            }
        except Exception as e:
            logger.error(f"[LibrarySync] Database transaction failed during library sync: {e}")
            await self.session.rollback()
            raise
