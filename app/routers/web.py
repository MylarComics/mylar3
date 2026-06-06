import re
from typing import Optional
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.models.comic import Comic
from app.models.issue import Issue
from app.models.weekly import WeeklyPullList

from app.core.config import settings

def check_settings():
    settings.check_and_reload()

router = APIRouter(dependencies=[Depends(check_settings)])
templates = Jinja2Templates(directory="app/templates")

def get_numeric_issue_number(num_str: str) -> float:
    """
    Parse a numeric issue number float value for natural sorting.
    """
    match = re.match(r'^(\d+(?:\.\d+)?)', num_str)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return 999999.0

@router.get("/", response_class=HTMLResponse)
async def read_dashboard(request: Request, session: AsyncSession = Depends(get_session)):
    stmt_comics = select(Comic)
    result = await session.execute(stmt_comics)
    comics = result.scalars().all()
    
    # Calculate progress metadata for each comic
    comics_data = []
    for comic in comics:
        stmt_total = select(Issue).where(Issue.comic_id == comic.comic_id)
        res_total = await session.execute(stmt_total)
        issues_list = res_total.scalars().all()
        
        total_count = len(issues_list)
        downloaded_count = sum(1 for iss in issues_list if iss.status == "Downloaded")
        
        comics_data.append({
            "comic_id": comic.comic_id,
            "comic_name": comic.comic_name,
            "comic_year": comic.comic_year,
            "publisher": comic.publisher,
            "status": comic.status,
            "location": comic.location,
            "total_issues_count": total_count,
            "downloaded_count": downloaded_count
        })
        
    # Sort watchlist comics alphabetically
    comics_data.sort(key=lambda x: x["comic_name"].lower())

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"comics": comics_data, "active_page": "dashboard"}
    )

@router.get("/comics/{comic_id}", response_class=HTMLResponse)
async def read_comic_detail(
    comic_id: str, 
    request: Request, 
    session: AsyncSession = Depends(get_session)
):
    stmt_comic = select(Comic).where(Comic.comic_id == comic_id)
    result_comic = await session.execute(stmt_comic)
    comic = result_comic.scalars().first()
    
    if not comic:
        raise HTTPException(status_code=404, detail="Comic series not found")
        
    stmt_issues = select(Issue).where(Issue.comic_id == comic_id)
    result_issues = await session.execute(stmt_issues)
    issues = result_issues.scalars().all()
    
    # Sort issues numerically by issue number
    issues.sort(key=lambda x: get_numeric_issue_number(x.issue_number))
    
    return templates.TemplateResponse(
        request,
        "detail.html",
        {"comic": comic, "issues": issues, "active_page": "dashboard"}
    )

@router.get("/settings", response_class=HTMLResponse)
async def read_settings_page(request: Request):
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"settings": settings, "active_page": "settings"}
    )

@router.get("/weekly", response_class=HTMLResponse)
async def read_weekly_releases(
    request: Request,
    week: Optional[int] = None,
    year: Optional[int] = None,
    publisher: Optional[str] = None,
    session: AsyncSession = Depends(get_session)
):
    import datetime
    if week is None or year is None:
        today = datetime.date.today()
        if week is None:
            week = int(today.strftime("%U"))
        if year is None:
            year = today.year
            
    # Calculate previous and next week boundaries
    prev_week = week - 1
    prev_year = year
    if prev_week < 0:
        prev_week = 52
        prev_year -= 1
        
    next_week = week + 1
    next_year = year
    if next_week > 52:
        next_week = 0
        next_year += 1

    # Fetch weekly releases
    stmt = select(WeeklyPullList).where(
        WeeklyPullList.weeknumber == week,
        WeeklyPullList.year == year
    )
    res = await session.execute(stmt)
    releases = res.scalars().all()
    
    # Extract unique publishers
    publishers = sorted(list(set(r.publisher for r in releases if r.publisher)))
    
    # Filter by publisher if requested
    if publisher:
        releases = [r for r in releases if r.publisher == publisher]
        
    # Sort releases alphabetically
    releases.sort(key=lambda r: (r.publisher or "", r.comic.lower()))

    return templates.TemplateResponse(
        request,
        "weekly.html",
        {
            "releases": releases,
            "publishers": publishers,
            "selected_pub": publisher,
            "week": week,
            "year": year,
            "prev_week": prev_week,
            "prev_year": prev_year,
            "next_week": next_week,
            "next_year": next_year,
            "active_page": "weekly"
        }
    )

@router.get("/import", response_class=HTMLResponse)
async def read_import_page(request: Request):
    return templates.TemplateResponse(
        request,
        "import.html",
        {"active_page": "import"}
    )
