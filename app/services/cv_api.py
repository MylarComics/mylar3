import asyncio
import time
from typing import Optional, List, Dict, Any
import httpx
from pydantic import BaseModel, Field
from app.core.config import settings
from app.core.logger import logger

class CVImage(BaseModel):
    icon_url: Optional[str] = None
    medium_url: Optional[str] = None
    super_url: Optional[str] = None
    screen_url: Optional[str] = None
    original_url: Optional[str] = None

class CVPublisherRef(BaseModel):
    id: int
    name: str
    api_detail_url: Optional[str] = None

class CVVolumeRef(BaseModel):
    id: int
    name: str
    api_detail_url: Optional[str] = None

class CVVolume(BaseModel):
    id: int
    name: str
    start_year: Optional[str] = None
    publisher: Optional[CVPublisherRef] = None
    description: Optional[str] = None
    deck: Optional[str] = None
    count_of_issues: Optional[int] = None
    image: Optional[CVImage] = None
    site_detail_url: Optional[str] = None
    aliases: Optional[str] = None

class CVIssue(BaseModel):
    id: int
    issue_number: str
    name: Optional[str] = None
    cover_date: Optional[str] = None
    store_date: Optional[str] = None
    description: Optional[str] = None
    image: Optional[CVImage] = None
    volume: Optional[CVVolumeRef] = None

class CVVolumeResponse(BaseModel):
    error: str
    status_code: int
    results: Optional[CVVolume] = None

class CVIssuesResponse(BaseModel):
    error: str
    status_code: int
    number_of_total_results: int
    results: List[CVIssue] = Field(default_factory=list)

class CVIssueResponse(BaseModel):
    error: str
    status_code: int
    results: Optional[CVIssue] = None

class CVSearchResponse(BaseModel):
    error: str
    status_code: int
    number_of_total_results: int
    results: List[CVVolume] = Field(default_factory=list)


class ComicVineAPIError(Exception):
    pass


class ComicVineClient:
    def __init__(self):
        self.api_key = settings.COMICVINE_API_KEY
        self.base_url = settings.COMICVINE_API_URL.rstrip("/")
        self._last_request_time = 0.0
        self._lock = asyncio.Lock()

    async def _throttle(self):
        async with self._lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < settings.CVAPI_RATE:
                wait_time = settings.CVAPI_RATE - elapsed
                logger.fdebug(f"[ComicVine] Throttling: sleeping {wait_time:.2f} seconds")
                await asyncio.sleep(wait_time)
            self._last_request_time = time.time()

    async def _request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.api_key or self.api_key.lower() == "none":
            logger.warning("[ComicVine] No ComicVine API key configured. API requests will fail.")
            raise ComicVineAPIError("ComicVine API key is not configured. Please get one at http://api.comicvine.com.")

        await self._throttle()

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        req_params = {
            "api_key": self.api_key,
            "format": "json"
        }
        if params:
            req_params.update(params)

        headers = {
            "User-Agent": settings.CV_USER_AGENT
        }

        logger.fdebug(f"[ComicVine] GET {url} with params {params}")
        
        async with httpx.AsyncClient(verify=settings.CV_VERIFY) as client:
            try:
                response = await client.get(url, params=req_params, headers=headers, timeout=30.0)
            except Exception as e:
                logger.error(f"[ComicVine] Request failed to {url}: {e}")
                raise ComicVineAPIError(f"HTTP request failed: {e}")

            if response.status_code == 403 or response.status_code == 429:
                content_str = response.text
                if "Abnormal Traffic Detected" in content_str:
                    logger.error("[ComicVine] Server IP has been banned or rate-limited by ComicVine.")
                    raise ComicVineAPIError("IP rate-limited or banned by ComicVine (Abnormal Traffic Detected).")
                raise ComicVineAPIError(f"HTTP status code {response.status_code}: Access Denied")
            
            if response.status_code != 200:
                raise ComicVineAPIError(f"HTTP status code {response.status_code} returned from ComicVine.")

            try:
                data = response.json()
            except Exception as e:
                logger.error(f"[ComicVine] Failed to parse JSON response: {e}")
                raise ComicVineAPIError(f"Failed to parse JSON response: {e}")

            # Check ComicVine internal status_code
            # status_code 1 is successful response, anything else represents an error
            cv_status = data.get("status_code", 1)
            cv_error = data.get("error", "OK")
            if cv_status != 1:
                logger.error(f"[ComicVine] API error: {cv_error} (status_code {cv_status})")
                raise ComicVineAPIError(f"ComicVine API error: {cv_error}")

            return data

    async def get_volume(self, comic_id: str) -> Optional[CVVolume]:
        """
        Retrieve volume details for 4050-{comic_id}
        """
        # Ensure ID format matches ComicVine standard: 4050-XXXX
        id_str = comic_id
        if not id_str.startswith("4050-"):
            # Strip non-numeric and prefix with 4050-
            clean_id = "".join(filter(str.isdigit, id_str))
            id_str = f"4050-{clean_id}"

        params = {
            "field_list": "id,name,start_year,publisher,description,deck,count_of_issues,image,site_detail_url,aliases"
        }
        
        try:
            data = await self._request(f"volume/{id_str}/", params=params)
            resp = CVVolumeResponse.model_validate(data)
            return resp.results
        except Exception as e:
            logger.error(f"[ComicVine] Error fetching volume details for {comic_id}: {e}")
            raise

    async def get_issues(self, comic_id: str, offset: int = 0) -> CVIssuesResponse:
        """
        Retrieve issues details under volume 4050-{comic_id}
        """
        clean_id = "".join(filter(str.isdigit, comic_id))
        params = {
            "filter": f"volume:{clean_id}",
            "field_list": "id,issue_number,name,cover_date,store_date,description,image,volume",
            "offset": offset,
            "limit": 100
        }

        try:
            data = await self._request("issues/", params=params)
            return CVIssuesResponse.model_validate(data)
        except Exception as e:
            logger.error(f"[ComicVine] Error fetching issues for volume {comic_id}: {e}")
            raise

    async def get_single_issue(self, issue_id: str) -> Optional[CVIssue]:
        """
        Retrieve issue details for 4000-{issue_id}
        """
        id_str = issue_id
        if not id_str.startswith("4000-"):
            clean_id = "".join(filter(str.isdigit, id_str))
            id_str = f"4000-{clean_id}"

        params = {
            "field_list": "id,issue_number,name,cover_date,store_date,description,image,volume"
        }

        try:
            data = await self._request(f"issue/{id_str}/", params=params)
            resp = CVIssueResponse.model_validate(data)
            return resp.results
        except Exception as e:
            logger.error(f"[ComicVine] Error fetching single issue details for {issue_id}: {e}")
            raise

    async def search_volumes(self, query: str) -> List[CVVolume]:
        """
        Search for volumes matching the query string.
        """
        params = {
            "resources": "volume",
            "query": query,
            "field_list": "id,name,start_year,publisher,image,description,deck,count_of_issues"
        }
        try:
            data = await self._request("search/", params=params)
            resp = CVSearchResponse.model_validate(data)
            return resp.results
        except Exception as e:
            logger.error(f"[ComicVine] Error searching volumes for query '{query}': {e}")
            return []
