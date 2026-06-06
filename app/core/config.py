from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    MYLAR_PORT: int = 8090
    SECRET_KEY: str = "placeholder_secret_key"
    LOG_LEVEL: str = "INFO"

    POSTGRES_USER: str = "mylar"
    POSTGRES_PASSWORD: str = "mylarpass"
    POSTGRES_DB: str = "mylar_new"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    
    DATABASE_URL: str = "postgresql+asyncpg://mylar:mylarpass@postgres:5432/mylar_new"
    REDIS_URL: str = "redis://redis:6379/0"
    
    COMICVINE_API_KEY: str = ""
    COMICVINE_API_URL: str = "https://comicvine.gamespot.com/api/"
    CV_USER_AGENT: str = "comictagger image fetcher"
    CVAPI_RATE: float = 2.0
    CV_VERIFY: bool = True
    CACHE_DIR: str = "cache"
    DESTINATION_DIR: str = "comics"
    CREATE_FOLDERS: bool = True
    COMIC_COVER_LOCAL: bool = True
    COVER_FOLDER_LOCAL: bool = True
    NEWZNAB_PROVIDERS: str = ""
    TORZNAB_PROVIDERS: str = ""

    # Scheduler settings
    SEARCH_INTERVAL_MINUTES: int = 60   # How often to run the wanted-issue search loop
    GRAB_ON_MATCH: bool = True           # Auto-submit best result to downloader on match
    CV_SYNC_INTERVAL_HOURS: int = 24    # How often to re-sync series metadata from ComicVine

    # Downloader settings
    DOWNLOADER_TYPE: str = "none"  # sabnzbd, nzbget, qbittorrent, transmission, none
    
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

    # Notification settings (Apprise)
    # Comma-separated list of Apprise notification URLs.
    # Examples: discord://webhook_id/token, tgram://bot_token/chat_id
    # Full URL list: https://github.com/caronc/apprise/wiki
    APPRISE_URLS: str = ""
    NOTIFY_ON_SNATCH: bool = True    # Notify when a download is successfully submitted
    NOTIFY_ON_FAILURE: bool = True   # Notify when a grab fails after all retries
    NOTIFY_ON_NEW_ISSUES: bool = True  # Notify when db_sync discovers new issues

    model_config = {
        "env_file": ".env",
        "extra": "ignore"
    }

settings = Settings()
