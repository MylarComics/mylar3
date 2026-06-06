import os
import zipfile
from datetime import datetime
from typing import Optional, List, Dict, Any
from urllib.parse import quote_plus
from fastapi import APIRouter, Request, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from PIL import Image
from io import BytesIO

from app.core.db import get_session
from app.models.comic import Comic
from app.models.issue import Issue
from app.core.config import settings
from app.core.logger import logger

def check_settings():
    settings.check_and_reload()

router = APIRouter(prefix="/opds", dependencies=[Depends(check_settings)])
templates = Jinja2Templates(directory="app/templates")

def get_zip_page_count(filepath: str) -> int:
    """
    Get the count of image pages inside a ZIP/CBZ comic book archive.
    """
    if not os.path.exists(filepath):
        return 0
    try:
        if zipfile.is_zipfile(filepath):
            with zipfile.ZipFile(filepath) as z:
                names = sorted([n for n in z.namelist() if n.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))])
                return len(names)
    except Exception as e:
        logger.error(f"[OPDS] Error reading zip page count from {filepath}: {e}")
    return 0

def get_zip_page_data(filepath: str, page_num: int, width: Optional[int] = None) -> Optional[tuple[bytes, str]]:
    """
    Retrieve raw bytes and mime type for a specific page in a ZIP/CBZ archive,
    with optional on-the-fly scaling.
    """
    if not os.path.exists(filepath):
        return None
    try:
        if zipfile.is_zipfile(filepath):
            with zipfile.ZipFile(filepath) as z:
                names = sorted([n for n in z.namelist() if n.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))])
                if page_num < 0 or page_num >= len(names):
                    logger.warning(f"[OPDS] Page {page_num} out of bounds for {filepath} (total pages: {len(names)})")
                    return None
                page_name = names[page_num]
                ext = os.path.splitext(page_name)[1][1:].lower()
                if ext == 'jpg':
                    ext = 'jpeg'
                
                with z.open(page_name) as f:
                    img_data = f.read()
                
                mime_type = f"image/{ext}"
                if width:
                    try:
                        img = Image.open(BytesIO(img_data))
                        scale = width / float(img.size[0])
                        height = int(scale * img.size[1])
                        # Handle color profile transformation for JPEG saving
                        if ext == 'jpeg' and img.mode in ("RGBA", "P"):
                            img = img.convert("RGB")
                        img = img.resize((width, height), Image.Resampling.LANCZOS)
                        
                        out_io = BytesIO()
                        img.save(out_io, format=ext.upper())
                        return out_io.getvalue(), mime_type
                    except Exception as resize_err:
                        logger.error(f"[OPDS] Failed resizing page {page_num}: {resize_err}")
                        return img_data, mime_type
                else:
                    return img_data, mime_type
    except Exception as e:
        logger.error(f"[OPDS] Error reading zip page data from {filepath}: {e}")
    return None

