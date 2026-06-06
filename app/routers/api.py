from typing import Optional
from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.models.comic import Comic
from app.models.issue import Issue
from app.notifications.factory import get_notifier
from app.services.cv_api import ComicVineClient
from app.services.importer import add_comic_to_db
from app.services.search import search_issue
from app.core.logger import logger
from app.core.config import settings

def check_settings():
    settings.check_and_reload()

router = APIRouter(prefix="/api", dependencies=[Depends(check_settings)])
templates = Jinja2Templates(directory="app/templates")

@router.get("/search-cv", response_class=HTMLResponse)
async def search_comicvine(request: Request, q: str = ""):
    if not q or len(q.strip()) < 2:
        return HTMLResponse(content="")
    
    cv_client = ComicVineClient()
    try:
        volumes = await cv_client.search_volumes(q)
    except Exception as e:
        logger.error(f"ComicVine search failed: {e}")
        return HTMLResponse(content='<div style="padding: 1.5rem; text-align: center; color: var(--accent-rose);">Search failed. Please check your API key and internet connectivity.</div>')
        
    return templates.TemplateResponse(
        request,
        "components/search_results.html",
        {"volumes": volumes}
    )

@router.post("/comics/add", response_class=HTMLResponse)
async def add_comic(
    request: Request,
    comic_id: str = Form(...),
    session: AsyncSession = Depends(get_session)
):
    # Check if comic already exists
    stmt_check = select(Comic).where(Comic.comic_id == comic_id)
    res_check = await session.execute(stmt_check)
    existing_comic = res_check.scalars().first()
    if existing_comic:
        return HTMLResponse(content="", status_code=204)

    try:
        comic = await add_comic_to_db(session, comic_id)
    except Exception as e:
        logger.error(f"Failed to add comic: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to add comic: {e}")

    if not comic:
        raise HTTPException(status_code=400, detail="Failed to add comic from ComicVine.")

    # Calculate counts
    stmt_total = select(Issue).where(Issue.comic_id == comic.comic_id)
    res_total = await session.execute(stmt_total)
    issues_list = res_total.scalars().all()
    total_count = len(issues_list)
    downloaded_count = sum(1 for iss in issues_list if iss.status == "Downloaded")
    
    comic_data = {
        "comic_id": comic.comic_id,
        "comic_name": comic.comic_name,
        "comic_year": comic.comic_year,
        "publisher": comic.publisher,
        "status": comic.status,
        "location": comic.location,
        "total_issues_count": total_count,
        "downloaded_count": downloaded_count
    }
    
    # Get total tracked comics count
    stmt_all = select(Comic)
    res_all = await session.execute(stmt_all)
    all_comics = res_all.scalars().all()
    new_tracked_count = len(all_comics)

    # Render card HTML
    card_html = templates.TemplateResponse(
        request,
        "components/comic_card.html",
        {"comic": comic_data}
    ).body.decode("utf-8")

    # HTMX Out-of-band swaps
    oob_count = f'<span id="watchlist-count" hx-swap-oob="outerHTML" style="font-size: 0.9rem; color: var(--text-secondary);">{new_tracked_count} Series tracked</span>'
    oob_empty = '<div id="watchlist-empty" hx-swap-oob="outerHTML"></div>'
    
    full_response = f"{card_html}\n{oob_count}\n{oob_empty}"
    return HTMLResponse(content=full_response)

@router.post("/comics/{comic_id}/toggle", response_class=HTMLResponse)
async def toggle_comic_status(comic_id: str, session: AsyncSession = Depends(get_session)):
    stmt = select(Comic).where(Comic.comic_id == comic_id)
    result = await session.execute(stmt)
    comic = result.scalars().first()
    if not comic:
        raise HTTPException(status_code=404, detail="Comic not found")
    
    comic.status = "Paused" if comic.status == "Active" else "Active"
    session.add(comic)
    await session.commit()
    await session.refresh(comic)
    
    badge_class = "badge-active" if comic.status == "Active" else "badge-paused"
    return f"""
    <span class="badge {badge_class}"
          id="status-badge-{comic.comic_id}"
          hx-post="/api/comics/{comic.comic_id}/toggle"
          hx-target="#status-badge-{comic.comic_id}"
          hx-swap="outerHTML">
        {comic.status}
    </span>
    """

@router.delete("/comics/{comic_id}", response_class=HTMLResponse)
async def delete_comic(
    comic_id: str,
    session: AsyncSession = Depends(get_session)
):
    stmt = select(Comic).where(Comic.comic_id == comic_id)
    res = await session.execute(stmt)
    comic = res.scalars().first()
    if not comic:
        raise HTTPException(status_code=404, detail="Comic not found")

    # Delete all associated issues first
    stmt_issues = select(Issue).where(Issue.comic_id == comic_id)
    res_issues = await session.execute(stmt_issues)
    for issue in res_issues.scalars().all():
        await session.delete(issue)

    await session.delete(comic)
    await session.commit()

    # Get remaining comics count
    stmt_all = select(Comic)
    res_all = await session.execute(stmt_all)
    remaining_comics = res_all.scalars().all()
    new_count = len(remaining_comics)

    # Since the hx-delete target is the card and hx-swap is outerHTML,
    # the main HTML response is replaced/removed in DOM (so empty string).
    # We add OOB elements:
    oob_elements = [
        f'<span id="watchlist-count" hx-swap-oob="outerHTML" style="font-size: 0.9rem; color: var(--text-secondary);">{new_count} Series tracked</span>'
    ]
    if new_count == 0:
        empty_placeholder = """
        <div id="watchlist-empty" hx-swap-oob="beforeend:#watchlist-grid" style="grid-column: 1/-1; text-align: center; padding: 4rem 1.5rem; background-color: var(--bg-surface); border: 1px dashed var(--border-color); border-radius: 12px; color: var(--text-secondary);">
            <p style="font-size: 1.1rem; margin-bottom: 1rem;">No comics in your watchlist yet.</p>
            <p style="font-size: 0.9rem; color: var(--text-muted);">Use the search bar above to find and add comics from ComicVine!</p>
        </div>
        """
        oob_elements.append(empty_placeholder)

    return HTMLResponse(content="\n".join(oob_elements))

