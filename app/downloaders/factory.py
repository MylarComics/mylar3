from typing import Optional

from app.core.config import settings
from app.core.logger import logger
from app.downloaders.base import BaseDownloader


def get_downloader(client_type: Optional[str] = None) -> Optional[BaseDownloader]:
    """
    Factory function that instantiates and returns the configured
    downloader client. Falls back to DOWNLOADER_TYPE from settings
    if no client_type is explicitly provided.

    Returns None if no valid downloader is configured.
    """
    resolved_type = (client_type or settings.DOWNLOADER_TYPE).lower().strip()

    if resolved_type == "sabnzbd":
        from app.downloaders.sabnzbd import SABnzbdDownloader
        return SABnzbdDownloader()

    if resolved_type == "nzbget":
        from app.downloaders.nzbget import NZBGetDownloader
        return NZBGetDownloader()

    if resolved_type == "qbittorrent":
        from app.downloaders.qbittorrent import QBittorrentDownloader
        return QBittorrentDownloader()

    if resolved_type == "transmission":
        from app.downloaders.transmission import TransmissionDownloader
        return TransmissionDownloader()

    if resolved_type != "none":
        logger.warning(
            f"[Downloaders] Unknown downloader type '{resolved_type}'. "
            "Valid options: sabnzbd, nzbget, qbittorrent, transmission, none."
        )
    return None
