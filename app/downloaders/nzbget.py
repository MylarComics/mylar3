import base64
import json
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.logger import logger
from app.downloaders.base import BaseDownloader


class NZBGetDownloader(BaseDownloader):
    """
    Async NZBGet downloader client using NZBGet's JSON-RPC API.
    Docs: https://nzbget.net/api
    """

    def __init__(self) -> None:
        parsed = urlparse(settings.NZBGET_URL)
        scheme = parsed.scheme or "http"
        host = parsed.hostname or "localhost"
        port = parsed.port or 6789
        path = parsed.path.rstrip("/") or ""

        user = settings.NZBGET_USERNAME
        password = settings.NZBGET_PASSWORD

        if user and password:
            self._rpc_url = f"{scheme}://{user}:{password}@{host}:{port}{path}/jsonrpc"
        else:
            self._rpc_url = f"{scheme}://{host}:{port}{path}/jsonrpc"

        self._category = settings.NZBGET_CATEGORY

    async def _rpc_call(self, method: str, params: list) -> Optional[Any]:
        payload = {"version": "1.1", "method": method, "params": params}
        try:
            async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
                response = await client.post(
                    self._rpc_url,
                    content=json.dumps(payload),
                    headers={"Content-Type": "application/json"},
                )
                data = response.json()
                if data.get("error"):
                    logger.error(f"[NZBGet] RPC error for '{method}': {data['error']}")
                    return None
                return data.get("result")
        except Exception as e:
            logger.error(f"[NZBGet] RPC call '{method}' failed: {e}")
            return None

    async def test_connection(self) -> bool:
        result = await self._rpc_call("version", [])
        if result:
            logger.info(f"[NZBGet] Connected successfully. Version: {result}")
            return True
        logger.warning("[NZBGet] Connection test returned no version.")
        return False

    async def add_download(
        self,
        url_or_filepath: str,
        title: str,
        category: Optional[str] = None,
    ) -> Optional[str]:
        used_category = category or self._category

        # NZBGet appendurl: (name, category, priority, addpaused, dupekey, dupescore, dupemode, url)
        result = await self._rpc_call(
            "appendurl",
            [title, used_category, 0, False, "", 0, "SCORE", url_or_filepath],
        )
        if result and result > 0:
            logger.info(f"[NZBGet] Added download '{title}' with NZBID: {result}")
            return str(result)
        logger.error(f"[NZBGet] Failed to add download '{title}'. Result: {result}")
        return None

    async def get_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        nzbid = int(job_id)

        # Check active queue first
        queue = await self._rpc_call("listgroups", [0])
        if queue:
            for item in queue:
                if item.get("NZBID") == nzbid:
                    raw_status = item.get("Status", "DOWNLOADING")
                    return {
                        "job_id": job_id,
                        "name": item.get("NZBName", ""),
                        "status": "Downloading",
                        "location": item.get("DestDir"),
                        "failed": "FAILURE" in raw_status,
                    }

        # Check history
        history = await self._rpc_call("history", [False])
        if history:
            for item in history:
                if item.get("NZBID") == nzbid:
                    raw_status = item.get("Status", "")
                    failed = "FAILURE" in raw_status
                    return {
                        "job_id": job_id,
                        "name": item.get("Name", ""),
                        "status": "Failed" if failed else "Completed",
                        "location": item.get("DestDir"),
                        "failed": failed,
                    }

        logger.warning(f"[NZBGet] Job {job_id} not found in queue or history.")
        return None

    async def remove_job(self, job_id: str, delete_files: bool = False) -> bool:
        nzbid = int(job_id)
        action = "HistoryDelete" if not delete_files else "HistoryFinalDelete"
        result = await self._rpc_call("editqueue", [action, "", [nzbid]])
        if result:
            logger.info(f"[NZBGet] Removed job {job_id} from history.")
            return True
        logger.warning(f"[NZBGet] Failed to remove job {job_id}.")
        return False
