from typing import Any, Dict, Optional

import httpx

from app.core.config import settings
from app.core.logger import logger
from app.downloaders.base import BaseDownloader


class SABnzbdDownloader(BaseDownloader):
    """
    Async SABnzbd downloader client using SABnzbd's JSON REST API.
    Docs: https://sabnzbd.org/wiki/advanced/api
    """

    def __init__(self) -> None:
        self._base_url = settings.SABNZBD_URL.rstrip("/") + "/api"
        self._api_key = settings.SABNZBD_API_KEY
        self._category = settings.SABNZBD_CATEGORY

    def _base_params(self) -> Dict[str, str]:
        return {"apikey": self._api_key, "output": "json"}

    async def test_connection(self) -> bool:
        params = {**self._base_params(), "mode": "version"}
        try:
            async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
                response = await client.get(self._base_url, params=params)
                data = response.json()
                version = data.get("version", "")
                if version:
                    logger.info(f"[SABnzbd] Connected successfully. Version: {version}")
                    return True
                logger.warning("[SABnzbd] Connected but no version returned.")
                return False
        except Exception as e:
            logger.error(f"[SABnzbd] Connection test failed: {e}")
            return False

    async def add_download(
        self,
        url_or_filepath: str,
        title: str,
        category: Optional[str] = None,
    ) -> Optional[str]:
        used_category = category or self._category
        params = {
            **self._base_params(),
            "mode": "addurl",
            "name": url_or_filepath,
            "nzbname": title,
            "cat": used_category,
        }
        try:
            async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
                response = await client.post(self._base_url, data=params)
                data = response.json()
                if data.get("status") is True:
                    nzo_id = "".join(data.get("nzo_ids", []))
                    logger.info(f"[SABnzbd] Added download '{title}' with NZO-ID: {nzo_id}")
                    return nzo_id or None
                logger.error(f"[SABnzbd] Failed to add download: {data}")
                return None
        except Exception as e:
            logger.error(f"[SABnzbd] Add download failed: {e}")
            return None

    async def get_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        # First check active queue
        queue_params = {
            **self._base_params(),
            "mode": "queue",
            "search": job_id,
        }
        try:
            async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
                queue_resp = await client.get(self._base_url, params=queue_params)
                queue_data = queue_resp.json()
                slots = queue_data.get("queue", {}).get("slots", [])
                for slot in slots:
                    if slot.get("nzo_id") == job_id:
                        status = slot.get("status", "Downloading")
                        return {
                            "job_id": job_id,
                            "name": slot.get("filename", ""),
                            "status": status,
                            "location": None,  # Not available while queued
                            "failed": False,
                        }

                # Not in active queue — check history
                history_params = {
                    **self._base_params(),
                    "mode": "history",
                    "nzo_ids": job_id,
                }
                hist_resp = await client.get(self._base_url, params=history_params)
                hist_data = hist_resp.json()
                hist_slots = hist_data.get("history", {}).get("slots", [])
                for slot in hist_slots:
                    if slot.get("nzo_id") == job_id:
                        raw_status = slot.get("status", "")
                        failed = raw_status == "Failed"
                        return {
                            "job_id": job_id,
                            "name": slot.get("name", ""),
                            "status": "Failed" if failed else "Completed",
                            "location": slot.get("storage", None),
                            "failed": failed,
                        }
        except Exception as e:
            logger.error(f"[SABnzbd] Status check failed for {job_id}: {e}")

        logger.warning(f"[SABnzbd] Job {job_id} not found in queue or history.")
        return None

    async def remove_job(self, job_id: str, delete_files: bool = False) -> bool:
        params = {
            **self._base_params(),
            "mode": "history",
            "name": "delete",
            "value": job_id,
        }
        if delete_files:
            params["del_files"] = "1"
        try:
            async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
                response = await client.get(self._base_url, params=params)
                data = response.json()
                success = data.get("status") is True
                if success:
                    logger.info(f"[SABnzbd] Removed job {job_id} from history.")
                else:
                    logger.warning(f"[SABnzbd] Failed to remove job {job_id}.")
                return success
        except Exception as e:
            logger.error(f"[SABnzbd] Remove job failed for {job_id}: {e}")
            return False