@router.post("/issues/{issue_id}/toggle", response_class=HTMLResponse)
async def toggle_issue_status(issue_id: str, session: AsyncSession = Depends(get_session)):
    stmt = select(Issue).where(Issue.issue_id == issue_id)
    result = await session.execute(stmt)
    issue = result.scalars().first()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
        
    status_cycle = {
        "Skipped": "Wanted",
        "Wanted": "Snatched",
        "Snatched": "Downloaded",
        "Downloaded": "Skipped"
    }
    
    issue.status = status_cycle.get(issue.status, "Skipped")
    session.add(issue)
    await session.commit()
    await session.refresh(issue)
    
    badge_classes = {
        "Wanted": "badge-wanted",
        "Snatched": "badge-snatched",
        "Downloaded": "badge-downloaded",
        "Skipped": "badge-skipped"
    }
    badge_class = badge_classes.get(issue.status, "badge-skipped")
    
    return f"""
    <span class="badge {badge_class}"
          id="issue-badge-{issue.issue_id}"
          hx-post="/api/issues/{issue.issue_id}/toggle"
          hx-target="#issue-badge-{issue.issue_id}"
          hx-swap="outerHTML">
        {issue.status}
    </span>
    """

@router.post("/issues/{issue_id}/search", response_class=HTMLResponse)
async def manual_search_issue(
    request: Request,
    issue_id: str,
    session: AsyncSession = Depends(get_session)
):
    stmt_issue = select(Issue).where(Issue.issue_id == issue_id)
    res_issue = await session.execute(stmt_issue)
    issue = res_issue.scalars().first()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    stmt_comic = select(Comic).where(Comic.comic_id == issue.comic_id)
    res_comic = await session.execute(stmt_comic)
    comic = res_comic.scalars().first()
    if not comic:
        raise HTTPException(status_code=404, detail="Comic not found")

    # Run the search
    try:
        results = await search_issue(comic, issue)
        if results:
            issue.status = "Snatched"
            session.add(issue)
            await session.commit()
            await session.refresh(issue)
    except Exception as e:
        logger.error(f"Manual issue search failed: {e}")

    # Render updated issue row HTML
    return templates.TemplateResponse(
        request,
        "components/issue_row.html",
        {"issue": issue}
    )


@router.post("/notifications/test", response_class=JSONResponse)
async def test_notification():
    """
    Send a test notification to all configured Apprise services.
    Returns JSON indicating success or failure so users can verify
    their APPRISE_URLS setup without needing to trigger a real grab.
    """
    notifier = get_notifier()
    if notifier is None:
        return JSONResponse(
            status_code=200,
            content={"ok": False, "message": "No notification URLs configured (APPRISE_URLS is empty)."}
        )

    try:
        success = await notifier.notify(
            title="Mylar3 Test Notification 🧠",
            body="Notification system is working correctly! Your Apprise setup is configured.",
            notify_type="success",
        )
        if success:
            logger.info("[Notifications] Test notification sent successfully.")
            return JSONResponse(
                status_code=200,
                content={"ok": True, "message": "Test notification sent successfully."}
            )
        else:
            return JSONResponse(
                status_code=200,
                content={"ok": False, "message": "Notification was dispatched but one or more services reported failure."}
            )
    except Exception as exc:
        logger.error(f"[Notifications] Test notification failed: {exc}")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "message": f"Exception: {exc}"}
        )

@router.post("/postprocess")
async def api_postprocess(
    folder_path: str = Form(...),
    nzb_name: Optional[str] = Form(None),
    status: Optional[str] = Form("success")
):
    from app.tasks.post_process import post_process_folder
    task = post_process_folder.delay(folder_path, nzb_name, status)
    return {"ok": True, "task_id": task.id}

@router.post("/weekly/sync")
async def sync_weekly_releases(
    week: Optional[int] = Form(None),
    year: Optional[int] = Form(None),
    session: AsyncSession = Depends(get_session)
):
    from app.services.weekly_pull import WeeklyPullService
    service = WeeklyPullService(session)
    try:
        res = await service.fetch_and_sync(week, year)
        return res
    finally:
        await service.close()

@router.post("/settings")
async def update_settings(request: Request, session: AsyncSession = Depends(get_session)):
    form_data = await request.form()
    new_settings = {}
    for k, v in form_data.items():
        new_settings[k] = v
        
    from app.services.settings_service import save_settings
    success = await save_settings(session, new_settings)
    if success:
        return JSONResponse({"ok": True})
    else:
        return JSONResponse({"ok": False, "message": "Failed to save settings to database"})

@router.post("/import/scan", response_class=HTMLResponse)
async def api_import_scan(
    request: Request,
    scan_dir: str = Form(...),
    session: AsyncSession = Depends(get_session)
):
    from app.services.library_sync import LibrarySyncService
    service = LibrarySyncService(session)
    res = await service.scan_and_sync_library(scan_dir)
    
    return templates.TemplateResponse(
        request,
        "components/import_results.html",
        {
            "synced_count": res["synced_files_count"],
            "candidates": res["unmatched_candidates"]
        }
    )