@router.get("", response_class=Response)
async def opds_catalog(
    request: Request,
    cmd: Optional[str] = Query(None),
    index: int = Query(0),
    pubid: Optional[str] = Query(None),
    comicid: Optional[str] = Query(None),
    issueid: Optional[str] = Query(None),
    page: Optional[int] = Query(None),
    width: Optional[int] = Query(None),
    session: AsyncSession = Depends(get_session)
):
    if not settings.OPDS_ENABLE:
        raise HTTPException(status_code=403, detail="OPDS server is disabled.")

    base_url = str(request.base_url).rstrip('/') + "/opds"
    page_size = settings.OPDS_PAGESIZE
    now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # Command Router
    command = cmd or "root"

    if command == "root":
        # Root Catalog
        # Count all unique publishers
        stmt_publishers = select(Comic.publisher).where(Comic.publisher != None).group_by(Comic.publisher)
        res_pub = await session.execute(stmt_publishers)
        publishers = res_pub.scalars().all()
        pub_count = len(publishers)

        # Count all watchlist comics
        stmt_comics = select(Comic)
        res_comics = await session.execute(stmt_comics)
        comics = res_comics.scalars().all()
        comics_count = len(comics)

        links = [
            {"rel": "start", "href": base_url, "type": "application/atom+xml; profile=opds-catalog; kind=navigation", "title": "Home"},
            {"rel": "self", "href": f"{base_url}?cmd=root", "type": "application/atom+xml; profile=opds-catalog; kind=navigation"}
        ]

        entries = [
            {
                "title": "Recent Arrivals",
                "id": "Recent",
                "updated": now_str,
                "content": "Recently post-processed and downloaded comic books",
                "href": f"{base_url}?cmd=Recent",
                "kind": "acquisition",
                "rel": "subsection"
            }
        ]

        if pub_count > 0:
            entries.append({
                "title": f"Publishers ({pub_count})",
                "id": "Publishers",
                "updated": now_str,
                "content": "Browse watchlist series grouped by publisher",
                "href": f"{base_url}?cmd=Publishers",
                "kind": "navigation",
                "rel": "subsection"
            })

        if comics_count > 0:
            entries.append({
                "title": f"All Titles ({comics_count})",
                "id": "AllTitles",
                "updated": now_str,
                "content": "Browse all monitored comic series",
                "href": f"{base_url}?cmd=AllTitles",
                "kind": "navigation",
                "rel": "subsection"
            })

        xml_content = templates.TemplateResponse(
            request,
            "opds.xml",
            {
                "title": "Mylar OPDS Catalog",
                "id": "mylar:opds:root",
                "updated": now_str,
                "links": links,
                "entries": entries
            }
        )
        return Response(content=xml_content.body, media_type="application/atom+xml; charset=utf-8")

    elif command == "Publishers":
        # Group by publishers
        stmt = select(Comic.publisher).where(Comic.publisher != None).group_by(Comic.publisher)
        res = await session.execute(stmt)
        publishers = sorted(res.scalars().all())

        links = [
            {"rel": "start", "href": base_url, "type": "application/atom+xml; profile=opds-catalog; kind=navigation", "title": "Home"},
            {"rel": "self", "href": f"{base_url}?cmd=Publishers&index={index}", "type": "application/atom+xml; profile=opds-catalog; kind=navigation"}
        ]

        entries = []
        for pub in publishers:
            # Count titles under this publisher
            stmt_count = select(Comic).where(Comic.publisher == pub)
            res_count = await session.execute(stmt_count)
            titles_count = len(res_count.scalars().all())

            entries.append({
                "title": f"{pub} ({titles_count})",
                "id": f"publisher:{pub}",
                "updated": now_str,
                "content": f"Browse {titles_count} series from {pub}",
                "href": f"{base_url}?cmd=Publisher&pubid={quote_plus(pub)}",
                "kind": "navigation",
                "rel": "subsection"
            })

        # Pagination logic
        paginated_entries = entries[index:index + page_size]
        if len(entries) > index + page_size:
            links.append({"rel": "next", "href": f"{base_url}?cmd=Publishers&index={index + page_size}", "type": "application/atom+xml; profile=opds-catalog; kind=navigation"})
        if index >= page_size:
            links.append({"rel": "previous", "href": f"{base_url}?cmd=Publishers&index={index - page_size}", "type": "application/atom+xml; profile=opds-catalog; kind=navigation"})

        xml_content = templates.TemplateResponse(
            request,
            "opds.xml",
            {
                "title": "OPDS - Publishers",
                "id": "mylar:opds:publishers",
                "updated": now_str,
                "links": links,
                "entries": paginated_entries
            }
        )
        return Response(content=xml_content.body, media_type="application/atom+xml; charset=utf-8")

    elif command == "Publisher":
        if not pubid:
            raise HTTPException(status_code=400, detail="Missing pubid parameter.")

        stmt = select(Comic).where(Comic.publisher == pubid)
        res = await session.execute(stmt)
        comics = sorted(res.scalars().all(), key=lambda c: c.comic_name.lower())

        links = [
            {"rel": "start", "href": base_url, "type": "application/atom+xml; profile=opds-catalog; kind=navigation", "title": "Home"},
            {"rel": "self", "href": f"{base_url}?cmd=Publisher&pubid={quote_plus(pubid)}&index={index}", "type": "application/atom+xml; profile=opds-catalog; kind=navigation"}
        ]

        entries = []
        for comic in comics:
            entries.append({
                "title": f"{comic.comic_name} ({comic.comic_year or ''})",
                "id": f"comic:{comic.comic_id}",
                "updated": now_str,
                "content": f"{comic.comic_name} series detail",
                "href": f"{base_url}?cmd=Comic&comicid={comic.comic_id}",
                "kind": "acquisition",
                "rel": "subsection"
            })

        paginated_entries = entries[index:index + page_size]
        if len(entries) > index + page_size:
            links.append({"rel": "next", "href": f"{base_url}?cmd=Publisher&pubid={quote_plus(pubid)}&index={index + page_size}", "type": "application/atom+xml; profile=opds-catalog; kind=navigation"})
        if index >= page_size:
            links.append({"rel": "previous", "href": f"{base_url}?cmd=Publisher&pubid={quote_plus(pubid)}&index={index - page_size}", "type": "application/atom+xml; profile=opds-catalog; kind=navigation"})

        xml_content = templates.TemplateResponse(
            request,
            "opds.xml",
            {
                "title": f"Publisher - {pubid}",
                "id": f"mylar:opds:publisher:{pubid}",
                "updated": now_str,
                "links": links,
                "entries": paginated_entries
            }
        )
        return Response(content=xml_content.body, media_type="application/atom+xml; charset=utf-8")

    elif command == "AllTitles":
        stmt = select(Comic)
        res = await session.execute(stmt)
        comics = sorted(res.scalars().all(), key=lambda c: c.comic_name.lower())

        links = [
            {"rel": "start", "href": base_url, "type": "application/atom+xml; profile=opds-catalog; kind=navigation", "title": "Home"},
            {"rel": "self", "href": f"{base_url}?cmd=AllTitles&index={index}", "type": "application/atom+xml; profile=opds-catalog; kind=navigation"}
        ]

        entries = []
        for comic in comics:
            entries.append({
                "title": f"{comic.comic_name} ({comic.comic_year or ''})",
                "id": f"comic:{comic.comic_id}",
                "updated": now_str,
                "content": f"{comic.comic_name} ({comic.comic_year or ''}) monitored series",
                "href": f"{base_url}?cmd=Comic&comicid={comic.comic_id}",
                "kind": "acquisition",
                "rel": "subsection"
            })

        paginated_entries = entries[index:index + page_size]
        if len(entries) > index + page_size:
            links.append({"rel": "next", "href": f"{base_url}?cmd=AllTitles&index={index + page_size}", "type": "application/atom+xml; profile=opds-catalog; kind=navigation"})
        if index >= page_size:
            links.append({"rel": "previous", "href": f"{base_url}?cmd=AllTitles&index={index - page_size}", "type": "application/atom+xml; profile=opds-catalog; kind=navigation"})

        xml_content = templates.TemplateResponse(
            request,
            "opds.xml",
            {
                "title": "All Titles",
                "id": "mylar:opds:alltitles",
                "updated": now_str,
                "links": links,
                "entries": paginated_entries
            }
        )
        return Response(content=xml_content.body, media_type="application/atom+xml; charset=utf-8")

    elif command == "Comic":
        if not comicid:
            raise HTTPException(status_code=400, detail="Missing comicid parameter.")

        stmt_comic = select(Comic).where(Comic.comic_id == comicid)
        res_comic = await session.execute(stmt_comic)
        comic = res_comic.scalars().first()
        if not comic:
            raise HTTPException(status_code=404, detail="Comic series not found.")

        # Get issues with a location value (downloaded files)
        stmt_issues = select(Issue).where(Issue.comic_id == comicid).where(Issue.location != None)
        res_issues = await session.execute(stmt_issues)
        issues_list = res_issues.scalars().all()

        # Sort naturally by issue number
        def get_sort_key(iss):
            try:
                return float(iss.issue_number)
            except ValueError:
                return 99999.0
        issues_list.sort(key=get_sort_key)

        links = [
            {"rel": "start", "href": base_url, "type": "application/atom+xml; profile=opds-catalog; kind=navigation", "title": "Home"},
            {"rel": "self", "href": f"{base_url}?cmd=Comic&comicid={comicid}&index={index}", "type": "application/atom+xml; profile=opds-catalog; kind=navigation"}
        ]

        entries = []
        for issue in issues_list:
            if not comic.location or not issue.location:
                continue
            filepath = os.path.normpath(os.path.join(comic.location, issue.location))
            if not os.path.isfile(filepath):
                logger.warning(f"[OPDS] File is missing on disk, skipping: {filepath}")
                continue

            pse_count = get_zip_page_count(filepath)

            entries.append({
                "title": f"{comic.comic_name} #{issue.issue_number} - {issue.issue_name or 'No Title'}",
                "id": f"issue:{issue.issue_id}",
                "updated": now_str,
                "content": f"{comic.comic_name} #{issue.issue_number} published on {issue.release_date or 'unknown date'}.",
                "href": f"{base_url}?cmd=deliverFile&issueid={issue.issue_id}",
                "stream": f"{base_url}?cmd=Stream&issueid={issue.issue_id}",
                "pse_count": pse_count,
                "kind": "acquisition",
                "rel": "file",
                "thumbnail": f"{base_url}?cmd=Stream&issueid={issue.issue_id}&page=0&width=300"
            })

        paginated_entries = entries[index:index + page_size]
        if len(entries) > index + page_size:
            links.append({"rel": "next", "href": f"{base_url}?cmd=Comic&comicid={comicid}&index={index + page_size}", "type": "application/atom+xml; profile=opds-catalog; kind=navigation"})
        if index >= page_size:
            links.append({"rel": "previous", "href": f"{base_url}?cmd=Comic&comicid={comicid}&index={index - page_size}", "type": "application/atom+xml; profile=opds-catalog; kind=navigation"})

        xml_content = templates.TemplateResponse(
            request,
            "opds.xml",
            {
                "title": f"Series - {comic.comic_name}",
                "id": f"mylar:opds:comic:{comic.comic_id}",
                "updated": now_str,
                "links": links,
                "entries": paginated_entries
            }
        )
        return Response(content=xml_content.body, media_type="application/atom+xml; charset=utf-8")

    elif command == "Recent":
        # Get downloaded issues sorted by ID decending (most recent first)
        stmt = select(Issue).where(Issue.location != None).where(Issue.status == "Downloaded").order_by(Issue.id.desc())
        res = await session.execute(stmt)
        issues_list = res.scalars().all()

        links = [
            {"rel": "start", "href": base_url, "type": "application/atom+xml; profile=opds-catalog; kind=navigation", "title": "Home"},
            {"rel": "self", "href": f"{base_url}?cmd=Recent&index={index}", "type": "application/atom+xml; profile=opds-catalog; kind=navigation"}
        ]

        entries = []
        for issue in issues_list:
            stmt_comic = select(Comic).where(Comic.comic_id == issue.comic_id)
            res_comic = await session.execute(stmt_comic)
            comic = res_comic.scalars().first()
            if not comic or not comic.location or not issue.location:
                continue

            filepath = os.path.normpath(os.path.join(comic.location, issue.location))
            if not os.path.isfile(filepath):
                continue

            pse_count = get_zip_page_count(filepath)

            entries.append({
                "title": f"{comic.comic_name} #{issue.issue_number} - {issue.issue_name or 'No Title'}",
                "id": f"issue:{issue.issue_id}",
                "updated": now_str,
                "content": f"{comic.comic_name} #{issue.issue_number} downloaded recently.",
                "href": f"{base_url}?cmd=deliverFile&issueid={issue.issue_id}",
                "stream": f"{base_url}?cmd=Stream&issueid={issue.issue_id}",
                "pse_count": pse_count,
                "kind": "acquisition",
                "rel": "file",
                "thumbnail": f"{base_url}?cmd=Stream&issueid={issue.issue_id}&page=0&width=300"
            })

        paginated_entries = entries[index:index + page_size]
        if len(entries) > index + page_size:
            links.append({"rel": "next", "href": f"{base_url}?cmd=Recent&index={index + page_size}", "type": "application/atom+xml; profile=opds-catalog; kind=navigation"})
        if index >= page_size:
            links.append({"rel": "previous", "href": f"{base_url}?cmd=Recent&index={index - page_size}", "type": "application/atom+xml; profile=opds-catalog; kind=navigation"})

        xml_content = templates.TemplateResponse(
            request,
            "opds.xml",
            {
                "title": "Recent Arrivals",
                "id": "mylar:opds:recent",
                "updated": now_str,
                "links": links,
                "entries": paginated_entries
            }
        )
        return Response(content=xml_content.body, media_type="application/atom+xml; charset=utf-8")

    elif command == "deliverFile":
        if not issueid:
            raise HTTPException(status_code=400, detail="Missing issueid parameter.")

        stmt_issue = select(Issue).where(Issue.issue_id == issueid)
        res_issue = await session.execute(stmt_issue)
        issue = res_issue.scalars().first()
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found.")

        stmt_comic = select(Comic).where(Comic.comic_id == issue.comic_id)
        res_comic = await session.execute(stmt_comic)
        comic = res_comic.scalars().first()
        if not comic or not comic.location or not issue.location:
            raise HTTPException(status_code=404, detail="Comic directory or file path missing.")

        filepath = os.path.normpath(os.path.join(comic.location, issue.location))
        if not os.path.isfile(filepath):
            raise HTTPException(status_code=404, detail="Comic archive file not found on disk.")

        filename = os.path.basename(filepath)
        return FileResponse(filepath, media_type="application/octet-stream", filename=filename)

    elif command == "Stream":
        if not issueid:
            raise HTTPException(status_code=400, detail="Missing issueid parameter.")
        
        # Default page to 0 if not specified (crucial for inline thumbnails)
        page_val = page if page is not None else 0

        stmt_issue = select(Issue).where(Issue.issue_id == issueid)
        res_issue = await session.execute(stmt_issue)
        issue = res_issue.scalars().first()
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found.")

        stmt_comic = select(Comic).where(Comic.comic_id == issue.comic_id)
        res_comic = await session.execute(stmt_comic)
        comic = res_comic.scalars().first()
        if not comic or not comic.location or not issue.location:
            raise HTTPException(status_code=404, detail="Comic directory or file path missing.")

        filepath = os.path.normpath(os.path.join(comic.location, issue.location))
        if not os.path.isfile(filepath):
            raise HTTPException(status_code=404, detail="Comic archive file not found on disk.")

        if filepath.lower().endswith(".cbr") and not zipfile.is_zipfile(filepath):
            # CBR files require a conversion or patool extraction. To keep it clean and performant,
            # throw a warning/error since modern Mylar focuses on CBZ for OPDS web streaming.
            raise HTTPException(status_code=500, detail="Streaming from CBR (RAR) archives is not supported. Please use CBZ format.")

        res_data = get_zip_page_data(filepath, page_val, width)
        if res_data is None:
            raise HTTPException(status_code=404, detail="Page not found inside comic archive.")

        image_bytes, mime_type = res_data
        return Response(content=image_bytes, media_type=mime_type)

    else:
        raise HTTPException(status_code=400, detail=f"Unknown command: {command}")
