import os
import re
import json
import httpx
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from app.core.config import settings
from app.core.logger import logger
from app.services.search import SearchResultItem
from app.models.comic import Comic
from app.models.issue import Issue

def parse_size_to_bytes(text: str) -> int:
    """
    Parses file size string (e.g. '50 MB', '1.2 GB') to bytes.
    """
    match = re.search(r'(\d+(?:\.\d+)?)\s*(MB|GB|M|G|KB|K)', text, re.IGNORECASE)
    if match:
        val = float(match.group(1))
        unit = match.group(2).lower()
        if 'g' in unit:
            return int(val * 1024 * 1024 * 1024)
        elif 'm' in unit:
            return int(val * 1024 * 1024)
        elif 'k' in unit:
            return int(val * 1024)
    return 50 * 1024 * 1024  # Default 50MB fallback

class JDownloader2:
    """
    Lightweight API client for sending download links to JDownloader2.
    """
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def submit(self, links: Dict[str, str], package_name: str) -> Dict[str, Any]:
        """
        Submits links (URL -> Priority) to JDownloader2.
        """
        endpoint = f"{self.base_url}/linkgrabberv2/addLinks"
        job_id = None
        last_err = None
        for url, priority in links.items():
            query = {
                'assignJobID': True,
                'autostart': True,
                'packageName': package_name,
                'priority': priority,
                'links': url
            }
            if settings.JD2_DEST_DIR:
                query['destinationFolder'] = settings.JD2_DEST_DIR
                
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(endpoint, params={'query': json.dumps(query)})
                    resp.raise_for_status()
                    data = resp.json()
                    inner_data = data.get('data', data)
                    if isinstance(inner_data, dict):
                        job_id = inner_data.get('id') or inner_data.get('jobID')
            except Exception as e:
                logger.error(f"[JD2] Submission failed for url {url}: {e}")
                last_err = e
        
        if job_id:
            return {"status": True, "jobid": str(job_id)}
        return {"status": False, "jobid": None, "error": str(last_err)}

class DDLService:
    """
    Scraper and downloader service for Direct Download Links (DDL) using GetComics.
    Supports Flaresolverr redirection to bypass Cloudflare.
    """
    async def _fetch_url(self, url: str) -> str:
        if settings.ENABLE_FLARESOLVERR and settings.FLARESOLVERR_URL:
            logger.info(f"[DDL] Routing request via FlareSolverr proxy: {url}")
            payload = {
                "cmd": "request.get",
                "url": url,
                "maxTimeout": 60000
            }
            try:
                async with httpx.AsyncClient(timeout=70.0) as client:
                    resp = await client.post(settings.FLARESOLVERR_URL, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    if data.get("status") == "ok":
                        return data["solution"]["response"]
                    else:
                        raise Exception(f"FlareSolverr error: {data.get('status')}")
            except Exception as e:
                logger.error(f"[DDL] FlareSolverr request failed: {e}. Falling back to direct query.")

        # Fallback to direct request
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": "https://getcomics.info/"
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers, follow_redirects=True)
            resp.raise_for_status()
            return resp.text

    async def search_issue(self, comic: Comic, issue: Issue) -> List[SearchResultItem]:
        """
        Searches GetComics for a target comic/issue match.
        """
        # Formulate query: e.g. "Amazing Spider-Man 15"
        query = f"{comic.comic_name} {issue.issue_number}"
        logger.info(f"[DDL] Querying GetComics for: '{query}'")

        try:
            url = f"https://getcomics.info/?s={quote_plus(query)}"
            html = await self._fetch_url(url)
        except Exception as e:
            logger.error(f"[DDL] GetComics search failed: {e}")
            return []

        soup = BeautifulSoup(html, "html.parser")
        articles = soup.find_all("article")
        results = []

        for art in articles:
            # Title
            title_node = art.find("h1", class_="post-title")
            if not title_node:
                title_node = art.find("h2", class_="post-title")
            if not title_node:
                continue
            title = title_node.text.strip()

            # URL
            link_node = art.find("a")
            if not link_node or not link_node.get("href"):
                continue
            post_url = link_node["href"]

            # Parse size from text
            art_text = art.text
            size_bytes = parse_size_to_bytes(art_text)

            results.append(
                SearchResultItem(
                    title=title,
                    download_url=post_url,  # Hold the post page URL (resolved during grab)
                    size=size_bytes,
                    provider_name="GetComics",
                    type="ddl"
                )
            )

        logger.info(f"[DDL] Found {len(results)} search results on GetComics.")
        return results

    async def resolve_download_link(self, post_url: str) -> Optional[str]:
        """
        Fetches the individual post page and extracts the best download link
        based on settings.DDL_PRIORITY_ORDER.
        """
        logger.info(f"[DDL] Resolving download links from: {post_url}")
        try:
            html = await self._fetch_url(post_url)
        except Exception as e:
            logger.error(f"[DDL] Failed to fetch post page: {e}")
            return None

        soup = BeautifulSoup(html, "html.parser")
        classified_links = {}

        anchors = soup.find_all("a", href=True)
        for a in anchors:
            href = a["href"]
            text = a.text.lower()
            title = a.get("title", "").lower()

            if "sh.st" in href or "getcomics.info" in href:
                continue

            if "mega" in href or "mega" in text or "mega" in title:
                classified_links["mega"] = href
            elif "mediafire" in href or "mediafire" in text or "mediafire" in title:
                classified_links["mediafire"] = href
            elif "pixeldrain" in href or "pixeldrain" in text or "pixeldrain" in title:
                classified_links["pixeldrain"] = href
            elif "download now" in text or "main server" in text or "download now" in title:
                classified_links["main"] = href
            elif "mirror download" in text or "mirror" in title:
                classified_links["mirror"] = href

        # Resolve priority list
        try:
            priority_list = json.loads(settings.DDL_PRIORITY_ORDER)
        except Exception:
            priority_list = ["mega", "mediafire", "pixeldrain", "main"]

        if not settings.JD2_ENABLE:
            if "mega" in priority_list:
                priority_list.remove("mega")
                priority_list.append("mega")

        for provider in priority_list:
            if provider in classified_links:
                logger.info(f"[DDL] Resolved matching provider '{provider}': {classified_links[provider]}")
                return classified_links[provider]

        if "mirror" in classified_links:
            return classified_links["mirror"]
        if classified_links:
            fallback = list(classified_links.values())[0]
            logger.info(f"[DDL] Resolved fallback link: {fallback}")
            return fallback

        return None

    async def download_file(self, download_url: str, output_path: str) -> bool:
        """
        Streams a direct download link file from HTTP GET to local disk.
        """
        logger.info(f"[DDL] Streaming download from {download_url} to {output_path}")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://getcomics.info/"
        }
        try:
            # Ensure folder exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("GET", download_url, headers=headers, follow_redirects=True) as response:
                    if response.status_code != 200:
                        logger.error(f"[DDL] Download failed with HTTP {response.status_code}")
                        return False
                    
                    with open(output_path, "wb") as f:
                        async for chunk in response.iter_bytes(chunk_size=8192):
                            f.write(chunk)
            
            logger.info(f"[DDL] Downloaded successfully to {output_path}")
            return True
        except Exception as e:
            logger.error(f"[DDL] Exception downloading file: {e}")
            return False
