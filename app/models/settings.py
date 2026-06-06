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

    # General Post-Processing & Quality Settings
    FAILED_DOWNLOAD_HANDLING: bool = False
    FAILED_AUTO: bool = False
    FILE_FORMAT: str = "$Series $Annual $Issue ($Year)"
    FOLDER_FORMAT: str = "$Series ($Year)"
    MOVE_FILES: bool = False
    RENAME_FILES: bool = False
    PREFERRED_QUALITY: int = 0

    # Torrent Search & Download Settings
    ENABLE_PUBLIC: bool = False
    ENABLE_TORRENTS: bool = False
    ENABLE_TORRENT_SEARCH: bool = False
    MINSEEDS: int = 0
    PUBLIC_VERIFY: bool = True

    # Weekly Pull list Settings
    WEEKLY_PULL_PROXY_URL: str = "https://walksoftly.itsaninja.party/newcomics.php"
    ALT_PULL: int = 2
    AUTO_MASS_ADD: bool = False
    BIGGIE_PUB: int = 55
    INDIE_PUB: int = 75
    MASS_PUBLISHERS: str = ""
    PACK_0DAY_WATCHLIST_ONLY: bool = True
    PULL_REFRESH: str = ""
    RESET_PULLIST_PAGINATION: bool = True
    WEEKFOLDER: bool = False
    WEEKFOLDER_FORMAT: int = 0
    WEEKFOLDER_LOC: str = ""

    # Story Arc / Reading list Settings
    ARC_FILEOPS: str = "copy"
    ARC_FILEOPS_SOFTLINK_RELATIVE: bool = False
    ARC_FOLDERFORMAT: str = "$arc ($spanyears)"
    COPY2ARCDIR: bool = False
    SEARCH_STORYARCS: bool = False
    STORYARCDIR: bool = False
    STORYARC_LOCATION: str = ""
    UPCOMING_STORYARCS: bool = False

    # ComicTagger / Metatagging Settings
    CBR2CBZ_ONLY: bool = False
    CMTAGGER_PATH: str = ""
    CMTAG_START_YEAR_AS_VOLUME: bool = True
    CMTAG_VOLUME: bool = True
    CT_CBZ_OVERWRITE: bool = False
    CT_NOTES_FORMAT: str = "Issue ID"
    CT_SETTINGSPATH: str = ""
    CT_TAG_CBL: bool = False
    CT_TAG_CR: bool = True
    CV_BATCH_LIMIT_PROTECTION: bool = True
    CV_BATCH_LIMIT_THRESHOLD: int = 200
    ENABLE_META: bool = False
    SETDEFAULTVOLUME: bool = False
    UNRAR_CMD: str = ""

    # Direct Download Link (DDL) Settings
    DDL_AUTORESUME: bool = True
    DDL_LOCATION: str = ""
    DDL_PREFER_UPSCALED: bool = True
    DDL_PRIORITY_ORDER: str = '["mega", "mediafire", "pixeldrain", "main"]'
    DDL_QUERY_DELAY: int = 15
    ENABLE_DDL: bool = False
    ENABLE_EXTERNAL_SERVER: bool = False
    ENABLE_FLARESOLVERR: bool = False
    ENABLE_GETCOMICS: bool = False
    ENABLE_PROXY: bool = False
    EXTERNAL_APIKEY: str = ""
    EXTERNAL_SERVER: str = ""
    EXTERNAL_USERNAME: str = ""
    FLARESOLVERR_URL: str = ""
    HTTP_PROXY: str = ""
    HTTPS_PROXY: str = ""
    JD2_DEST_DIR: str = ""
    JD2_ENABLE: bool = False
    JD2_URL: str = ""
    PACK_PRIORITY: bool = False

    # Advanced Downloader Client settings
    # SABnzbd
    SAB_CLIENT_POST_PROCESSING: bool = False
    SAB_DIRECTORY: str = ""
    SAB_MOVING_DELAY: int = 5
    SAB_PASSWORD: str = ""
    SAB_PRIORITY: str = "Default"
    SAB_REMOVE_COMPLETED: bool = False
    SAB_REMOVE_FAILED: bool = False
    SAB_TO_MYLAR: bool = False
    SAB_USERNAME: str = ""
    SAB_VERSION: str = ""
    # NZBGet
    NZBGET_CLIENT_POST_PROCESSING: bool = False
    NZBGET_DIRECTORY: str = ""
    NZBGET_PORT: str = ""
    NZBGET_PRIORITY: str = ""
    NZBGET_SUB: str = ""
    # qBittorrent
    QBITTORRENT_FOLDER: str = ""
    QBITTORRENT_LABEL: str = ""
    QBITTORRENT_LOADACTION: str = "default"
    # Transmission
    TRANSMISSION_HOST: str = ""
