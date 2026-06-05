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

    model_config = {
        "env_file": ".env",
        "extra": "ignore"
    }

settings = Settings()
