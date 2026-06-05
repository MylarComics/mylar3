from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseDownloader(ABC):
    """
    Abstract base class defining the unified interface all downloader
    clients must implement. Each client handles a specific download
    backend (SABnzbd, NZBGet, qBittorrent, Transmission).
    """

    @abstractmethod
    async def test_connection(self) -> bool:
        """
        Verify the downloader is reachable and credentials are valid.
        Returns True if the connection succeeds, False otherwise.
        """

    @abstractmethod
    async def add_download(
        self,
        url_or_filepath: str,
        title: str,
        category: Optional[str] = None,
    ) -> Optional[str]:
        """
        Submit a new download to the client. For NZB clients this is
        an NZB URL or file path; for torrent clients this is a .torrent
        file path or magnet URI.

        Returns a job identifier string (NZO-ID, NZBID, torrent hash)
        on success, or None on failure.
        """

    @abstractmethod
    async def get_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Query the status of an active or completed download job.

        Returns a normalized dictionary with at minimum:
            {
                "job_id":   str,
                "name":     str,
                "status":   str,   # "Downloading", "Completed", "Failed", "Paused"
                "location": Optional[str],
                "failed":   bool,
            }
        or None if the job cannot be found.
        """

    @abstractmethod
    async def remove_job(self, job_id: str, delete_files: bool = False) -> bool:
        """
        Remove a completed or failed download from the client's history.
        Returns True on success, False otherwise.
        """
