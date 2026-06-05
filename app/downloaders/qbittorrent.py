import re
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings
from app.core.logger import logger
from app.downloaders.base import BaseDownloader

# Status string normalization map from qBittorrent raw states
_STATUS_MAP: Dict[str, str] = {
    "downloading": "Downloading",
    "stalledDL": "Downloading",
    "queuedDL": "Downloading",
    "metaDL": "Downloading",
    "forcedDL": "Downloading",
    "uploading": "Completed",
    "stalledUP": "Completed",
    "queuedUP": "Completed",
    "forcedUP": "Completed",
    "checkingDL": "Downloading",
    "checkingUP": "Completed",
    "pausedDL": "Paused",
    "pausedUP": "Paused",
    "moving": "Completed",
    "error": "Failed",
    "unknown": "Failed",
    "missingFiles": "Failed",
}


class QBittorrentDownloader(BaseDownloader):
    """
    Async qBittorrent downloader using its WebAPI v2 via httpx.
    Docs: https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-(qBittorrent-4.1)
    """

    def __init__(self) -> None:
        self._base_url = settings.QBITTORRENT_URL.rstrip("/")
        self._username = settings.QBITTORRENT_USERNAME
        self._password = settings.QBITTORRENT_PASSWORD
        self._category = settings.QBITTORRENT_CATEGORY
        self._cookies: Optional[httpx.Cookies] = None

    async def _get_authenticated_client(self) -> httpx.AsyncClient:
        client = httpx.AsyncClient(verify=False, timeout=15.0)
        response = await client.post(
            f"{self._base_url}/api/v2/auth/login",
            data={"username": self._username, "password": self._password},
        )
        if response.text != "Ok.":
            await client.aclose()
            raise ConnectionError(
                f"[qBittorrent] Login failed. Response: {response.text}"
            )
        return client

    async def test_connection(self) -> bool:
        try:
            client = await self._get_authenticated_client()
            async with client:
                response = await client.get(f"{self._base_url}/api/v2/app/version")
                version = response.text.strip()
                logger.info(f"[qBittorrent] Connected successfully. Version: {version}")
                return True
        except Exception as e:
            logger.error(f"[qBittorrent] Connection test failed: {e}")
            return False

    async def add_download(
        self,
        url_or_filepath: str,
        title: str,
        category: Optional[str] = None,
    ) -> Optional[str]:
        used_category = category or self._category
        try:
            client = await self._get_authenticated_client()
            async with client:
                if url_or_filepath.startswith("magnet"):
                    data = {
                        "urls": url_or_filepath,
                        "category": used_category,
                        "rename": title,
                    }
                    response = await client.post(
                        f"{self._base_url}/api/v2/torrents/add", data=data
                    )
                    if response.text == "Ok.":
                        torrent_hash = self._extract_magnet_hash(url_or_filepath)
                        logger.info(
                            f"[qBittorrent] Added magnet '{title}' hash: {torrent_hash}"
                        )
                        return torrent_hash
                else:
                    with open(url_or_filepath, "rb") as f:
                        files = {"torrents": (title + ".torrent", f, "application/x-bittorrent")}
                        data = {"category": used_category, "rename": title}
                        response = await client.post(
                            f"{self._base_url}/api/v2/torrents/add",
                            files=files,
                            data=data,
                        )
                    if response.text == "Ok.":
                        torrent_hash = self._get_hash_from_file(url_or_filepath)
                        logger.info(
                            f"[qBittorrent] Added torrent '{title}' hash: {torrent_hash}"
                        )
                        return torrent_hash

                logger.error(f"[qBittorrent] Failed to add torrent. Response: {response.text}")
                return None
        except Exception as e:
            logger.error(f"[qBittorrent] Add download failed: {e}")
            return None

    async def get_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        try:
            client = await self._get_authenticated_client()
            async with client:
                response = await client.get(
                    f"{self._base_url}/api/v2/torrents/info",
                    params={"hashes": job_id.lower()},
                )
                torrents = response.json()
                if torrents:
                    t = torrents[0]
                    raw_state = t.get("state", "unknown")
                    normalized = _STATUS_MAP.get(raw_state, "Downloading")
                    return {
                        "job_id": job_id,
                        "name": t.get("name", ""),
                        "status": normalized,
                        "location": t.get("save_path"),
                        "failed": normalized == "Failed",
                    }
        except Exception as e:
            logger.error(f"[qBittorrent] Status check failed for {job_id}: {e}")

        logger.warning(f"[qBittorrent] Job {job_id} not found.")
        return None

    async def remove_job(self, job_id: str, delete_files: bool = False) -> bool:
        try:
            client = await self._get_authenticated_client()
            async with client:
                response = await client.post(
                    f"{self._base_url}/api/v2/torrents/delete",
                    data={
                        "hashes": job_id.lower(),
                        "deleteFiles": "true" if delete_files else "false",
                    },
                )
                success = response.status_code == 200
                if success:
                    logger.info(f"[qBittorrent] Removed torrent {job_id}.")
                else:
                    logger.warning(f"[qBittorrent] Failed to remove torrent {job_id}.")
                return success
        except Exception as e:
            logger.error(f"[qBittorrent] Remove job failed for {job_id}: {e}")
            return False

    @staticmethod
    def _extract_magnet_hash(magnet_url: str) -> Optional[str]:
        match = re.search(r"urn:btih:([a-fA-F0-9]{32,40})", magnet_url)
        return match.group(1).upper() if match else None

    @staticmethod
    def _get_hash_from_file(filepath: str) -> Optional[str]:
        """
        Extract info-hash from a .torrent file using a lightweight
        native bencode parser to avoid heavy external dependencies.
        """
        try:
            import hashlib
            with open(filepath, "rb") as f:
                raw = f.read()
            # Find the info dict manually by locating "4:info" marker
            info_start = raw.find(b"4:info") + 6
            if info_start < 6:
                return None
            # We need to extract the raw bytes of the info dict value
            # by parsing the bencoded structure length
            info_bytes = _bencode_slice(raw, info_start)
            if info_bytes is not None:
                return hashlib.sha1(info_bytes).hexdigest().upper()
        except Exception as e:
            logger.error(f"[qBittorrent] Failed to extract hash from {filepath}: {e}")
        return None


def _bencode_slice(data: bytes, start: int) -> Optional[bytes]:
    """
    Return the raw bytes of a single bencoded value starting at `start`.
    Used only for extracting the info dictionary from .torrent files.
    """
    if start >= len(data):
        return None
    first = chr(data[start])
    if first == "d":  # dict
        end = _skip_bencode(data, start)
        return data[start:end] if end else None
    if first == "l":  # list
        end = _skip_bencode(data, start)
        return data[start:end] if end else None
    if first.isdigit():  # string
        colon = data.index(b":", start)
        length = int(data[start:colon])
        return data[start : colon + 1 + length]
    if first == "i":  # integer
        end = data.index(b"e", start) + 1
        return data[start:end]
    return None


def _skip_bencode(data: bytes, pos: int) -> Optional[int]:
    """Return the index one past the end of a bencoded value starting at pos."""
    if pos >= len(data):
        return None
    c = chr(data[pos])
    if c == "i":
        end = data.index(b"e", pos)
        return end + 1
    if c.isdigit():
        colon = data.index(b":", pos)
        length = int(data[pos:colon])
        return colon + 1 + length
    if c in ("d", "l"):
        pos += 1
        while pos < len(data) and chr(data[pos]) != "e":
            new_pos = _skip_bencode(data, pos)
            if new_pos is None:
                return None
            pos = new_pos
        return pos + 1  # skip over 'e'
    return None
