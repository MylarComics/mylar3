import os
import re
import shutil
import subprocess
from typing import Dict, Any, List, Optional
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import logger
from app.models.comic import Comic
from app.models.issue import Issue
from app.services.parsing import parse_filename
from app.notifications.factory import get_notifier

class PostProcessorService:
    """
    Service responsible for post-processing downloaded comic books.
    This includes folder scanning, filename matching, path formatting,
    archive type verification (CBR to CBZ), metatagging (ComicTagger),
    database updates, and notifications.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.extensions = (".cbz", ".cbr", ".pdf", ".cb7")

    def format_path(self, pattern: str, series_name: str, year: Optional[str | int], issue_number: Optional[str], publisher: Optional[str]) -> str:
        """
        Replaces placeholders in FOLDER_FORMAT and FILE_FORMAT with actual values.
        """
        res = pattern
        # Normalize variables
        yr_str = str(year) if year else ""
        iss_str = str(issue_number) if issue_number else ""
        pub_str = publisher if publisher else "Unknown"

        # Apply replacements
        res = res.replace("$Series", series_name)
        res = res.replace("$Year", yr_str)
        res = res.replace("$Issue", iss_str)
        res = res.replace("$Publisher", pub_str)
        res = res.replace("$Volume", yr_str) # Default fallback volume to start year
        res = res.replace("$Annual", "")

        # Clean up double spaces, trailing symbols or brackets
        res = re.sub(r'\(\s*\)', '', res) # Remove empty parentheses ()
        res = re.sub(r'\[\s*\]', '', res) # Remove empty brackets []
        res = re.sub(r'\s+', ' ', res)
        return res.strip()

    def clean_path_segment(self, segment: str) -> str:
        """
        Remove characters that are illegal in Windows/Linux filesystems.
        """
        safe = re.sub(r'[<>:"/\\|?*]', '', segment)
        return re.sub(r'\s+', ' ', safe).strip()

    async def handle_failed_download(self, nzb_name: Optional[str], download_dir: str) -> Dict[str, Any]:
        """
        Handles failed downloads passed from the downloader or API.
        Parses release name, matches it to Comic/Issue, blacklists it, and cycles status.
        """
        ref_name = nzb_name or os.path.basename(download_dir.rstrip("/\\"))
        if not ref_name:
            raise ValueError("Could not determine release name or folder name for failed download")

        # Remove common compression/archive extensions if any
        ref_name_clean = re.sub(r'\.(cbz|cbr|zip|rar|tar|gz|pdf|cb7|nzb)$', '', ref_name, flags=re.IGNORECASE)

        # 1. Parse name using parse_filename
        parsed = parse_filename(ref_name_clean)
        series_name = parsed.get("series_name")
        issue_number = parsed.get("issue_number")
        year = parsed.get("issue_year")

        if not series_name or not issue_number:
            raise ValueError(f"Could not parse series name or issue number from failed release reference: '{ref_name_clean}'")

        # 2. Match Comic
        stmt_comics = select(Comic)
        res_comics = await self.session.execute(stmt_comics)
        comics = res_comics.scalars().all()

        matched_comic: Optional[Comic] = None
        norm_parsed = re.sub(r'[^a-z0-9]', '', series_name.lower())
        for c in comics:
            norm_c = re.sub(r'[^a-z0-9]', '', c.comic_name.lower())
            if norm_c == norm_parsed:
                if year and c.comic_year:
                    if int(year) == int(c.comic_year):
                        matched_comic = c
                        break
                if matched_comic is None:
                    matched_comic = c

        if not matched_comic:
            raise ValueError(f"No matching active comic series found in watchlist for failed release: '{series_name}'")

        # 3. Match Issue
        stmt_issues = select(Issue).where(Issue.comic_id == matched_comic.comic_id)
        res_issues = await self.session.execute(stmt_issues)
        all_issues = res_issues.scalars().all()

        matched_issue: Optional[Issue] = None
        for iss in all_issues:
            try:
                if float(iss.issue_number) == float(issue_number):
                    matched_issue = iss
                    break
            except ValueError:
                if iss.issue_number.strip().lower() == str(issue_number).strip().lower():
                    matched_issue = iss
                    break

        if not matched_issue:
            raise ValueError(f"No matching issue #{issue_number} found under series '{matched_comic.comic_name}'")

        # 4. Save FailedRelease blacklist record
        from app.models.failed_release import FailedRelease
        import datetime
        
        # We use the ref_name as release_id and title
        stmt_fail = select(FailedRelease).where(FailedRelease.release_id == ref_name)
        res_fail = await self.session.execute(stmt_fail)
        existing = res_fail.scalars().first()
        
        if not existing:
            failed_rel = FailedRelease(
                release_id=ref_name,
                title=ref_name,
                provider="Unknown",
                comic_id=matched_comic.comic_id,
                issue_id=matched_issue.issue_id,
                date_failed=datetime.datetime.utcnow().isoformat()
            )
            self.session.add(failed_rel)

        # 5. Cycle issue status
        if settings.FAILED_AUTO:
            matched_issue.status = "Wanted"
        else:
            matched_issue.status = "Failed"
            
        self.session.add(matched_issue)
        await self.session.commit()

        if settings.FAILED_AUTO:
            from app.tasks.search_wanted import search_wanted
            logger.info(f"[PostProcessor] FAILED_AUTO is enabled. Dispatching search_wanted.")
            search_wanted.delay()

        # Send notifications
        from app.notifications.factory import get_notifier
        notifier = get_notifier()
        if notifier and settings.NOTIFY_ON_FAILURE:
            try:
                title = "Download Failed ❌"
                body = f"Failed download reported for '{matched_comic.comic_name} #{matched_issue.issue_number}'\nRelease: {ref_name}"
                await notifier.notify(title=title, body=body, notify_type="failure")
            except Exception as e:
                logger.error(f"[PostProcessor] Notification failed: {e}")

        logger.info(f"[PostProcessor] Processed failed download for '{ref_name}' (status set to {matched_issue.status})")
        return {"file": ref_name, "status": "failed_recorded", "detail": f"Status updated to {matched_issue.status}"}

    async def scan_and_process(self, download_dir: str, nzb_name: Optional[str] = None, status: Optional[str] = "success") -> List[Dict[str, Any]]:
        """
        Scans a download directory for new comic files, matches them to watchlist,
        formats/moves them, and flags them as Downloaded.
        """
        if settings.FAILED_DOWNLOAD_HANDLING and (status == "failed" or status == "Failed"):
            try:
                res = await self.handle_failed_download(nzb_name, download_dir)
                return [res]
            except Exception as e:
                logger.error(f"[PostProcessor] Failed to record download failure: {e}", exc_info=True)
                return [{"file": nzb_name or download_dir, "status": "failed", "detail": str(e)}]

        results = []
        if not os.path.exists(download_dir):
            logger.error(f"[PostProcessor] Download directory does not exist: {download_dir}")
            return results

        # Gather files
        files_to_process = []
        if os.path.isfile(download_dir):
            files_to_process.append(download_dir)
        else:
            for root, _, files in os.walk(download_dir):
                for file in files:
                    if file.lower().endswith(self.extensions):
                        files_to_process.append(os.path.join(root, file))

        logger.info(f"[PostProcessor] Found {len(files_to_process)} comic file(s) to process in {download_dir}")

        for filepath in files_to_process:
            filename = os.path.basename(filepath)
            try:
                res = await self.process_file(filepath, nzb_name)
                results.append({"file": filename, "status": "success", "detail": res})
            except Exception as e:
                logger.error(f"[PostProcessor] Failed to process file {filename}: {e}", exc_info=True)
                results.append({"file": filename, "status": "failed", "detail": str(e)})
                if settings.FAILED_DOWNLOAD_HANDLING:
                    try:
                        ref_name = nzb_name or filename
                        await self.handle_failed_download(ref_name, filepath)
                    except Exception as fe:
                        logger.error(f"[PostProcessor] Failed to run failure handler for {filename}: {fe}")

        return results

    async def process_file(self, filepath: str, nzb_name: Optional[str] = None) -> str:
        filename = os.path.basename(filepath)
        logger.info(f"[PostProcessor] Start processing file: {filename}")

        # 1. Parse filename metadata
        parsed = parse_filename(filename)
        series_name = parsed.get("series_name")
        issue_number = parsed.get("issue_number")
        year = parsed.get("issue_year")

        if not series_name or not issue_number:
            raise ValueError(f"Could not parse series name or issue number from filename: {filename}")

        # 2. Database lookup: Match Comic
        # Perform dynamic matching similar to Mylar's search
        stmt_comics = select(Comic)
        res_comics = await self.session.execute(stmt_comics)
        comics = res_comics.scalars().all()

        matched_comic: Optional[Comic] = None
        # Simple name normalization lookup
        norm_parsed = re.sub(r'[^a-z0-9]', '', series_name.lower())
        for c in comics:
            norm_c = re.sub(r'[^a-z0-9]', '', c.comic_name.lower())
            if norm_c == norm_parsed:
                # If year is parsed and we match year, select it
                if year and c.comic_year:
                    if int(year) == int(c.comic_year):
                        matched_comic = c
                        break
                # Fallback to first matching normalized name if no year discrepancy
                if matched_comic is None:
                    matched_comic = c

        if not matched_comic:
            raise ValueError(f"No matching active comic series found in database for: '{series_name}'")

        # 3. Match Issue under matched comic
        stmt_issues = select(Issue).where(Issue.comic_id == matched_comic.comic_id)
        res_issues = await self.session.execute(stmt_issues)
        all_issues = res_issues.scalars().all()

        matched_issue: Optional[Issue] = None
        for iss in all_issues:
            try:
                if float(iss.issue_number) == float(issue_number):
                    matched_issue = iss
                    break
            except ValueError:
                if iss.issue_number.strip().lower() == str(issue_number).strip().lower():
                    matched_issue = iss
                    break

        if not matched_issue:
            # In Mylar post-processing, we target Watched/Snatched issues.
            raise ValueError(f"No matching issue #{issue_number} found under series '{matched_comic.comic_name}'")

        # 4. Perform CBR to CBZ conversion if enabled & applicable
        working_file = filepath
        if settings.CBR2CBZ_ONLY and filepath.lower().endswith(".cbr"):
            try:
                working_file = await self.convert_cbr_to_cbz(filepath)
            except Exception as e:
                logger.error(f"[PostProcessor] CBR to CBZ conversion failed for {filename}: {e}")
                # Fall back to using the original CBR
                working_file = filepath

        # 5. Format Destination Folder & Filename
        pub_segment = self.clean_path_segment(matched_comic.publisher or "Unknown")
        series_segment = self.clean_path_segment(self.format_path(settings.FOLDER_FORMAT, matched_comic.comic_name, matched_comic.comic_year, None, matched_comic.publisher))
        
        dest_folder = os.path.join(settings.DESTINATION_DIR, pub_segment, series_segment)
        
        file_ext = os.path.splitext(working_file)[1]
        new_filename_base = self.format_path(settings.FILE_FORMAT, matched_comic.comic_name, matched_comic.comic_year, matched_issue.issue_number, matched_comic.publisher)
        new_filename = self.clean_path_segment(new_filename_base) + file_ext
        dest_filepath = os.path.join(dest_folder, new_filename)

        # Ensure destination folder exists
        if settings.CREATE_FOLDERS:
            os.makedirs(dest_folder, exist_ok=True)

        # 6. Apply ComicTagger Metadata if enabled
        if settings.ENABLE_META and settings.CMTAGGER_PATH:
            await self.run_comictagger(working_file, matched_comic, matched_issue)

        # 7. Move/Copy file to final destination
        if settings.MOVE_FILES:
            logger.info(f"[PostProcessor] Moving {working_file} to {dest_filepath}")
            shutil.move(working_file, dest_filepath)
            # Tidy up original parent directory if it's empty
            parent_dir = os.path.dirname(filepath)
            if parent_dir != settings.DESTINATION_DIR and os.path.isdir(parent_dir) and not os.listdir(parent_dir):
                shutil.rmtree(parent_dir)
        else:
            logger.info(f"[PostProcessor] Copying {working_file} to {dest_filepath}")
            shutil.copy2(working_file, dest_filepath)

        # If CBR was converted to a temp CBZ, delete the temp CBZ file
        if working_file != filepath and os.path.exists(working_file) and not settings.MOVE_FILES:
            os.remove(working_file)

        # 8. Update DB Issue status & location
        matched_issue.status = "Downloaded"
        matched_issue.location = os.path.relpath(dest_filepath, matched_comic.location or settings.DESTINATION_DIR)
        
        # Capture properties for notification/logging before session commit
        comic_title = matched_comic.comic_name
        issue_num = matched_issue.issue_number
        issue_id_val = matched_issue.issue_id

        self.session.add(matched_issue)
        await self.session.commit()

        # 9. Send Notifications
        notifier = get_notifier()
        if notifier:
            try:
                title = "Processed ✅"
                body = f"Success processing '{comic_title} #{issue_num}'\nSaved to: {new_filename}"
                await notifier.notify(title=title, body=body, notify_type="success")
            except Exception as e:
                logger.error(f"[PostProcessor] Apprise notification failed: {e}")

        logger.info(f"[PostProcessor] Successfully processed issue {issue_id_val} to location: {dest_filepath}")
        return dest_filepath

    async def convert_cbr_to_cbz(self, cbr_path: str) -> str:
        """
        Dummy / simple placeholder for CBR (RAR) to CBZ (ZIP) conversion.
        In alpine, without unrar binaries, this logs a warning and raises.
        If tools are available, unpacks cbr to temp dir and packs as zip.
        """
        logger.warning(f"[PostProcessor] CBR to CBZ conversion requested for {cbr_path} but alpine container lacks unrar. Skipping conversion.")
        raise NotImplementedError("CBR to CBZ requires system unrar/patool libraries.")

    async def run_comictagger(self, filepath: str, comic: Comic, issue: Issue) -> None:
        """
        Invokes ComicTagger CLI to write metadata tags to the CBZ/CBR file.
        """
        logger.info(f"[PostProcessor] Running ComicTagger for: {filepath}")
        cmd = [
            settings.CMTAGGER_PATH,
            "-t", "cr", # tag type: ComicRack
            "-f",       # overwrite
            "-s",       # save tags
            "-p",       # import metadata
            "--volume", str(comic.comic_year or ""),
            "--issue", issue.issue_number,
            "--series", comic.comic_name,
            filepath
        ]
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate()
            if process.returncode != 0:
                logger.error(f"[PostProcessor] ComicTagger exited with code {process.returncode}. Error: {stderr}")
            else:
                logger.info("[PostProcessor] ComicTagger completed successfully.")
        except Exception as e:
            logger.error(f"[PostProcessor] Failed to execute ComicTagger: {e}")
