import json
import os
import re
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings
from app.core.logger import logger
from app.downloaders.base import BaseDownloader

# Transmission RPC default path
_RPC_PATH = "/transmission/rpc"
_SESSION_HEADER = "X-Transmission-Session-Id"


class TransmissionDownloader(BaseDownloader):
    """
    Async Transmission downloader using Transmission's JSON-RPC API.
    Docs: https://github.com/transmission/transmission/blob/main/docs/rpc-spec.md
    """

    def __init__(self) -> None:
        self._base_url = settings.TRANSMISSION_URL.rstrip("/") + _RPC_PATH
        self._username = settings.TRANSMISSION_USERNAME or None
        self._password = settings.TRANSMISSION_PASSWORD or None
        self._directory = settings.TRANSMISSION_DIRECTORY or None
        self._session_id: Optional[str] = None

    def _auth(self) -> Optional[httpx.DigestAuth]:
        if self._username and self._password:
            return httpx.BasicAuth(self._username, self._password)
        return None

    async def _rpc_call(
        self, method: str, arguments: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        payload = {"method": method, "arguments": arguments}
        headers = {}
        if self._session_id:
            headers[_SESSION_HEADER] = self._session_id

        try:
            async with httpx.AsyncClient(
                auth=self._auth(), verify=False, timeout=15.0
            ) as client:
                response = await client.post(
                    self._base_url,
                    content=json.dumps(payload),
                    headers={**headers, "Content-Type": "application/json"},
                )

                # Transmission requires a CSRF session token
                if response.status_code == 409:
                    self._session_id = response.headers.get(_SESSION_HEADER, "")
                    headers[_SESSION_HEADER] = self._session_id
                    response = await client.post(
                        self._base_url,
                        content=json.dumps(payload),
                        headers={**headers, "Content-Type": "application/json"},
                    )

                data = response.json()
                if data.get("result") == "success":
                    return data.get("arguments", {})
                logger.error(f"[Transmission] RPC error for '{method}': {data.get('result')}")
                return None
        except Exception as e:
            logger.error(f"[Transmission] RPC call '{method}' failed: {e}")
            return None

    async def test_connection(self) -> bool:
        result = await self._rpc_call("session-get", {"fields": ["version"]})
        if result:
            version = result.get("version", "unknown")
            logger.info(f"[Transmission] Connected successfully. Version: {version}")
            return True
        logger.warning("[Transmission] Connection test failed.")
        return False

    async def add_download(
        self,
        url_or_filepath: str,
        title: str,
        category: Optional[str] = None,
    ) -> Optional[str]:
        arguments: Dict[str, Any] = {}

        if self._directory:
            arguments["download-dir"] = self._directory

        if url_or_filepath.startswith("magnet") or url_or_filepath.startswith("http"):
            arguments["filename"] = url_or_filepath
        else:
            # Read file and encode as base64
            with open(url_or_filepath, "rb") as f:
                import base64
                arguments["metainfo"] = base64.b64encode(f.read()).decode("utf-8")

        result = await self._rpc_call("torrent-add", arguments)
        if result:
            # Can return "torrent-added" or "torrent-duplicate"
            torrent = result.get("torrent-added") or result.get("torrent-duplicate")
            if torrent:
                torrent_hash = torrent.get("hashString", "")
                logger.info(
                    f"[Transmission] Added torrent '{title}' hash: {torrent_hash}"
                )
                return torrent_hash
        logger.error(f"[Transmission] Failed to add download '{title}'.")
        return None

    async def get_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        result = await self._rpc_call(
            "torrent-get",
            {
                "ids": [job_id],
                "fields": [
                    "hashString", "name", "status", "downloadDir",
                    "percentDone", "error", "errorString",
                ],
            },
        )
        if result:
            torrents = result.get("torrents", [])
            if torrents:
                t = torrents[0]
                # Transmission status codes:
                # 0=Stopped, 1=CheckWait, 2=Check, 3=DownloadWait, 4=Download, 5=SeedWait, 6=Seed
                status_code = t.get("status", 0)
                has_error = t.get("error", 0) != 0
                if has_error:
                    normalized = "Failed"
                elif status_code in (5, 6):
                    normalized = "Completed"
                elif status_code == 0:
                    normalized = "Paused"
                else:
                    normalized = "Downloading"

                return {
                    "job_id": job_id,
                    "name": t.get("name", ""),
                    "status": normalized,
                    "location": t.get("downloadDir"),
                    "failed": has_error,
                }

        logger.warning(f"[Transmission] Job {job_id} not found.")
        return None

    async def remove_job(self, job_id: str, delete_files: bool = False) -> bool:
        result = await self._rpc_call(
            "torrent-remove",
            {"ids": [job_id], "delete-local-data": delete_files},
        )
        if result is not None:
            logger.info(f"[Transmission] Removed torrent {job_id}.")
            return True
        logger.warning(f"[Transmission] Failed to remove torrent {job_id}.")
        return False
