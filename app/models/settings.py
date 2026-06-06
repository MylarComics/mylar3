from sqlmodel import SQLModel, Field

class SystemSettings(SQLModel, table=True):
    __tablename__ = "system_settings"
    
    id: int = Field(default=1, primary_key=True)
    
    # ComicVine Settings
    COMICVINE_API_KEY: str = ""
    COMICVINE_API_URL: str = "https://comicvine.gamespot.com/api/"
    CV_USER_AGENT: str = "comictagger image fetcher"
    CVAPI_RATE: float = 2.0
    CV_VERIFY: bool = True
    
    # Folder Settings
    CACHE_DIR: str = "cache"
    DESTINATION_DIR: str = "comics"
    CREATE_FOLDERS: bool = True
    COMIC_COVER_LOCAL: bool = True
    COVER_FOLDER_LOCAL: bool = True
    
    # Indexer Settings
    NEWZNAB_PROVIDERS: str = ""
    TORZNAB_PROVIDERS: str = ""
    
    # Scheduler Settings
    SEARCH_INTERVAL_MINUTES: int = 60
    GRAB_ON_MATCH: bool = True
    CV_SYNC_INTERVAL_HOURS: int = 24
    
    # Downloader Settings
    DOWNLOADER_TYPE: str = "none"
    
    # SABnzbd
    SABNZBD_URL: str = "http://localhost:8080"
    SABNZBD_API_KEY: str = ""
    SABNZBD_CATEGORY: str = "comics"
    
    # NZBGet
    NZBGET_URL: str = "http://localhost:6789"
    NZBGET_USERNAME: str = ""
    NZBGET_PASSWORD: str = ""
    NZBGET_CATEGORY: str = "comics"
    
    # qBittorrent
    QBITTORRENT_URL: str = "http://localhost:8080"
    QBITTORRENT_USERNAME: str = "admin"
    QBITTORRENT_PASSWORD: str = "adminadmin"
    QBITTORRENT_CATEGORY: str = "comics"
    
    # Transmission
    TRANSMISSION_URL: str = "http://localhost:9091"
    TRANSMISSION_USERNAME: str = ""
    TRANSMISSION_PASSWORD: str = ""
    TRANSMISSION_DIRECTORY: str = ""
    
    # Apprise Settings
    APPRISE_URLS: str = ""
    NOTIFY_ON_SNATCH: bool = True
    NOTIFY_ON_FAILURE: bool = True
    NOTIFY_ON_NEW_ISSUES: bool = True
