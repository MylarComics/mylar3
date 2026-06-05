import re
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.models.comic import Comic
from app.models.issue import Issue

router = APIRouter()
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
