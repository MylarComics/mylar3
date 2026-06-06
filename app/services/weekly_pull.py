import re
import httpx
import datetime
from typing import Dict, Any, List, Optional
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import logger
from app.models.weekly import WeeklyPullList
from app.models.comic import Comic
from app.models.issue import Issue
from app.notifications.factory import get_notifier

class WeeklyPullService:
    """
    Service responsible for fetching new release schedules from League of Comic Geeks proxy,
    synchronizing them in the DB, and auto-matching new releases against the user's watchlist.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.client = httpx.AsyncClient(verify=settings.CV_VERIFY, timeout=15.0)

    async def get_current_week_info(self) -> Dict[str, Any]:
        """
        Helper to calculate the current week number and year.
        """
        today = datetime.date.today()
        # %U: Week number of the year (Sunday as the first day of the week)
        weeknumber = int(today.strftime("%U"))
        year = today.year
        return {"week": weeknumber, "year": year}

    def normalize_name(self, name: str) -> str:
        """
        Normalized name for lookup matching (alphanumeric only, lowercase).
        """
        return re.sub(r'[^a-z0-9]', '', name.lower()).strip()

    async def fetch_and_sync(self, week: Optional[int] = None, year: Optional[int] = None) -> Dict[str, Any]:
        """
        Fetches the weekly release schedule from the walksoftly proxy and syncs it.
        """
        if week is None or year is None:
            info = await self.get_current_week_info()
            week = week if week is not None else info["week"]
            year = year if year is not None else info["year"]

        url = "https://walksoftly.itsaninja.party/newcomics.php"
        params = {"week": str(week), "year": str(year)}

        logger.info(f"[WeeklyPull] Fetching weekly pull list for week {week}, year {year} from proxy...")
        
        try:
            response = await self.client.get(url, params=params)
            if response.status_code != 200:
                logger.error(f"[WeeklyPull] Proxy returned HTTP {response.status_code}")
                return {"status": "failure", "message": f"Proxy returned HTTP {response.status_code}"}
            
            data = response.json()
        except Exception as e:
            logger.error(f"[WeeklyPull] Failed to fetch weekly releases: {e}")
            return {"status": "failure", "message": str(e)}

        if not data:
            logger.warning(f"[WeeklyPull] Received empty list of releases for week {week}, year {year}")
            return {"status": "success", "count": 0}

        logger.info(f"[WeeklyPull] Retrieved {len(data)} releases from proxy. Commencing DB sync...")

        # Get active comics watchlist
        stmt_comics = select(Comic).where(Comic.status == "Active")
        res_comics = await self.session.execute(stmt_comics)
        watched_comics = res_comics.scalars().all()
        
        # Create lookup map
        watched_map = {self.normalize_name(c.comic_name): c for c in watched_comics}

        added_count = 0
        matched_count = 0
        new_issues_added = []

        # Delete existing weekly records for this week to rebuild fresh
        stmt_delete = select(WeeklyPullList).where(
            WeeklyPullList.weeknumber == week,
            WeeklyPullList.year == year
        )
        res_delete = await self.session.execute(stmt_delete)
        for old_record in res_delete.scalars().all():
            await self.session.delete(old_record)
        await self.session.flush()

        for item in data:
            series_name = item.get("series", "").strip()
            issue_val = str(item.get("issue", "")).replace("#", "").strip()
            publisher = item.get("publisher", "").strip()
            shipdate = item.get("shipdate", "").strip()
            cv_comicid = item.get("comicid")
            cv_issueid = item.get("issueid")

            if not series_name:
                continue

            dyn_name = self.normalize_name(series_name)
            
            # Check watchlist matching
            matched_comic = watched_map.get(dyn_name)
            status = "Skipped"
            comic_id_db = str(cv_comicid) if cv_comicid else None

            if matched_comic:
                status = "Wanted"
                comic_id_db = matched_comic.comic_id
                matched_count += 1
                
                # If matched, verify if the issue is in the Issue table
                if cv_issueid:
                    stmt_iss = select(Issue).where(Issue.issue_id == str(cv_issueid))
                    res_iss = await self.session.execute(stmt_iss)
                    existing_issue = res_iss.scalars().first()
                    
                    if not existing_issue:
                        # Add new issue automatically as Wanted
                        new_iss = Issue(
                            issue_id=str(cv_issueid),
                            comic_id=matched_comic.comic_id,
                            issue_number=issue_val,
                            issue_name=item.get("title", f"Issue #{issue_val}"),
                            release_date=shipdate,
                            status="Wanted"
                        )
                        self.session.add(new_iss)
                        new_issues_added.append(new_iss)
                        logger.info(f"[WeeklyPull] Auto-added new issue: {series_name} #{issue_val} to watchlist")

            record = WeeklyPullList(
                shipdate=shipdate,
                publisher=publisher,
                issue=issue_val,
                comic=series_name,
                extra=item.get("type", ""),
                status=status,
                comic_id=comic_id_db,
                issue_id=str(cv_issueid) if cv_issueid else None,
                dynamic_name=dyn_name,
                weeknumber=week,
                year=year,
                volume=str(item.get("volume", "")),
                seriesyear=str(item.get("seriesyear", "")),
                annuallink=item.get("link", ""),
                format=item.get("type", "")
            )
            self.session.add(record)
            added_count += 1

        try:
            await self.session.commit()
            logger.info(f"[WeeklyPull] Successfully synchronized {added_count} weekly releases. Matched {matched_count} watchlist series.")
            
            # If new issues discovered, trigger Apprise notification
            if new_issues_added and settings.NOTIFY_ON_NEW_ISSUES:
                notifier = get_notifier()
                if notifier:
                    title = "New Releases Discovered 📚"
                    body = "\n".join([f"- {item.issue_name} (Issue #{item.issue_number})" for item in new_issues_added])
                    await notifier.notify(title=title, body=body, notify_type="info")
                    
            return {"status": "success", "count": added_count, "matched": matched_count, "new_issues": len(new_issues_added)}
        except Exception as e:
            logger.error(f"[WeeklyPull] Database transaction failed during pull list save: {e}")
            await self.session.rollback()
            return {"status": "failure", "message": str(e)}
            
    async def close(self):
        await self.client.aclose()
